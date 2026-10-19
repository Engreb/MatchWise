"""Does knowing who is missing improve the predictions? A one-off test on past seasons.

Historical injury and suspension lists come from API-Football (the free plan covers seasons
2022-23 to 2024-25; one request returns a whole league-season). For every match we count each
side's players listed as "Missing Fixture", relative to that team's own average so far that
season: a side that is always missing three players already has that in its results.

The adjustment tested is   home goals x exp(b * (away_extra - home_extra)),
                           away goals x exp(b * (home_extra - away_extra)),
with b fitted on 2022-23 and judged on 2023-24 and 2024-25 against the unadjusted model.
API team names are matched to football-data names by results (same date, same score), never by
spelling.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from .backtest import bootstrap_diff, is_over, ll_1x2, ll_bin, load_config, mix_for, replay
from .data import LEAGUES, RAW_DIR, ROOT, _fetch, load_results
from .model import prediction

API = "https://v3.football.api-sports.io/{path}"
LEAGUE_IDS = {"E0": 39, "SP1": 140, "I1": 135, "D1": 78, "F1": 61}
SEASONS = {"2223": 2022, "2324": 2023, "2425": 2024}
FIT_SEASON, TEST_SEASONS = "2223", ["2324", "2425"]
CACHE = RAW_DIR / "apifootball"
OUT = ROOT / "data" / "injury_test.json"


def api_key() -> str | None:
    if os.environ.get("API_FOOTBALL_KEY"):
        return os.environ["API_FOOTBALL_KEY"]
    env = ROOT / "secrets.env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("API_FOOTBALL_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def _get(path: str, key: str) -> dict:
    import urllib.request
    import urllib.error
    req = urllib.request.Request(API.format(path=path), headers={"x-apisports-key": key, "User-Agent": "matchwise-personal/0.1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(65)  # per-minute limit hit: wait for the window to reset
    if d.get("errors"):
        raise RuntimeError(f"API-Football: {d['errors']}")
    return d


def download(log=print) -> None:
    """Fixtures and injuries per league-season, cached (past seasons never change)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = None
    for div, lid in LEAGUE_IDS.items():
        for s, year in SEASONS.items():
            for kind in ("fixtures", "injuries"):
                path = CACHE / f"{kind}_{s}_{div}.json"
                if path.exists():
                    continue
                key = key or api_key()
                if not key:
                    raise SystemExit("API_FOOTBALL_KEY not set (engine/secrets.env)")
                time.sleep(7)  # free plan: at most 10 requests a minute
                d = _get(f"{kind}?league={lid}&season={year}", key)
                path.write_text(json.dumps(d["response"], separators=(",", ":")), encoding="utf-8")
                log(f"  {kind} {div} {s}: {d['results']} rows")


def team_map(div: str, season: str, matches) -> dict[int, str]:
    """API team id -> football-data name, by matching played fixtures on date and score."""
    fx = json.loads((CACHE / f"fixtures_{season}_{div}.json").read_text(encoding="utf-8"))
    by_key = defaultdict(list)
    for m in matches:
        if m.season == season and m.played:
            by_key[(m.date, m.hg, m.ag)].append(m)
    votes = defaultdict(lambda: defaultdict(int))
    for f in fx:
        g = f["goals"]
        if g["home"] is None:
            continue
        d = datetime.fromisoformat(f["fixture"]["date"]).date()
        for dd in (d, date.fromordinal(d.toordinal() - 1), date.fromordinal(d.toordinal() + 1)):
            for m in by_key.get((dd, g["home"], g["away"]), []):
                votes[f["teams"]["home"]["id"]][m.home] += 1
                votes[f["teams"]["away"]["id"]][m.away] += 1
    # A team's true name wins nearly all of its ~19 home and ~19 away matches.
    return {tid: max(v, key=v.get) for tid, v in votes.items() if max(v.values()) >= 10}


def missing_counts(div: str, season: str, matches) -> dict[tuple, tuple[int, int]]:
    """(date, home, away) -> number of players listed as missing for each side."""
    names = team_map(div, season, matches)
    fx = {f["fixture"]["id"]: f for f in json.loads((CACHE / f"fixtures_{season}_{div}.json").read_text(encoding="utf-8"))}
    count = defaultdict(int)
    for x in json.loads((CACHE / f"injuries_{season}_{div}.json").read_text(encoding="utf-8")):
        if x["player"]["type"] == "Missing Fixture":
            count[(x["fixture"]["id"], x["team"]["id"])] += 1
    played = {(m.date, m.home, m.away) for m in matches if m.season == season and m.played}
    out = {}
    for fid, f in fx.items():
        h, a = names.get(f["teams"]["home"]["id"]), names.get(f["teams"]["away"]["id"])
        if not h or not a:
            continue
        d = datetime.fromisoformat(f["fixture"]["date"]).date()
        for dd in (d, date.fromordinal(d.toordinal() - 1), date.fromordinal(d.toordinal() + 1)):
            if (dd, h, a) in played:
                out[(dd, h, a)] = (count[(fid, f["teams"]["home"]["id"])], count[(fid, f["teams"]["away"]["id"])])
                break
    return out


