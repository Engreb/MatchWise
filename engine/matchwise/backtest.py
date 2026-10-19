"""Leakage-safe chronological replay and evaluation.

Each season is replayed in 7-day blocks: the model is refitted on every result before the
block starts and then predicts every match in the block. Tuning uses VALIDATION seasons only;
TEST seasons are evaluated once with the chosen configuration.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np

from .data import LEAGUES, ROOT, SEASONS, TUNING_DIVS, UNDERSTAT_LEAGUES, Match, load_results
from .blend import blended_prediction, tune_weights
from .model import DCModel, fit, linked_priors, prediction, promoted_priors, shrink_total

VALIDATION = ["2324"]
TEST = ["2425", "2526"]
# alpha = weight on actual goals; the rest is shots on target converted to goal-equivalents.
CONFIGS = [(xi, ridge, alpha) for xi in (0.001, 0.002, 0.003) for ridge in (2.0, 5.0) for alpha in (1.0, 0.7, 0.5, 0.3)]
DEFAULT_CONFIG = {"xi": 0.002, "ridge": 2.0, "alpha": 1.0}
CONFIG_PATH = ROOT / "data" / "model_config.json"
BLOCK_DAYS = 7
SEASON_LABEL = {s: f"20{s[:2]}–{s[2:]}" for s in SEASONS}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return dict(DEFAULT_CONFIG)


def season_teams(matches: list[Match], season: str) -> set[str]:
    return {t for m in matches if m.season == season for t in (m.home, m.away)}


# Second divisions whose data can rate teams promoted into a top division.
FEEDERS = {"E0": "E1"}


def preseason_priors(matches, season, xi, ridge, extra_teams=(), feeder=None):
    """Teams in the league this season, rating priors for promoted sides, and the
    low-score correction rho estimated from goals before the season."""
    i = SEASONS.index(season)
    teams = season_teams(matches, season) | set(extra_teams)
    in_season = [m.date for m in matches if m.season == season]
    if i == 0 or not in_season:
        return sorted(teams), {}, None
    prev = season_teams(matches, SEASONS[i - 1])
    start = min(in_season)
    base = fit(matches, start, xi, ridge)
    promoted = sorted(teams - prev)
    priors = promoted_priors(base, sorted(prev - teams), promoted)
    if feeder and promoted:
        # Rate promoted sides from a joint top + second division fit instead of the
        # relegated-sides average (falls back to that for any team the joint fit lacks).
        joint = fit(matches + feeder, start, xi, ridge, divisions=[matches[0].div, feeder[0].div])
        priors.update(linked_priors(base, joint, promoted))
    return sorted(teams), priors, base.rho


def mix_targets(matches, mix, cutoff):
    """Replace each result's goals with a weighted mix of goals, shots on target and xG (each
    scaled to goal-equivalents using the league's ratios before `cutoff`). A match missing a
    component uses the remaining ones, re-weighted. Only used for fitting ratings; predictions
    are always scored against real goals."""
    g, s_, x = mix
    if s_ <= 0 and x <= 0:
        return matches
    prior = [m for m in matches if m.played and m.date < cutoff]
    sot = [m for m in prior if m.hst is not None]
    ks = sum(m.hg + m.ag for m in sot) / max(1, sum(m.hst + m.ast for m in sot))
    xg_prior = [m for m in prior if m.hxg is not None]
    kx = sum(m.hg + m.ag for m in xg_prior) / sum(m.hxg + m.axg for m in xg_prior) if xg_prior else 1.0
    out = []
    for m in matches:
        if not m.played:
            out.append(m)
            continue
        parts = [(g, m.hg, m.ag)]
        if s_ > 0 and m.hst is not None:
            parts.append((s_, ks * m.hst, ks * m.ast))
        if x > 0 and m.hxg is not None:
            parts.append((x, kx * m.hxg, kx * m.axg))
        if len(parts) == 1:
            out.append(m)
            continue
        tw = sum(w for w, _, _ in parts)
        out.append(replace(m, hg=sum(w * h for w, h, _ in parts) / tw, ag=sum(w * a for w, _, a in parts) / tw))
    return out


def shot_mixed(matches, alpha, cutoff):
    """alpha*goals + (1-alpha)*goal-equivalent shots on target (no xG)."""
    return mix_targets(matches, (alpha, 1 - alpha, 0.0), cutoff)


def mix_for(cfg, div):
    """The ratings mix used for a league: goals/shots/xG where xG history exists and xG was
    adopted, otherwise goals/shots."""
    if cfg.get("mix_xg") and div in UNDERSTAT_LEAGUES:
        return tuple(cfg["mix_xg"])
    a = cfg.get("alpha", 1.0)
    return (a, 1 - a, 0.0)


def _fit_mixed(matches, cutoff, cfg, teams, priors):
    """Fit with the configured goals/shots mix. Goal rates come from the mix; the low-score
    correction comes from actual goals (it describes scorelines, not chance creation)."""
    mix = mix_for(cfg, matches[0].div)
    if mix[0] >= 1:
        return fit(matches, cutoff, cfg["xi"], cfg["ridge"], teams=teams, priors=priors)
    m = fit(mix_targets(matches, mix, cutoff), cutoff, cfg["xi"], cfg["ridge"], teams=teams, priors=priors, fix_rho=True)
    m.rho = fit(matches, cutoff, cfg["xi"], cfg["ridge"], teams=teams, priors=priors).rho
    return m


def fit_current(matches, cutoff, cfg, teams, priors):
    """Fit with the configured ratings mix and pull of expected total goals towards the league average."""
    m = _fit_mixed(matches, cutoff, cfg, teams, priors)
    m.total_target, m.total_shrink = league_total(matches, cutoff), cfg.get("total_shrink", 0.0)
    return m


def league_total(matches, cutoff, days=365):
    """Average goals per game in the league over the `days` before `cutoff`."""
    recent = [m.hg + m.ag for m in matches if m.played and m.date < cutoff and (cutoff - m.date).days <= days]
    return float(np.mean(recent)) if recent else None


def _baseline(matches, cutoff):
    recent = [m for m in matches if m.played and m.date < cutoff and (cutoff - m.date).days <= 365]
    n = len(recent)
    h = sum(m.hg > m.ag for m in recent) / n
    d = sum(m.hg == m.ag for m in recent) / n
    o25 = sum(m.hg + m.ag > 2.5 for m in recent) / n
    btts = sum(m.hg > 0 and m.ag > 0 for m in recent) / n
    return (h, d, 1 - h - d), o25, btts


def replay(matches, season, xi, ridge, *, alpha=1.0, mix=None, fix_rho=False, with_baseline=False,
           extra_teams=(), feeder=None, total_shrink=0.0):
    """Yield (match, prediction, model, baseline) for every played match in `season`."""
    teams, priors, rho = preseason_priors(matches, season, xi, ridge, extra_teams, feeder)
    played = [m for m in matches if m.season == season and m.played]
    mix = tuple(mix) if mix else (alpha, 1 - alpha, 0.0)
    alpha = mix[0]
    # Goals-per-shot and goals-per-xG ratios from before the season, so nothing in-season leaks.
    mixed = mix_targets(matches, mix, played[0].date) if played else matches
    i, model = 0, None
    while i < len(played):
        start = played[i].date
        if alpha < 1:
            model = fit(mixed, start, xi, ridge, teams=teams, priors=priors, fix_rho=True, init=model)
            model.rho = 0.0 if fix_rho else rho
        else:
            model = fit(matches, start, xi, ridge, teams=teams, priors=priors, fix_rho=fix_rho, init=model)
        if total_shrink:
            model.total_target, model.total_shrink = league_total(matches, start), total_shrink
        base = _baseline(matches, start) if with_baseline else None
        end = start + timedelta(days=BLOCK_DAYS)
        while i < len(played) and played[i].date < end:
            m = played[i]
            assert model.cutoff <= m.date, "leakage: model fitted on or after match date"
            yield m, model.predict(m.home, m.away), model, base
            i += 1


def _outcome(m: Match) -> int:
    return 0 if m.hg > m.ag else (1 if m.hg == m.ag else 2)


def record(m: Match, p, base=None) -> dict:
    r = {
        "div": m.div, "season": m.season, "date": m.date.isoformat(), "home": m.home, "away": m.away,
        "hg": m.hg, "ag": m.ag, "outcome": _outcome(m),
        "p": [p.home, p.draw, p.away], "o25": p.over(2.5), "btts": p.btts,
        "lam": p.lam, "mu": p.mu, "rho": p.rho,
        "mkt": list(m.market_close) if m.market_close else None,
        "mkt_open": list(m.market_open) if m.market_open else None,
        "mkt_o25": m.market_o25_close,
        "mkt_o25_open": m.market_o25_open,
    }
    if base:
        r["base"] = list(base[0]); r["base_o25"] = base[1]; r["base_btts"] = base[2]
    return r


# ---------- metrics ----------
EPS = 1e-12


def ll_1x2(p, o):
    return -math.log(max(p[o], EPS))


def brier_1x2(p, o):
    return sum((p[k] - (1.0 if k == o else 0.0)) ** 2 for k in range(3))


def ll_bin(p, y):
    return -math.log(max(p if y else 1 - p, EPS))


def brier_bin(p, y):
    return (p - (1.0 if y else 0.0)) ** 2


def summarize_1x2(rows, key):
    rows = [r for r in rows if r.get(key)]
    if not rows:
        return None
    return {
        "n": len(rows),
        "log_loss": float(np.mean([ll_1x2(r[key], r["outcome"]) for r in rows])),
        "brier": float(np.mean([brier_1x2(r[key], r["outcome"]) for r in rows])),
        "accuracy": float(np.mean([int(np.argmax(r[key])) == r["outcome"] for r in rows])),
    }


def summarize_bin(rows, key, target):
    rows = [r for r in rows if r.get(key) is not None]
    if not rows:
        return None
    ys = [target(r) for r in rows]
    return {
        "n": len(rows),
        "log_loss": float(np.mean([ll_bin(r[key], y) for r, y in zip(rows, ys)])),
        "brier": float(np.mean([brier_bin(r[key], y) for r, y in zip(rows, ys)])),
    }


def is_over(r):
    return r["hg"] + r["ag"] > 2.5


def is_btts(r):
    return r["hg"] > 0 and r["ag"] > 0


def bootstrap_diff(a, b, n_boot=2000, seed=7):
    """95% percentile interval for mean(a - b), resampling matches."""
    d = np.asarray(a) - np.asarray(b)
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), (n_boot, len(d)))].mean(axis=1)
    return {"mean": float(d.mean()), "lo": float(np.percentile(means, 2.5)), "hi": float(np.percentile(means, 97.5))}


def calibration(pairs, bins=10):
    pairs = np.asarray(pairs)
    out, ece = [], 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = (pairs[:, 0] >= lo) & ((pairs[:, 0] < hi) if b < bins - 1 else (pairs[:, 0] <= hi))
        if sel.sum() == 0:
            continue
        mp, fr = float(pairs[sel, 0].mean()), float(pairs[sel, 1].mean())
        out.append({"bin": [lo, hi], "predicted": mp, "observed": fr, "n": int(sel.sum())})
        ece += sel.sum() / len(pairs) * abs(mp - fr)
    return out, float(ece)


# ---------- runs ----------
def _objective(rows):
    return (np.mean([ll_1x2(r["p"], r["outcome"]) for r in rows])
            + np.mean([ll_bin(r["o25"], is_over(r)) for r in rows]))


def tune(data: dict[str, list[Match]], log=print) -> tuple[dict, list[dict], list[dict]]:
    tried, rows_by = [], {}
    for xi, ridge, alpha in CONFIGS:
        rows = []
        for div, matches in data.items():
            for season in VALIDATION:
                rows += [record(m, p) for m, p, _, _ in replay(matches, season, xi, ridge, alpha=alpha)]
        rows_by[(xi, ridge, alpha)] = rows
        obj = float(_objective(rows))
        s = summarize_1x2(rows, "p")
        tried.append({"xi": xi, "ridge": ridge, "alpha": alpha, "objective": obj, "log_loss_1x2": s["log_loss"], "n": s["n"]})
        log(f"  xi={xi} ridge={ridge} goals-weight={alpha}: objective {obj:.4f}")
    best = min(tried, key=lambda t: t["objective"])
    goals_best = min((t for t in tried if t["alpha"] >= 1), key=lambda t: t["objective"])
    cfg = {"xi": best["xi"], "ridge": best["ridge"], "alpha": best["alpha"],
           "goals_only": {"xi": goals_best["xi"], "ridge": goals_best["ridge"]}}
    return cfg, tried, rows_by[(best["xi"], best["ridge"], best["alpha"])]


def evaluate(data, cfg, log=print) -> dict:
    dc_rows, pois_rows, goal_rows = [], [], []
    g = cfg["goals_only"]
    ts = cfg.get("total_shrink", 0.0)
    for div, matches in data.items():
        for season in TEST:
            log(f"  test replay {div} {season}")
            dc_rows += [record(m, p, b) for m, p, _, b in
                        replay(matches, season, cfg["xi"], cfg["ridge"], mix=mix_for(cfg, div), with_baseline=True,
                               total_shrink=ts)]
            pois_rows += [record(m, p) for m, p, _, _ in
                          replay(matches, season, cfg["xi"], cfg["ridge"], mix=mix_for(cfg, div), fix_rho=True,
                                 total_shrink=ts)]
            goal_rows += [record(m, p) for m, p, _, _ in replay(matches, season, g["xi"], g["ridge"], total_shrink=ts)]
    for r, q, gr in zip(dc_rows, pois_rows, goal_rows):
        assert (r["home"], r["date"]) == (q["home"], q["date"]) == (gr["home"], gr["date"])
        r["pois"] = q["p"]; r["pois_o25"] = q["o25"]; r["pois_btts"] = q["btts"]
        r["goals"] = gr["p"]; r["goals_o25"] = gr["o25"]; r["goals_btts"] = gr["btts"]
    log("  blending with pre-match odds…")
    for r in dc_rows:
        if r["mkt_open"]:
            b = blended_prediction(prediction(r["lam"], r["mu"], r["rho"]), r["mkt_open"], r["mkt_o25_open"], cfg["blend"])
            r["blend"] = [b.home, b.draw, b.away]; r["blend_o25"] = b.over(2.5); r["blend_btts"] = b.btts

    # Compare on matches with both pre-match and closing prices so every approach scores the same games.
    common = [r for r in dc_rows if r["mkt"] and r["mkt_open"]]
    approaches = [
        ("dc", "Model only" + (" (goals + xG in the top five, goals + shots elsewhere)" if cfg.get("mix_xg") else " (goals + shots on target)" if cfg["alpha"] < 1 else " (Dixon–Coles)"), "p", "o25", "btts"),
        ("goals", "Model only, goals-based ratings", "goals", "goals_o25", "goals_btts"),
        ("blend", "Model + pre-match bookmaker odds (blended)", "blend", "blend_o25", "blend_btts"),
        ("market_open", "Bookmaker pre-match odds", "mkt_open", "mkt_o25_open", None),
        ("market", "Bookmaker closing odds", "mkt", "mkt_o25", None),
        ("poisson", "Independent Poisson", "pois", "pois_o25", "pois_btts"),
        ("base", "League averages only", "base", "base_o25", "base_btts"),
    ]
    table = []
    for key, label, k1, ko, kb in approaches:
        table.append({
            "key": key, "label": label,
            "x12": summarize_1x2(common, k1),
            "o25": summarize_bin(common, ko, is_over),
            "btts": summarize_bin(common, kb, is_btts) if kb else None,
        })

    ll = lambda k: [ll_1x2(r[k], r["outcome"]) for r in common]
    diffs = {
        "dc_vs_market": bootstrap_diff(ll("p"), ll("mkt")),
        "dc_vs_poisson": bootstrap_diff(ll("p"), ll("pois")),
        "dc_vs_base": bootstrap_diff(ll("p"), ll("base")),
        "blend_vs_dc": bootstrap_diff(ll("blend"), ll("p")),
        "dc_vs_goals": bootstrap_diff(ll("p"), ll("goals")),
        "blend_vs_market_open": bootstrap_diff(ll("blend"), ll("mkt_open")),
        "blend_vs_market": bootstrap_diff(ll("blend"), ll("mkt")),
    }
    cal_x12, ece_x12 = calibration([(r["p"][k], int(r["outcome"] == k)) for r in dc_rows for k in range(3)])
    cal_o25, ece_o25 = calibration([(r["o25"], int(is_over(r))) for r in dc_rows])
    cal_btts, ece_btts = calibration([(r["btts"], int(is_btts(r))) for r in dc_rows])
    cal_blend_o25, ece_blend_o25 = calibration([(r["blend_o25"], int(is_over(r))) for r in common])
    cal_blend, ece_blend = calibration([(r["blend"][k], int(r["outcome"] == k)) for r in common for k in range(3)])

    by_league = []
    for div, (key, name) in LEAGUES.items():
        rows = [r for r in common if r["div"] == div]
        by_league.append({"key": key, "name": name, "tuned_on": div in TUNING_DIVS,
                          "dc": summarize_1x2(rows, "p"), "blend": summarize_1x2(rows, "blend"),
                          "market": summarize_1x2(rows, "mkt"),
                          "o25": summarize_bin(rows, "o25", is_over), "o25_market": summarize_bin(rows, "mkt_o25", is_over),
                          "btts": summarize_bin(rows, "btts", is_btts)})
    by_season = []
    for season in TEST:
        rows = [r for r in common if r["season"] == season]
        by_season.append({"season": SEASON_LABEL[season], "dc": summarize_1x2(rows, "p"), "market": summarize_1x2(rows, "mkt")})

    # Promotion gate (docs/MODEL.md): beat both naive baselines with a 95% interval below zero
    # and keep calibration error small. Matching the bookmakers is reported, not required.
    validated = (diffs["dc_vs_base"]["hi"] < 0 and diffs["dc_vs_poisson"]["mean"] <= 0.002 and ece_x12 < 0.03)
    return {
        "test_seasons": [SEASON_LABEL[s] for s in TEST],
        "validation_seasons": [SEASON_LABEL[s] for s in VALIDATION],
        "n_matches": len(dc_rows), "n_common": len(common),
        "table": table, "diffs": diffs,
        "calibration_1x2": cal_x12, "ece_1x2": ece_x12,
        "calibration_o25": cal_o25, "ece_o25": ece_o25,
        "calibration_btts": cal_btts, "ece_btts": ece_btts,
        "calibration_blend_o25": cal_blend_o25, "ece_blend_o25": ece_blend_o25,
        "tuning_leagues": [LEAGUES[d][1] for d in TUNING_DIVS],
        "calibration_blend": cal_blend, "ece_blend": ece_blend,
        "by_league": by_league, "by_season": by_season,
        "status": "validated" if validated else "research",
    }


def run(out_dir: Path, log=print) -> dict:
    t0 = time.time()
    data = {div: load_results(div) for div in LEAGUES}
    prev = load_config()
    log("Tuning on validation season(s)…")
    # Settings are tuned on the original nine leagues only; the others are pure out-of-sample tests.
    cfg, tried, val_rows = tune({d: data[d] for d in TUNING_DIVS}, log)
    cfg["blend"] = tune_weights([r for r in val_rows], ll_1x2, ll_bin, is_over)
    if prev.get("mix_xg"):
        cfg["mix_xg"] = prev["mix_xg"]  # adopted by the separate xG experiment; keep it
    if prev.get("total_shrink"):
        cfg["total_shrink"] = prev["total_shrink"]  # adopted by the separate totals experiment; keep it
    log(f"Chosen: xi={cfg['xi']} ridge={cfg['ridge']} blend weights 1X2={cfg['blend']['w_1x2']} O2.5={cfg['blend']['w_o25']}")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    log("Evaluating on held-out test seasons…")
    res = evaluate(data, cfg, log)
    log("Testing second-division links for promoted teams…")
    res["link_test"] = link_experiment(data, cfg, log)
    cfg["link"] = {top: r["adopt"] for top, r in res["link_test"].items()}
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    res["config"] = cfg
    # Results of the separate one-off experiments (xG, team news, total goals) are kept across re-runs.
    acc = out_dir / "accuracy.json"
    prev_res = json.loads(acc.read_text(encoding="utf-8")) if acc.exists() else {}
    for k in ("xg_test", "injury_test", "totals_test"):
        if k in prev_res:
            res[k] = prev_res[k]
    res["configs_tried"] = tried
    res["block_days"] = BLOCK_DAYS
    res["runtime_s"] = round(time.time() - t0, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "accuracy.json").write_text(json.dumps(res, indent=1))
    log(f"Done in {res['runtime_s']}s. Status: {res['status']}")
    return res


def link_experiment(data, cfg, log=print) -> dict:
    """Does rating promoted sides from the second division beat the relegated-average prior?
    Compared on the top division only, chosen on validation and confirmed on test seasons."""
    out = {}
    for top, second in FEEDERS.items():
        if top not in data or second not in data:
            continue
        res = {}
        for label, seasons in (("validation", VALIDATION), ("test", TEST)):
            rows = {"base": [], "linked": []}
            for season in seasons:
                prev = season_teams(data[top], SEASONS[SEASONS.index(season) - 1])
                for key, feeder in (("base", None), ("linked", data[second])):
                    for m, p, _, _ in replay(data[top], season, cfg["xi"], cfg["ridge"], alpha=cfg["alpha"], feeder=feeder):
                        r = record(m, p)
                        r["promoted_game"] = m.home not in prev or m.away not in prev
                        rows[key].append(r)
            promoted_rows = {k: [r for r in v if r["promoted_game"]] for k, v in rows.items()}
            ll = lambda rs: [ll_1x2(r["p"], r["outcome"]) for r in rs]
            res[label] = {
                "all": bootstrap_diff(ll(rows["linked"]), ll(rows["base"])),
                "promoted_matches": bootstrap_diff(ll(promoted_rows["linked"]), ll(promoted_rows["base"])),
                "n": len(rows["base"]), "n_promoted": len(promoted_rows["base"]),
            }
            log(f"  {top}<-{second} {label}: log loss change {res[label]['all']['mean']:+.4f} "
                f"(promoted-team matches {res[label]['promoted_matches']['mean']:+.4f}, n={res[label]['n_promoted']})")
        res["adopt"] = res["validation"]["all"]["mean"] < 0 and res["test"]["all"]["mean"] <= 0
        out[top] = res
    return out


XG_MIXES = [(0.7, 0.3, 0.0), (0.5, 0.2, 0.3), (0.4, 0.1, 0.5), (0.3, 0.1, 0.6), (0.5, 0.0, 0.5), (0.3, 0.0, 0.7), (0.2, 0.0, 0.8)]


def xg_experiment(data, cfg, log=print) -> dict:
    """Does adding xG to the ratings beat the current goals + shots mix? Top five leagues only
    (where xG history exists). Mix chosen on validation, confirmed on the held-out test seasons."""
    divs = [d for d in UNDERSTAT_LEAGUES if d in data]
    a0 = cfg.get("alpha", 1.0)
    current = (a0, round(1 - a0, 10), 0.0)

    def rows_for(mix, seasons):
        out = []
        for d in divs:
            for season in seasons:
                out += [record(m, p) for m, p, _, _ in replay(data[d], season, cfg["xi"], cfg["ridge"], mix=mix)]
        return out

    tried = []
    for mix in XG_MIXES:
        obj = float(_objective(rows_for(mix, VALIDATION)))
        tried.append({"mix": list(mix), "objective": obj})
        log(f"  goals/shots/xG {mix}: validation objective {obj:.4f}")
    best = tuple(min(tried, key=lambda t: t["objective"])["mix"])
    base_rows, best_rows = rows_for(current, TEST), rows_for(best, TEST)
    for a, b in zip(base_rows, best_rows):
        assert (a["home"], a["date"]) == (b["home"], b["date"])
    ll1 = lambda rs: [ll_1x2(r["p"], r["outcome"]) for r in rs]
    llo = lambda rs: [ll_bin(r["o25"], is_over(r)) for r in rs]
    llb = lambda rs: [ll_bin(r["btts"], is_btts(r)) for r in rs]
    res = {
        "current": list(current), "best": list(best), "tried": tried, "n_test": len(base_rows),
        "x12": bootstrap_diff(ll1(best_rows), ll1(base_rows)),
        "o25": bootstrap_diff(llo(best_rows), llo(base_rows)),
        "btts": bootstrap_diff(llb(best_rows), llb(base_rows)),
        "accuracy_current": float(np.mean([int(np.argmax(r["p"])) == r["outcome"] for r in base_rows])),
        "accuracy_best": float(np.mean([int(np.argmax(r["p"])) == r["outcome"] for r in best_rows])),
        "by_league": {},
    }
    for d in divs:
        a = [r for r in base_rows if r["div"] == d]
        b = [r for r in best_rows if r["div"] == d]
        res["by_league"][LEAGUES[d][0]] = {"name": LEAGUES[d][1], "n": len(a),
                                           "x12_change": float(np.mean(ll1(b)) - np.mean(ll1(a))),
                                           "o25_change": float(np.mean(llo(b)) - np.mean(llo(a)))}
    val_best = min(t["objective"] for t in tried)
    val_cur = next((t["objective"] for t in tried if tuple(t["mix"]) == current), val_best)
    res["adopt"] = best != current and val_best < val_cur and (res["x12"]["mean"] + res["o25"]["mean"]) < 0
    verdict = "ADOPT" if res["adopt"] else "keep current"
    log(f"  best {best} vs current {current}: test log loss change 1X2 {res['x12']['mean']:+.4f} "
        f"(95% {res['x12']['lo']:+.4f} to {res['x12']['hi']:+.4f}), O2.5 {res['o25']['mean']:+.4f}, "
        f"BTTS {res['btts']['mean']:+.4f} -> {verdict}")
    return res


TOTAL_SHRINKS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)


def totals_experiment(data, cfg, log=print) -> dict:
    """Does pulling each match's expected total goals towards the league's recent average fix the
    over/under and both-teams-to-score calibration? The pull is chosen on the validation season
    (tuning leagues only) and confirmed on the test seasons across every league."""
    def rows_for(divs, seasons):
        out = []
        for d in divs:
            for season in seasons:
                cache = {}
                for m, p, model, _ in replay(data[d], season, cfg["xi"], cfg["ridge"], mix=mix_for(cfg, d)):
                    if model.cutoff not in cache:
                        cache[model.cutoff] = league_total(data[d], model.cutoff)
                    r = record(m, p)
                    r["target"] = cache[model.cutoff]
                    out.append(r)
        return out

    def shrunk(rows, s):
        out = []
        for r in rows:
            q = prediction(*shrink_total(r["lam"], r["mu"], r["target"], s), r["rho"])
            out.append({**r, "p": [q.home, q.draw, q.away], "o25": q.over(2.5), "btts": q.btts})
        return out

    ll1 = lambda rs: [ll_1x2(r["p"], r["outcome"]) for r in rs]
    llo = lambda rs: [ll_bin(r["o25"], is_over(r)) for r in rs]
    llb = lambda rs: [ll_bin(r["btts"], is_btts(r)) for r in rs]
    objective = lambda rs: float(np.mean(ll1(rs)) + np.mean(llo(rs)) + np.mean(llb(rs)))

    val = rows_for([d for d in TUNING_DIVS if d in data], VALIDATION)
    tried = []
    for s in TOTAL_SHRINKS:
        rs = shrunk(val, s)
        tried.append({"shrink": s, "objective": objective(rs), "x12": float(np.mean(ll1(rs))),
                      "o25": float(np.mean(llo(rs))), "btts": float(np.mean(llb(rs)))})
        log(f"  shrink {s}: validation objective {tried[-1]['objective']:.4f}")
    best = min(tried, key=lambda t: t["objective"])["shrink"]

    test = rows_for(list(data), TEST)
    base_rows, best_rows = shrunk(test, 0.0), shrunk(test, best)
    ece = lambda rs, k, f: calibration([(r[k], int(f(r))) for r in rs])[1]
    ece12 = lambda rs: calibration([(r["p"][k], int(r["outcome"] == k)) for r in rs for k in range(3)])[1]
    res = {
        "best": best, "tried": tried, "n_validation": len(val), "n_test": len(test),
        "x12": bootstrap_diff(ll1(best_rows), ll1(base_rows)),
        "o25": bootstrap_diff(llo(best_rows), llo(base_rows)),
        "btts": bootstrap_diff(llb(best_rows), llb(base_rows)),
        "ece_before": {"x12": ece12(base_rows), "o25": ece(base_rows, "o25", is_over), "btts": ece(base_rows, "btts", is_btts)},
        "ece_after": {"x12": ece12(best_rows), "o25": ece(best_rows, "o25", is_over), "btts": ece(best_rows, "btts", is_btts)},
        "by_group": {},
        "by_league": {},
    }
    for group, divs in (("tuning_leagues", set(TUNING_DIVS)), ("other_leagues", set(data) - set(TUNING_DIVS))):
        a = [r for r in base_rows if r["div"] in divs]
        b = [r for r in best_rows if r["div"] in divs]
        res["by_group"][group] = {"n": len(a), "x12": bootstrap_diff(ll1(b), ll1(a)),
                                  "o25": bootstrap_diff(llo(b), llo(a)), "btts": bootstrap_diff(llb(b), llb(a))}
    for d in data:
        a = [r for r in base_rows if r["div"] == d]
        b = [r for r in best_rows if r["div"] == d]
        res["by_league"][LEAGUES[d][0]] = {"name": LEAGUES[d][1], "n": len(a), "tuned_on": d in TUNING_DIVS,
                                           "x12_change": float(np.mean(ll1(b)) - np.mean(ll1(a))),
                                           "o25_change": float(np.mean(llo(b)) - np.mean(llo(a))),
                                           "btts_change": float(np.mean(llb(b)) - np.mean(llb(a)))}
    # Pre-registered rule: adopt only if O/U and BTTS both improve on test and 1X2 does not get worse.
    res["adopt"] = best > 0 and res["o25"]["mean"] < 0 and res["btts"]["mean"] < 0 and res["x12"]["mean"] <= 0
    verdict = "ADOPT" if res["adopt"] else "keep current"
    log(f"  shrink {best}: test log loss change 1X2 {res['x12']['mean']:+.4f} "
        f"(95% {res['x12']['lo']:+.4f} to {res['x12']['hi']:+.4f}), O2.5 {res['o25']['mean']:+.4f} "
        f"(95% {res['o25']['lo']:+.4f} to {res['o25']['hi']:+.4f}), BTTS {res['btts']['mean']:+.4f} "
        f"(95% {res['btts']['lo']:+.4f} to {res['btts']['hi']:+.4f}) -> {verdict}")
    log(f"  calibration error O2.5 {res['ece_before']['o25']:.4f} -> {res['ece_after']['o25']:.4f}, "
        f"BTTS {res['ece_before']['btts']:.4f} -> {res['ece_after']['btts']:.4f}, "
        f"1X2 {res['ece_before']['x12']:.4f} -> {res['ece_after']['x12']:.4f}")
    return res


def run_totals(out_dir: Path, log=print) -> dict:
    """Run the total-goals experiment once, store its result in accuracy.json and adopt or drop the
    pull in model_config.json. Re-run `backtest` afterwards so the headline figures include it."""
    data = {div: load_results(div) for div in LEAGUES}
    cfg = load_config()
    log("Testing a pull of expected total goals towards the league average…")
    res = totals_experiment(data, cfg, log)
    cfg.pop("total_shrink", None)
    if res["adopt"]:
        cfg["total_shrink"] = res["best"]
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    acc = out_dir / "accuracy.json"
    full = json.loads(acc.read_text(encoding="utf-8")) if acc.exists() else {}
    full["totals_test"] = res
    acc.write_text(json.dumps(full, indent=1))
    return res
