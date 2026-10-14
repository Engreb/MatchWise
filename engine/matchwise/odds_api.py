"""Near-kick-off bookmaker odds from The Odds API (UK bookmakers, incl. Sky Bet and Coral).

Budget: each league request costs 2 credits (h2h + totals markets, one region). Only leagues
with a fixture in the next ODDS_HOURS hours are requested, and requests stop when the
account's remaining credits fall below MIN_REMAINING. The key comes from the ODDS_API_KEY
environment variable (GitHub secret) or engine/secrets.env; it is never written anywhere.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .data import ROOT, implied  # importing data also applies the IPv4-first network fix

SPORT_KEYS = {"E0": "soccer_epl", "SP1": "soccer_spain_la_liga", "I1": "soccer_italy_serie_a",
              "D1": "soccer_germany_bundesliga", "F1": "soccer_france_ligue_one"}
BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
ODDS_HOURS = 72
MIN_REMAINING = 20
SHOW_BOOKS = {"skybet": "Sky Bet", "coral": "Coral"}
ARCHIVE_DIR = ROOT / "data" / "odds"


def api_key() -> str | None:
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if key:
        return key
    path = ROOT / "secrets.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("ODDS_API_KEY="):
                return line.split("=", 1)[1].strip() or None
    return None


class Budget:
    def __init__(self):
        self.remaining: int | None = None
        self.used: int | None = None
        self.calls = 0

    @property
    def ok(self) -> bool:
        return self.remaining is None or self.remaining >= MIN_REMAINING


def fetch(div: str, key: str, budget: Budget, log=print) -> list[dict] | None:
    if not budget.ok:
        log(f"    odds: skipped {div}, only {budget.remaining} credits left this month")
        return None
    q = urllib.parse.urlencode({"apiKey": key, "regions": "uk", "markets": "h2h,totals",
                                "oddsFormat": "decimal", "dateFormat": "iso"})
    try:
        with urllib.request.urlopen(f"{BASE.format(sport=SPORT_KEYS[div])}?{q}", timeout=30) as r:
            budget.remaining = int(r.headers.get("x-requests-remaining", budget.remaining or 0))
            budget.used = int(r.headers.get("x-requests-used", budget.used or 0))
            budget.calls += 1
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Never echo the request URL: it contains the key.
        log(f"    odds: {div} request failed (HTTP {e.code})")
    except Exception as e:
        log(f"    odds: {div} request failed ({type(e).__name__})")
    return None


def _avg(rows: list[list[float]]) -> list[float] | None:
    return [sum(c) / len(c) for c in zip(*rows)] if rows else None


def summarise(event: dict) -> dict | None:
    """Average UK bookmaker odds for one event, with Sky Bet and Coral kept separately."""
    home, away = event["home_team"], event["away_team"]
    h2h, over, books, updated = [], [], {}, None
    for b in event.get("bookmakers", []):
        for m in b.get("markets", []):
            if m["key"] == "h2h":
                price = {o["name"]: o["price"] for o in m["outcomes"]}
                if {home, away, "Draw"} <= price.keys():
                    trio = [price[home], price["Draw"], price[away]]
                    h2h.append(trio)
                    if b["key"] in SHOW_BOOKS:
                        books[b["key"]] = trio
                    lu = b.get("last_update") or m.get("last_update")
                    updated = max(updated or lu, lu) if lu else updated
            elif m["key"] == "totals":
                o = {x["name"]: x["price"] for x in m["outcomes"] if x.get("point") == 2.5}
                if {"Over", "Under"} <= o.keys():
                    over.append([o["Over"], o["Under"]])
    if not h2h:
        return None
    avg = _avg(h2h)
    ou = _avg(over)
    return {"odds_avg": [round(v, 3) for v in avg], "market": list(implied(tuple(avg))),
            "market_o25": implied(tuple(ou))[0] if ou else None,
            "books": {k: v for k, v in books.items()}, "n_books": len(h2h), "updated": updated}


def fixture_odds(div: str, known: set[str], key: str, budget: Budget, canonical, log=print) -> dict:
    """{(home, away): summary} for one league, with names mapped to football-data spelling."""
    events = fetch(div, key, budget, log)
    out = {}
    for ev in events or []:
        h, a = canonical(ev["home_team"], known), canonical(ev["away_team"], known)
        for raw, mapped in ((ev["home_team"], h), (ev["away_team"], a)):
            if mapped is None:
                log(f"    ! unknown odds team name {raw!r} in {div}: add it to matchwise/teams.py")
        s = summarise(ev)
        if h and a and s:
            out[(h, a)] = {**s, "commence": ev.get("commence_time")}
    if events is not None:
        log(f"    odds: {len(out)} {div} matches from {SPORT_KEYS[div]} (credits left: {budget.remaining})")
    return out


def archive(snap: dict, now: datetime) -> None:
    """Keep each run's processed odds so their value can be evaluated later."""
    if not snap:
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    rows = [{"div": d, "home": h, "away": a, **v} for (d, h, a), v in snap.items()]
    (ARCHIVE_DIR / f"{now:%Y-%m-%dT%H%M}.json").write_text(json.dumps(
        {"fetched_at": now.isoformat().replace("+00:00", "Z"), "matches": rows}, separators=(",", ":")), encoding="utf-8")
