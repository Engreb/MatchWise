"""Fit current models and write the JSON files the app reads."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .backtest import fit_current, load_config, preseason_priors, record, replay, summarize_1x2
from .blend import blended_prediction
from .data import CURRENT_SEASON, LEAGUES, ROOT, Match, load_fixtures, load_results, load_schedule
from .model import DCModel, fit
from . import news
from .teams import canonical

SNAPSHOT_DIR = ROOT / "data" / "snapshots"
MODEL_VERSION = "dc-0.1"
LIMITED_WEIGHT = 8.0  # effective (time-weighted) matches below which a rating is flagged
GRID_N = 6
FIXTURE_DAYS = 10
R = 4  # decimal places in output


def _r(v):
    return round(float(v), R)


def pair_payload(model: DCModel, home: str, away: str) -> list:
    return payload(model.predict(home, away))


def payload(p) -> list:
    g = p.grid[:GRID_N, :GRID_N]
    return [_r(p.lam), _r(p.mu), _r(p.home), _r(p.draw), _r(p.away),
            *[_r(p.over(l)) for l in (0.5, 1.5, 2.5, 3.5, 4.5)], _r(p.btts),
            *[_r(v) for v in g.flatten()]]


PAIR_FIELDS = ["lam", "mu", "H", "D", "A", "o05", "o15", "o25", "o35", "o45", "btts", f"grid{GRID_N}x{GRID_N}"]


def team_table(model: DCModel, teams: list[str]) -> list[dict]:
    rows = []
    for t in teams:
        i = model.index(t)
        rows.append({"name": t, "attack": _r(model.attack[i]), "defence": _r(model.defence[i]),
                     "weight": round(model.team_weight.get(t, 0.0), 1),
                     "limited": bool(model.team_weight.get(t, 0.0) < LIMITED_WEIGHT),
                     "promoted_prior": t in model.prior_teams})
    by_att = sorted(rows, key=lambda r: -r["attack"])
    by_def = sorted(rows, key=lambda r: r["defence"])
    for r in rows:
        r["rank_attack"] = by_att.index(r) + 1
        r["rank_defence"] = by_def.index(r) + 1
    # Overall strength = expected goal difference against an average side on neutral ground.
    for r in rows:
        r["strength"] = _r(np.exp(model.intercept + r["attack"]) - np.exp(model.intercept + r["defence"]))
    return sorted(rows, key=lambda r: -r["strength"])


def _iso(dt: datetime | None, d: date) -> str:
    return dt.isoformat().replace("+00:00", "Z") if dt else d.isoformat()


def _snapshot_index() -> dict:
    """Latest saved pre-kick-off prediction per fixture key."""
    idx = {}
    if not SNAPSHOT_DIR.exists():
        return idx
    for f in sorted(SNAPSHOT_DIR.glob("*.json")):
        snap = json.loads(f.read_text())
        for fx in snap["fixtures"]:
            ko = fx.get("kickoff")
            if ko and snap["created"] >= ko:  # only predictions saved before kick-off count
                continue
            idx[(fx["div"], fx["date"], fx["home"], fx["away"])] = {**fx, "saved_at": snap["created"]}
    return idx


def upcoming_fixtures(div: str, teams: list[str], odds_rows: list[Match], now: datetime, log=print) -> list[dict]:
    """Matches not yet kicked off in the next FIXTURE_DAYS days (or the league's next round if
    none fall in that window), from the full schedule, with odds attached where published."""
    known = set(teams)
    odds = {(m.home, m.away): m for m in odds_rows}
    sched = [s for s in load_schedule(div) if s["kickoff_utc"] > now]
    if sched:
        end = max(now + timedelta(days=FIXTURE_DAYS), sched[0]["kickoff_utc"] + timedelta(days=3))
        sched = [s for s in sched if s["kickoff_utc"] <= end]
    out, seen = [], set()
    for s in sched:
        h, a = canonical(s["home"], known), canonical(s["away"], known)
        for raw, mapped in ((s["home"], h), (s["away"], a)):
            if mapped is None:
                log(f"    ! unknown team name {raw!r} in {div} schedule: add it to matchwise/teams.py")
        f = {**s, "home": h or s["home"], "away": a or s["away"]}
        f["odds"] = odds.get((f["home"], f["away"]))
        seen.add((f["home"], f["away"]))
        out.append(f)
    # Fall back to football-data's own fixture list for anything the schedule lacks.
    for m in odds_rows:
        if (m.home, m.away) not in seen and (m.kickoff_utc is None or m.kickoff_utc > now):
            out.append({"home": m.home, "away": m.away, "kickoff_utc": m.kickoff_utc, "date": m.date, "odds": m})
    return out


def run(out_dir: Path, log=print, offline: bool = False) -> dict:
    cfg = load_config()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    out_dir.mkdir(parents=True, exist_ok=True)
    fixtures = load_fixtures()
    snaps = _snapshot_index()
    leagues_meta, fixture_rows, history_rows, snapshot_rows = [], [], [], []
    epl_teams: set[str] = set()

    for div, (key, name) in LEAGUES.items():
        matches = load_results(div)
        played = [m for m in matches if m.played]
        cur = [m for m in played if m.season == CURRENT_SEASON]
        fx = [f for f in fixtures if f.div == div]
        last = max(m.date for m in played)
        cutoff = last + timedelta(days=1)
        teams, priors, _ = preseason_priors(matches, CURRENT_SEASON, cfg["xi"], cfg["ridge"],
                                         extra_teams={t for f in fx for t in (f.home, f.away)})
        model = fit_current(matches, cutoff, cfg, teams, priors)
        log(f"  {name}: {model.n_matches} matches to {last}, {len(teams)} teams, converged={model.converged}")

        pairs = {f"{h}|{a}": pair_payload(model, h, a) for h in teams for a in teams if h != a}
        table = team_table(model, teams)
        (out_dir / f"league-{key}.json").write_text(json.dumps({
            "key": key, "name": name, "season": CURRENT_SEASON, "data_through": last.isoformat(),
            "model": {"version": MODEL_VERSION, "cutoff": cutoff.isoformat(), "n_matches": model.n_matches,
                      "home_adv": _r(model.home_adv), "home_effect_pct": round((np.exp(model.home_adv) - 1) * 100),
                      "intercept": _r(model.intercept), "rho": _r(model.rho), **cfg},
            "teams": table, "pair_fields": PAIR_FIELDS, "pairs": pairs,
        }, separators=(",", ":")))
        if key == "epl":
            epl_teams = set(teams)
        leagues_meta.append({"key": key, "name": name, "data_through": last.isoformat(),
                             "matches_this_season": len(cur), "teams": len(teams)})

        for f in upcoming_fixtures(div, teams, fx, now, log):
            ok = f["home"] in teams and f["away"] in teams
            odds = f["odds"]
            row = {"league": key, "div": div, "date": f["date"].isoformat(), "kickoff": _iso(f["kickoff_utc"], f["date"]),
                   "round": f.get("round"), "home": f["home"], "away": f["away"], "assessable": ok,
                   "market": [_r(v) for v in odds.market_open] if odds and odds.market_open else None,
                   "odds_avg": list(odds.odds_avg) if odds and odds.odds_avg else None,
                   "odds_skybet": list(odds.odds_skybet) if odds and odds.odds_skybet else None,
                   "blend": None}
            if ok and row["market"] and cfg.get("blend"):
                b = blended_prediction(model.predict(f["home"], f["away"]), odds.market_open, odds.market_o25_open, cfg["blend"])
                row["blend"] = payload(b)
            fixture_rows.append(row)
            if ok:
                pr = pair_payload(model, f["home"], f["away"])
                snapshot_rows.append({"div": div, "date": row["date"], "kickoff": row["kickoff"], "home": f["home"],
                                      "away": f["away"], "H": pr[2], "D": pr[3], "A": pr[4], "o25": pr[7],
                                      "btts": pr[10], "lam": pr[0], "mu": pr[1],
                                      "model": MODEL_VERSION, "cutoff": cutoff.isoformat()})

        # This season so far: replayed with data available before each match, or the
        # prediction actually saved before kick-off when one exists.
        for m, p, mdl, _ in replay(matches, CURRENT_SEASON, cfg["xi"], cfg["ridge"], alpha=cfg.get("alpha", 1.0)):
            r = record(m, p)
            s = snaps.get((div, r["date"], m.home, m.away))
            history_rows.append({
                "league": key, "date": r["date"], "home": m.home, "away": m.away, "hg": m.hg, "ag": m.ag,
                "outcome": r["outcome"], "p": [_r(v) for v in ([s["H"], s["D"], s["A"]] if s else r["p"])],
                "o25": _r(s["o25"] if s else r["o25"]), "btts": _r(s["btts"] if s else r["btts"]),
                "mkt": [_r(v) for v in r["mkt"]] if r["mkt"] else None,
                "source": "saved" if s else "replay", "cutoff": s["cutoff"] if s else mdl.cutoff.isoformat(),
            })

    if snapshot_rows:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        (SNAPSHOT_DIR / f"{now:%Y-%m-%d}.json").write_text(json.dumps(
            {"created": now.isoformat().replace("+00:00", "Z"), "fixtures": snapshot_rows}, indent=1))

    if not offline:
        news.write(out_dir, epl_teams, log)
    fixture_rows.sort(key=lambda r: (r["kickoff"], r["league"], r["home"]))
    history_rows.sort(key=lambda r: (r["date"], r["home"]), reverse=True)
    common = [r for r in history_rows if r["mkt"]]
    summary = {"model": summarize_1x2(history_rows, "p"), "model_common": summarize_1x2(common, "p"),
               "market_common": summarize_1x2(common, "mkt")}
    (out_dir / "history.json").write_text(json.dumps({"season": CURRENT_SEASON, "summary": summary,
                                                       "matches": history_rows}, separators=(",", ":")))
    acc_path = out_dir / "accuracy.json"
    status = json.loads(acc_path.read_text())["status"] if acc_path.exists() else "unvalidated"
    meta = {"generated_at": now.isoformat().replace("+00:00", "Z"), "model_version": MODEL_VERSION,
            "config": cfg, "status": status, "leagues": leagues_meta,
            "source": "football-data.co.uk"}
    (out_dir / "fixtures.json").write_text(json.dumps({**meta, "fixtures": fixture_rows}, indent=1))
    log(f"Wrote {len(fixture_rows)} fixtures, {len(history_rows)} history rows. Status: {status}")
    return meta
