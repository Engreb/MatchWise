"""English domestic cups (FA Cup, EFL Cup): fixtures and results from ESPN, predictions from one
Dixon–Coles fit of the Premier League to League Two together.

Only ties between two teams in our English leagues that season are predicted; non-league sides
have no data and stay "unable to assess". The prediction is for the 90-minute result: a tie that
went to extra time or penalties counts as a draw. Extra time and penalties aren't modelled.

The joint fit puts all 92 teams on one scale (teams that moved between divisions link them) and
gives each division its own goal level; a tie between divisions uses the mean of the two levels.
Finals (and FA Cup semi-finals, at Wembley) are played without home advantage.
The settings are the leagues' own (`xi`, `ridge`); nothing was tuned on cup results.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from .data import RAW_DIR, SEASONS, UK, Match, _fetch, load_results
from .model import DCModel, Prediction, fit, prediction
from .teams import canonical

# app key -> (ESPN slug, display name)
CUPS = {"facup": ("eng.fa", "FA Cup"), "eflcup": ("eng.league_cup", "EFL Cup")}
DIVS = ["E0", "E1", "E2", "E3"]
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={year}&limit=1000"
NEUTRAL_ROUNDS = {"final", "finals"}
NEUTRAL_SEMIS = {"facup"}  # EFL Cup semi-finals are two-legged, at the clubs' grounds
ROUND_NAMES = {"preliminary-round": "Preliminary round", "first-round": "First round", "second-round": "Second round",
               "third-round": "Third round", "fourth-round": "Fourth round", "fifth-round": "Fifth round",
               "quarterfinals": "Quarter-finals", "semifinals": "Semi-finals", "final": "Final", "finals": "Final"}
FINISHED = {"STATUS_FULL_TIME", "STATUS_FINAL_AET", "STATUS_FINAL_PEN", "STATUS_FINAL_ET"}


@dataclass
class CupMatch:
    cup: str
    id: str
    season: str
    date: date  # UK date
    kickoff_utc: datetime
    home: str  # ESPN names
    away: str
    state: str  # "pre", "in" or "post"
    finished: bool
    round: str | None
    ft_h: int | None = None
    ft_a: int | None = None
    h90: int | None = None  # None when extra time was played and goal minutes are incomplete
    a90: int | None = None
    extra_time: bool = False  # went beyond 90 minutes (extra time and/or penalties)
    pens: tuple[int, int] | None = None

    @property
    def neutral(self) -> bool:
        return self.round in NEUTRAL_ROUNDS or (self.round == "semifinals" and self.cup in NEUTRAL_SEMIS)

    @property
    def outcome(self) -> int | None:
        """90-minute result: 0 home win, 1 draw, 2 away win."""
        if not self.finished:
            return None
        if self.extra_time:
            return 1
        return 0 if self.ft_h > self.ft_a else 1 if self.ft_h == self.ft_a else 2


def season_of(d: date) -> str:
    y = d.year - (1 if d.month < 7 else 0)
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def _minute(s: str | None) -> int | None:
    m = re.match(r"(\d+)'", s or "")
    return int(m.group(1)) if m else None


def parse_event(cup: str, e: dict) -> dict | None:
    """One ESPN event as a compact record (the form cached on disk)."""
    c = e["competitions"][0]
    side = {t["homeAway"]: t for t in c["competitors"]}
    if "home" not in side or "away" not in side:
        return None
    h, a = side["home"], side["away"]
    st = e["status"]["type"]
    r = {"id": e["id"], "date": e["date"], "home": h["team"]["displayName"], "away": a["team"]["displayName"],
         "state": st.get("state"), "status": st["name"], "round": (e.get("season") or {}).get("slug")}
    if st["name"] in FINISHED:
        r["ft"] = [int(h["score"]), int(a["score"])]
        r["et"] = st["name"] != "STATUS_FULL_TIME"
        if h.get("shootoutScore") is not None and a.get("shootoutScore") is not None:
            r["pens"] = [int(h["shootoutScore"]), int(a["shootoutScore"])]
        if r["et"]:
            # 90-minute score from goal minutes (stoppage time shows as 90'+n'), when they're complete.
            goals = [x for x in c.get("details", []) if x.get("scoringPlay") and not x.get("shootout")]
            ids = (h["team"]["id"], a["team"]["id"])
            if [sum(x.get("team", {}).get("id") == i for x in goals) for i in ids] == r["ft"]:
                mins = [(_minute(x.get("clock", {}).get("displayValue")), x["team"]["id"]) for x in goals]
                if all(m is not None for m, _ in mins):
                    r["s90"] = [sum(m <= 90 and t == i for m, t in mins) for i in ids]
    return r


def to_match(cup: str, r: dict) -> CupMatch:
    ko = datetime.fromisoformat(r["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
    d = ko.astimezone(UK).date()
    m = CupMatch(cup=cup, id=r["id"], season=season_of(d), date=d, kickoff_utc=ko, home=r["home"], away=r["away"],
                 state=r.get("state") or "pre", finished="ft" in r, round=r.get("round"))
    if m.finished:
        m.ft_h, m.ft_a = r["ft"]
        m.extra_time = r["et"]
        m.pens = tuple(r["pens"]) if r.get("pens") else None
        s90 = r["ft"] if not r["et"] else r.get("s90")
        if s90:
            m.h90, m.a90 = s90
    return m


def raw_path(cup: str, year: int) -> Path:
    return RAW_DIR / f"cup_{cup}_{year}.json"


def season_years(season: str) -> list[int]:
    return [2000 + int(season[:2]), 2000 + int(season[2:])]


def download(seasons: list[str], refresh: set[int] = frozenset(), log=print) -> None:
    """Fetch each cup's calendar years for `seasons` (cached; years in `refresh` are re-fetched).
    ESPN's API is unofficial: if it fails, the cached files are kept and the run carries on."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    years = sorted({y for s in seasons for y in season_years(s)})
    for cup, (slug, name) in CUPS.items():
        for y in years:
            path = raw_path(cup, y)
            if path.exists() and y not in refresh:
                continue
            try:
                d = json.loads(_fetch(SCOREBOARD_URL.format(slug=slug, year=y), timeout=30, attempts=2))
                rows = [r for r in (parse_event(cup, e) for e in d.get("events", [])) if r]
                path.write_text(json.dumps(rows, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
                log(f"  {name} {y}: {len(rows)} matches")
                from .data import mark_source
                mark_source("ESPN cups")
            except Exception as e:
                log(f"  {name} {y}: ESPN unavailable ({type(e).__name__}); using the saved copy if there is one")


def load(cup: str) -> list[CupMatch]:
    out = {}
    for path in sorted(RAW_DIR.glob(f"cup_{cup}_*.json")):
        for r in json.loads(path.read_text(encoding="utf-8")):
            out[r["id"]] = to_match(cup, r)  # later files win (an event can appear in two calendar years)
    return sorted(out.values(), key=lambda m: (m.kickoff_utc, m.home))


# ---------- model ----------
def league_matches() -> list[Match]:
    return sorted((m for d in DIVS for m in load_results(d)), key=lambda m: m.date)


def team_divisions(matches: list[Match], season: str) -> dict[str, str]:
    return {t: m.div for m in matches if m.season == season for t in (m.home, m.away)}


def season_setup(matches: list[Match], season: str, cfg: dict) -> tuple[list[str], dict]:
    """This season's 92 teams and rating priors: sides new to League Two (up from the National
    League, so with no data) start at the average of the sides that dropped out of it."""
    i = SEASONS.index(season)
    cur = team_divisions(matches, season)
    prev = team_divisions(matches, SEASONS[i - 1]) if i else {}
    new, gone = sorted(set(cur) - set(prev)), sorted(set(prev) - set(cur))
    if not new or not gone:
        return sorted(cur), {}
    start = min(m.date for m in matches if m.season == season)
    base = fit(matches, start, cfg["xi"], cfg["ridge"], divisions=DIVS)
    g = [t for t in gone if t in base.teams]
    a = float(np.mean([base.attack[base.index(t)] for t in g]))
    d = float(np.mean([base.defence[base.index(t)] for t in g]))
    return sorted(cur), {t: (a, d) for t in new}


def joint_fit(matches: list[Match], cutoff: date, cfg: dict, teams: list[str], priors: dict,
              init: DCModel | None = None) -> DCModel:
    """Premier League to League Two on one scale, from results strictly before `cutoff`."""
    return fit(matches, cutoff, cfg["xi"], cfg["ridge"], teams=teams, priors=priors, init=init, divisions=DIVS)


def division_levels(model: DCModel) -> dict[str, float]:
    n = len(model.teams)
    return dict(zip(DIVS, np.append(0.0, model.theta[1 + 2 * n:])))


def predict(model: DCModel, home: str, away: str, div_home: str, div_away: str, neutral: bool) -> Prediction:
    lv = division_levels(model)
    level = 0.5 * (lv[div_home] + lv[div_away])
    h, a = model.index(home), model.index(away)
    lam = math.exp(model.intercept + (0.0 if neutral else model.home_adv) + model.attack[h] + model.defence[a] + level)
    mu = math.exp(model.intercept + model.attack[a] + model.defence[h] + level)
    return prediction(lam, mu, model.rho)


# ---------- backtest ----------
BACKTEST_SEASONS = ["2122", "2223", "2324", "2425", "2526"]
TEST_SEASONS = ["2425", "2526"]
TIER = {d: i for i, d in enumerate(DIVS)}


def replay(matches: list[Match], cups: dict[str, list[CupMatch]], season: str, cfg: dict):
    """Yield (cup match, home, away, prediction, model, divisions) for every finished, rateable tie in `season`,
    each predicted from a fit on results strictly before its date."""
    divs = team_divisions(matches, season)
    teams, priors = season_setup(matches, season, cfg)
    known = set(divs)
    ties = []
    for cm in (m for ms in cups.values() for m in ms):
        if cm.season != season or not cm.finished:
            continue
        h, a = canonical(cm.home, known), canonical(cm.away, known)
        if h and a:
            ties.append((cm, h, a))
    ties.sort(key=lambda x: (x[0].date, x[0].home))
    model, day = None, None
    for cm, h, a in ties:
        if cm.date != day:
            day = cm.date
            model = joint_fit(matches, day, cfg, teams, priors, init=model)
        assert model.cutoff <= cm.date, "leakage: model fitted on or after match date"
        yield cm, h, a, predict(model, h, a, divs[h], divs[a], cm.neutral), model, (divs[h], divs[a])


def backtest(cfg: dict, log=print) -> dict:
    """Cup ties 2021-22 to 2025-26 against two baselines: earlier cup results' home/draw/away
    frequencies (naive), and the same split by division gap (does the model add anything beyond
    "the higher-league side usually wins"?)."""
    from .backtest import bootstrap_diff, ll_1x2
    matches = league_matches()
    cups = {c: load(c) for c in CUPS}
    rows = []
    for season in BACKTEST_SEASONS:
        for cm, h, a, p, _, (dh, da) in replay(matches, cups, season, cfg):
            rows.append({"cup": cm.cup, "season": season, "date": cm.date, "home": h, "away": a, "neutral": cm.neutral,
                         "gap": TIER[da] - TIER[dh], "outcome": cm.outcome, "p": [p.home, p.draw, p.away]})
        log(f"  cups {season}: {sum(r['season'] == season for r in rows)} ties")
    every = sorted((m.date, m.outcome) for ms in cups.values() for m in ms if m.finished)
    for r in rows:
        cnt = np.bincount([o for d, o in every if d < r["date"]], minlength=3) + 1.0
        r["base"] = list(cnt / cnt.sum())
    for r in rows:
        same = [x["outcome"] for x in rows if x["date"] < r["date"] and x["gap"] == r["gap"] and x["neutral"] == r["neutral"]]
        cnt = np.bincount(same, minlength=3) + 10 * np.array(r["base"])  # shrunk to naive with 10 pseudo-ties
        r["tier"] = list(cnt / cnt.sum())

    def block(rs):
        ll = lambda k: [ll_1x2(r[k], r["outcome"]) for r in rs]
        return {"n": len(rs), "log_loss": {k: float(np.mean(ll(k))) for k in ("p", "base", "tier")},
                "accuracy": float(np.mean([int(np.argmax(r["p"])) == r["outcome"] for r in rs])),
                "vs_base": bootstrap_diff(ll("p"), ll("base")), "vs_tier": bootstrap_diff(ll("p"), ll("tier"))}

    test = [r for r in rows if r["season"] in TEST_SEASONS]
    res = {"seasons": BACKTEST_SEASONS, "test_seasons": TEST_SEASONS, "all": block(rows), "test": block(test),
           "cross_division": block([r for r in rows if r["gap"]]), "same_division": block([r for r in rows if not r["gap"]]),
           "by_cup": {c: block([r for r in rows if r["cup"] == c]) for c in CUPS},
           "by_season": {s: block([r for r in rows if r["season"] == s]) for s in BACKTEST_SEASONS}}
    # Calibration by division gap (positive: the home side is in the higher division).
    res["by_gap"] = []
    for g in sorted({r["gap"] for r in rows}):
        rs = [r for r in rows if r["gap"] == g]
        res["by_gap"].append({"gap": g, "n": len(rs), "predicted": [float(v) for v in np.mean([r["p"] for r in rs], axis=0)],
                              "observed": [float(v) for v in np.bincount([r["outcome"] for r in rs], minlength=3) / len(rs)]})
    t = res["test"]
    log(f"  cups test {'+'.join(TEST_SEASONS)}: n={t['n']} log loss {t['log_loss']['p']:.4f} "
        f"(naive {t['log_loss']['base']:.4f}, division gap {t['log_loss']['tier']:.4f}); "
        f"vs naive {t['vs_base']['mean']:+.4f} [{t['vs_base']['lo']:+.4f}, {t['vs_base']['hi']:+.4f}], "
        f"vs division gap {t['vs_tier']['mean']:+.4f} [{t['vs_tier']['lo']:+.4f}, {t['vs_tier']['hi']:+.4f}]")
    return res


def run_backtest(out_dir: Path, cfg: dict, log=print) -> dict:
    """Download past cup seasons (once), run the backtest and store it in accuracy.json."""
    download(BACKTEST_SEASONS, log=log)
    res = backtest(cfg, log)
    acc = out_dir / "accuracy.json"
    full = json.loads(acc.read_text(encoding="utf-8")) if acc.exists() else {}
    full["cup_test"] = res
    acc.write_text(json.dumps(full, indent=1))
    return res
