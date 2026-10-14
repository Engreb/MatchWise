"""Premier League team news (injuries, suspensions, doubts) from the official Fantasy
Premier League data. Shown as context only: it is not used by the prediction model yet.
Each update also archives the news so its predictive value can be tested later."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .data import ROOT, _fetch
from .teams import canonical

FPL_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
ARCHIVE_DIR = ROOT / "data" / "news"
STATUS = {"i": "injured", "s": "suspended", "d": "doubtful"}  # 'u'/'n' = left club or ineligible
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def build(known_teams: set[str], log=print) -> dict | None:
    try:
        b = json.loads(_fetch(FPL_URL))
    except Exception as e:
        log(f"  team news unavailable ({e})")
        return None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    team_names = {t["id"]: canonical(t["name"], known_teams) for t in b["teams"]}
    for t in b["teams"]:
        if team_names[t["id"]] is None:
            log(f"    ! unknown FPL team {t['name']!r}: add it to matchwise/teams.py")
    games = {}  # proxy for matches played: most starts by any player in the squad
    for p in b["elements"]:
        games[p["team"]] = max(games.get(p["team"], 0), p.get("starts") or 0)
    teams: dict[str, list] = {n: [] for n in team_names.values() if n}
    for p in b["elements"]:
        name = team_names.get(p["team"])
        if not name or p["status"] not in STATUS:
            continue
        starts = p.get("starts") or 0
        teams[name].append({
            "player": p["web_name"], "position": POSITIONS.get(p["element_type"], ""),
            "status": STATUS[p["status"]], "chance": p["chance_of_playing_next_round"],
            "news": p["news"], "since": p["news_added"],
            "starts": starts, "regular": games.get(p["team"], 0) > 0 and starts >= 0.5 * games[p["team"]],
        })
    for lst in teams.values():
        lst.sort(key=lambda x: (not x["regular"], x["status"] == "doubtful", -x["starts"]))
    out = {"fetched_at": now.isoformat().replace("+00:00", "Z"), "source": "Fantasy Premier League", "teams": teams}
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ARCHIVE_DIR / f"epl-{now:%Y-%m-%d}.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v) for v in teams.values())
    log(f"  Premier League team news: {n} players listed as injured, suspended or doubtful")
    return out


def write(out_dir: Path, known_teams: set[str], log=print) -> None:
    news = build(known_teams, log)
    if news:
        (out_dir / "news-epl.json").write_text(json.dumps(news, separators=(",", ":")), encoding="utf-8")
