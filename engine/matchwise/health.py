"""Data health: is every source still feeding the app, and is the live record in line with testing?

Run at the end of every update (written to app/data/health.json for the app) and as
`python -m matchwise health --strict`, which exits with an error when a check fails, so the
GitHub run goes red and GitHub emails the owner.

Levels: "error" = something users can see is wrong (a league with games this week shows none,
results a long way behind); "warn" = worth a look (a source not updated for a couple of days,
team names that can't be matched, Odds API credits running low, live accuracy drifting).
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data import LEAGUES, RAW_DIR, load_schedule

SOURCES_PATH = RAW_DIR / "sources.json"
SOURCE_MAX_AGE_H = 48  # every source is refreshed daily
LAG_WARN_D, LAG_ERROR_D = 4, 10  # football-data results behind the schedule by this many days
CREDITS_WARN, CREDITS_ERROR = 60, 15
DRIFT_DAYS, DRIFT_MIN_N, DRIFT_MARGIN = 28, 150, 0.01


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def league_checks(meta: dict, now: datetime) -> list[dict]:
    out = []
    shown: dict[str, int] = {}
    unassessable: dict[str, set] = {}
    for f in meta["fixtures"]:
        if f.get("status") == "started" or f.get("cup"):
            continue
        ko = _dt(f["kickoff"]) if "T" in f["kickoff"] else None
        if ko and now < ko <= now + timedelta(days=7):
            shown[f["league"]] = shown.get(f["league"], 0) + 1
        if not f.get("assessable"):
            unassessable.setdefault(f["league"], set()).update({f["home"], f["away"]})
    div_of = {key: div for div, (key, _) in LEAGUES.items()}
    for lg in meta["leagues"]:
        key, name = lg["key"], lg["name"]
        div = div_of.get(key)
        sched = load_schedule(div, include_played=True) if div else []
        due = [s for s in sched if s["hg"] is None and now < s["kickoff_utc"] <= now + timedelta(days=7)]
        n_shown = shown.get(key, 0)
        if due and n_shown == 0:
            out.append({"level": "error", "area": "fixtures", "league": name,
                        "message": f"The schedule has {len(due)} games in the next 7 days, but none are shown."})
        elif due and n_shown < 0.8 * len(due):
            out.append({"level": "warn", "area": "fixtures", "league": name,
                        "message": f"Only {n_shown} of {len(due)} scheduled games in the next 7 days are shown."})
        if key in unassessable:
            out.append({"level": "warn", "area": "teams", "league": name,
                        "message": "Fixtures that can't be predicted (team name not recognised?): "
                                   + ", ".join(sorted(unassessable[key])[:6])})
        # Results lag: games the schedule source already has a score for, days ago, that
        # football-data hasn't published. (Games without a score are usually postponed.)
        through = datetime.fromisoformat(lg["data_through"]).date()
        missing = [s for s in sched if s["hg"] is not None and s["date"] > through
                   and s["kickoff_utc"] < now - timedelta(hours=72)]
        if missing:
            lag = (now - min(s["kickoff_utc"] for s in missing)).days
            if lag >= LAG_WARN_D:
                out.append({"level": "error" if lag >= LAG_ERROR_D else "warn", "area": "results", "league": name,
                            "message": f"football-data.co.uk results are {lag} days behind ({len(missing)} games missing since {through})."})
    return out


def source_checks(now: datetime, sources: dict | None = None) -> list[dict]:
    if sources is None:
        try:
            sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return [{"level": "warn", "area": "sources", "message": "No record of when the data sources last updated."}]
    out = []
    for name, when in sorted(sources.items()):
        age_h = (now - _dt(when)).total_seconds() / 3600
        if age_h > SOURCE_MAX_AGE_H:
            out.append({"level": "warn", "area": "sources",
                        "message": f"{name} last downloaded {age_h / 24:.1f} days ago."})
    return out


def odds_checks(meta: dict) -> list[dict]:
    left = (meta.get("odds") or {}).get("credits_remaining")
    if left is None:
        return []
    if left < CREDITS_WARN:
        return [{"level": "error" if left < CREDITS_ERROR else "warn", "area": "odds",
                 "message": f"Only {left} Odds API credits left this month; live odds will stop when they run out."}]
    return []


def drift(history: list[dict], accuracy: dict | None, now: datetime) -> dict | None:
    """Live log loss of what the app showed minus the bookmakers' closing odds, over the last
    DRIFT_DAYS, against the gap the backtest found. Flags when it is clearly worse."""
    since = (now - timedelta(days=DRIFT_DAYS)).date().isoformat()
    rows = [r for r in history if r.get("source") == "saved" and r.get("mkt") and r.get("p") and r["date"] >= since]
    if not rows:
        return None
    ll = lambda p, o: -math.log(max(p[o], 1e-12))
    d = [ll(r.get("pb") or r["p"], r["outcome"]) - ll(r["mkt"], r["outcome"]) for r in rows]
    n = len(d)
    mean = sum(d) / n
    se = (sum((x - mean) ** 2 for x in d) / (n - 1)) ** 0.5 / n ** 0.5 if n > 1 else float("inf")
    expected = None
    if accuracy:
        t = {x["key"]: x for x in accuracy.get("table", [])}
        if "blend" in t and "market" in t:
            expected = t["blend"]["x12"]["log_loss"] - t["market"]["x12"]["log_loss"]
    flag = bool(n >= DRIFT_MIN_N and expected is not None and mean - 1.96 * se > expected + DRIFT_MARGIN)
    return {"days": DRIFT_DAYS, "n": n, "gap": mean, "lo": mean - 1.96 * se, "hi": mean + 1.96 * se,
            "expected": expected, "flag": flag, "enough": n >= DRIFT_MIN_N}


def run(app_data: Path, now: datetime | None = None, log=print) -> dict:
    now = now or datetime.now(timezone.utc)
    read = lambda name: json.loads((app_data / name).read_text(encoding="utf-8")) if (app_data / name).exists() else None
    meta, hist, acc = read("fixtures.json"), read("history.json"), read("accuracy.json")
    checks = league_checks(meta, now) + source_checks(now) + odds_checks(meta)
    dr = drift(hist["matches"] if hist else [], acc, now)
    if dr and dr["flag"]:
        checks.append({"level": "warn", "area": "accuracy",
                       "message": f"Over the last {dr['days']} days the app's log loss is {dr['gap']:+.3f} against closing odds "
                                  f"(testing expected {dr['expected']:+.3f}). Worth checking for a broken source or a stale model."})
    level = "error" if any(c["level"] == "error" for c in checks) else "warn" if checks else "ok"
    out = {"generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"), "status": level,
           "checks": checks, "drift": dr}
    (app_data / "health.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    log(f"Health: {level}" + "".join(f"\n  [{c['level']}] {c.get('league', c['area'])}: {c['message']}" for c in checks))
    return out
