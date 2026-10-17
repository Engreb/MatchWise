from datetime import date

from matchwise.pipeline import provisional_rows

SNAP = {"H": 0.5, "D": 0.25, "A": 0.25, "o25": 0.55, "btts": 0.5, "cutoff": "2026-10-13",
        "saved_at": "2026-10-16T10:24:57Z", "saves": 2, "bH": 0.48, "bD": 0.26, "bA": 0.26, "bo25": 0.52,
        "market": [0.48, 0.26, 0.26], "odds_source": "The Odds API"}
SCHED = [
    {"home": "Eintracht Frankfurt", "away": "1. FC Köln", "date": date(2026, 10, 16), "hg": 1, "ag": 0},
    {"home": "FC Bayern München", "away": "SC Paderborn 07", "date": date(2026, 10, 17), "hg": None, "ag": None},
]
TEAMS = ["Ein Frankfurt", "FC Koln", "Bayern Munich", "Paderborn"]


def test_saved_prediction_settles_provisionally_from_schedule_score():
    snaps = {("D1", "2026-10-16", "Ein Frankfurt", "FC Koln"): SNAP}
    rows = provisional_rows("D1", "bundesliga", TEAMS, set(), snaps, schedule=SCHED)
    assert len(rows) == 1
    r = rows[0]
    assert (r["home"], r["hg"], r["ag"], r["outcome"]) == ("Ein Frankfurt", 1, 0, 0)
    assert r["provisional"] and r["source"] == "saved" and r["pb"] == [0.48, 0.26, 0.26]


def test_no_saved_prediction_means_no_provisional_row():
    assert provisional_rows("D1", "bundesliga", TEAMS, set(), {}, schedule=SCHED) == []


def test_football_data_result_takes_precedence():
    snaps = {("D1", "2026-10-16", "Ein Frankfurt", "FC Koln"): SNAP}
    have = {(date(2026, 10, 16), "Ein Frankfurt", "FC Koln")}
    assert provisional_rows("D1", "bundesliga", TEAMS, have, snaps, schedule=SCHED) == []
