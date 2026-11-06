from datetime import date, datetime, timezone

from matchwise import data
from matchwise.data import Match


def test_espn_names_matched_by_results(monkeypatch):
    fd = [Match("D2", data.CURRENT_SEASON, date(2026, 8, d), None, h, a, hg, ag)
          for d, h, a, hg, ag in [(1, "Furth", "Dresden", 2, 1), (8, "Dresden", "Kiel", 0, 0),
                                  (15, "Kiel", "Furth", 3, 1), (22, "Dresden", "Furth", 1, 2)]]
    monkeypatch.setattr(data, "load_results", lambda div: fd)
    ko = lambda d: datetime(2026, 8, d, 13, 0, tzinfo=timezone.utc)
    rows = [{"home": "SpVgg Greuther Fürth", "away": "Dynamo Dresden", "ko": ko(1), "hg": 2, "ag": 1},
            {"home": "Dynamo Dresden", "away": "Holstein Kiel", "ko": ko(8), "hg": 0, "ag": 0},
            {"home": "Holstein Kiel", "away": "SpVgg Greuther Fürth", "ko": ko(15), "hg": 3, "ag": 1},
            {"home": "Dynamo Dresden", "away": "SpVgg Greuther Fürth", "ko": ko(22), "hg": 1, "ag": 2},
            {"home": "Holstein Kiel", "away": "Dynamo Dresden", "ko": ko(29), "hg": None, "ag": None}]
    m = data.espn_team_map("D2", rows)
    assert m["SpVgg Greuther Fürth"] == "Furth" and m["Dynamo Dresden"] == "Dresden"
    assert "Holstein Kiel" not in m  # only 2 matched games: below the 3-vote threshold, left unmapped
