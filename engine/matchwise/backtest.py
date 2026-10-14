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

from .data import LEAGUES, ROOT, SEASONS, Match, load_results
from .blend import blended_prediction, tune_weights
from .model import DCModel, fit, prediction, promoted_priors

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


def preseason_priors(matches, season, xi, ridge, extra_teams=()):
    """Teams in the league this season, rating priors for promoted sides, and the
    low-score correction rho estimated from goals before the season."""
    i = SEASONS.index(season)
    teams = season_teams(matches, season) | set(extra_teams)
    in_season = [m.date for m in matches if m.season == season]
    if i == 0 or not in_season:
        return sorted(teams), {}, None
    prev = season_teams(matches, SEASONS[i - 1])
    base = fit(matches, min(in_season), xi, ridge)
    return sorted(teams), promoted_priors(base, sorted(prev - teams), sorted(teams - prev)), base.rho


def shot_mixed(matches, alpha, cutoff):
    """Replace each result's goals with alpha*goals + (1-alpha)*k*shots_on_target, where k is
    the league's goals per shot on target before `cutoff`. Only used for fitting ratings;
    predictions are always scored against real goals."""
    if alpha >= 1:
        return matches
    prior = [m for m in matches if m.played and m.hst is not None and m.date < cutoff]
    k = sum(m.hg + m.ag for m in prior) / max(1, sum(m.hst + m.ast for m in prior))
    return [replace(m, hg=alpha * m.hg + (1 - alpha) * k * m.hst, ag=alpha * m.ag + (1 - alpha) * k * m.ast)
            if m.played and m.hst is not None else m for m in matches]


def fit_current(matches, cutoff, cfg, teams, priors):
    """Fit with the configured goals/shots mix. Goal rates come from the mix; the low-score
    correction comes from actual goals (it describes scorelines, not chance creation)."""
    alpha = cfg.get("alpha", 1.0)
    if alpha >= 1:
        return fit(matches, cutoff, cfg["xi"], cfg["ridge"], teams=teams, priors=priors)
    m = fit(shot_mixed(matches, alpha, cutoff), cutoff, cfg["xi"], cfg["ridge"], teams=teams, priors=priors, fix_rho=True)
    m.rho = fit(matches, cutoff, cfg["xi"], cfg["ridge"], teams=teams, priors=priors).rho
    return m


def _baseline(matches, cutoff):
    recent = [m for m in matches if m.played and m.date < cutoff and (cutoff - m.date).days <= 365]
    n = len(recent)
    h = sum(m.hg > m.ag for m in recent) / n
    d = sum(m.hg == m.ag for m in recent) / n
    o25 = sum(m.hg + m.ag > 2.5 for m in recent) / n
    btts = sum(m.hg > 0 and m.ag > 0 for m in recent) / n
    return (h, d, 1 - h - d), o25, btts


def replay(matches, season, xi, ridge, *, alpha=1.0, fix_rho=False, with_baseline=False, extra_teams=()):
    """Yield (match, prediction, model, baseline) for every played match in `season`."""
    teams, priors, rho = preseason_priors(matches, season, xi, ridge, extra_teams)
    played = [m for m in matches if m.season == season and m.played]
    # Goals-per-shot ratio from before the season starts, so no in-season information leaks.
    mixed = shot_mixed(matches, alpha, played[0].date) if played else matches
    i, model = 0, None
    while i < len(played):
        start = played[i].date
        if alpha < 1:
            model = fit(mixed, start, xi, ridge, teams=teams, priors=priors, fix_rho=True, init=model)
            model.rho = 0.0 if fix_rho else rho
        else:
            model = fit(matches, start, xi, ridge, teams=teams, priors=priors, fix_rho=fix_rho, init=model)
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
    for div, matches in data.items():
        for season in TEST:
            log(f"  test replay {div} {season}")
            dc_rows += [record(m, p, b) for m, p, _, b in
                        replay(matches, season, cfg["xi"], cfg["ridge"], alpha=cfg["alpha"], with_baseline=True)]
            pois_rows += [record(m, p) for m, p, _, _ in
                          replay(matches, season, cfg["xi"], cfg["ridge"], alpha=cfg["alpha"], fix_rho=True)]
            goal_rows += [record(m, p) for m, p, _, _ in replay(matches, season, g["xi"], g["ridge"])]
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
        ("dc", "Model only" + (" (goals + shots on target)" if cfg["alpha"] < 1 else " (Dixon–Coles)"), "p", "o25", "btts"),
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
    cal_blend, ece_blend = calibration([(r["blend"][k], int(r["outcome"] == k)) for r in common for k in range(3)])

    by_league = []
    for div, (key, name) in LEAGUES.items():
        rows = [r for r in common if r["div"] == div]
        by_league.append({"key": key, "name": name, "dc": summarize_1x2(rows, "p"), "blend": summarize_1x2(rows, "blend"),
                          "market": summarize_1x2(rows, "mkt")})
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
        "calibration_blend": cal_blend, "ece_blend": ece_blend,
        "by_league": by_league, "by_season": by_season,
        "status": "validated" if validated else "research",
    }


def run(out_dir: Path, log=print) -> dict:
    t0 = time.time()
    data = {div: load_results(div) for div in LEAGUES}
    log("Tuning on validation season(s)…")
    cfg, tried, val_rows = tune(data, log)
    cfg["blend"] = tune_weights([r for r in val_rows], ll_1x2, ll_bin, is_over)
    log(f"Chosen: xi={cfg['xi']} ridge={cfg['ridge']} blend weights 1X2={cfg['blend']['w_1x2']} O2.5={cfg['blend']['w_o25']}")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    log("Evaluating on held-out test seasons…")
    res = evaluate(data, cfg, log)
    res["config"] = cfg
    res["configs_tried"] = tried
    res["block_days"] = BLOCK_DAYS
    res["runtime_s"] = round(time.time() - t0, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "accuracy.json").write_text(json.dumps(res, indent=1))
    log(f"Done in {res['runtime_s']}s. Status: {res['status']}")
    return res