def collect(log=print) -> list[dict]:
    cfg = load_config()
    rows = []
    for div in LEAGUE_IDS:
        ms = load_results(div)
        for season in SEASONS:
            miss = missing_counts(div, season, ms)
            seen = defaultdict(list)  # team -> missing counts in its earlier matches this season
            n0 = len(rows)
            for m, p, _, _ in replay(ms, season, cfg["xi"], cfg["ridge"], mix=mix_for(cfg, div)):
                c = miss.get((m.date, m.home, m.away))
                if c is None:
                    continue
                extra = []
                for team, k in ((m.home, c[0]), (m.away, c[1])):
                    prev = seen[team]
                    extra.append(k - (np.mean(prev) if prev else k))
                    prev.append(k)
                rows.append({"div": div, "season": season, "hg": m.hg, "ag": m.ag,
                             "outcome": 0 if m.hg > m.ag else 1 if m.hg == m.ag else 2,
                             "lam": p.lam, "mu": p.mu, "rho": p.rho, "xh": extra[0], "xa": extra[1],
                             "mh": c[0], "ma": c[1]})
            log(f"  {LEAGUES[div][1]} {season}: {len(rows) - n0} matches with injury lists")
    return rows


def adjusted(r, b):
    lam = r["lam"] * np.exp(b * (r["xa"] - r["xh"]))
    mu = r["mu"] * np.exp(b * (r["xh"] - r["xa"]))
    return prediction(lam, mu, r["rho"])


def score_ll(rows, b):
    out = 0.0
    for r in rows:
        g = adjusted(r, b).grid
        out -= np.log(max(g[min(r["hg"], g.shape[0] - 1), min(r["ag"], g.shape[1] - 1)], 1e-12))
    return out / len(rows)


def run(app_data: Path | None = None, log=print) -> dict:
    download(log)
    rows = collect(log)
    fit_rows = [r for r in rows if r["season"] == FIT_SEASON]
    test = [r for r in rows if r["season"] in TEST_SEASONS]
    b = float(minimize_scalar(lambda v: score_ll(fit_rows, v), bounds=(-0.2, 0.2), method="bounded").x)
    base = [prediction(r["lam"], r["mu"], r["rho"]) for r in test]
    adj = [adjusted(r, b) for r in test]
    l1 = lambda ps: [ll_1x2([p.home, p.draw, p.away], r["outcome"]) for p, r in zip(ps, test)]
    lo = lambda ps: [ll_bin(p.over(2.5), is_over(r)) for p, r in zip(ps, test)]
    big = [i for i, r in enumerate(test) if abs(r["xh"] - r["xa"]) >= 2]
    res = {
        "source": "API-Football injuries (players listed as missing), relative to each team's season average",
        "fit_season": "2022–23", "test_seasons": ["2023–24", "2024–25"], "leagues": [LEAGUES[d][1] for d in LEAGUE_IDS],
        "b": b, "goal_effect_pct_per_player": (np.exp(b) - 1) * 100,
        "n_fit": len(fit_rows), "n_test": len(test),
        "avg_missing": float(np.mean([r["mh"] + r["ma"] for r in rows]) / 2),
        "x12": bootstrap_diff(l1(adj), l1(base)), "o25": bootstrap_diff(lo(adj), lo(base)),
        "big_gap_matches": len(big),
        "x12_big_gap": bootstrap_diff([l1(adj)[i] for i in big], [l1(base)[i] for i in big]) if big else None,
    }
    res["adopt"] = res["x12"]["hi"] < 0
    OUT.write_text(json.dumps(res, indent=1))
    acc = app_data / "accuracy.json" if app_data else None
    if acc and acc.exists():  # shown on the Model accuracy page
        a = json.loads(acc.read_text(encoding="utf-8"))
        a["injury_test"] = res
        acc.write_text(json.dumps(a, indent=1), encoding="utf-8")
    log(f"  b = {b:+.4f} ({res['goal_effect_pct_per_player']:+.1f}% goals per extra missing player)")
    log(f"  test 1X2 log loss change {res['x12']['mean']:+.4f} (95% {res['x12']['lo']:+.4f} to {res['x12']['hi']:+.4f}), "
        f"O2.5 {res['o25']['mean']:+.4f}; matches with a 2+ player gap: {len(big)}"
        + (f", change there {res['x12_big_gap']['mean']:+.4f}" if big else ""))
    log("  -> " + ("small improvement on past seasons (the lists may include late call-offs not known before kick-off)"
               if res["adopt"] else "no reliable improvement: keep it as context only"))
    return res
