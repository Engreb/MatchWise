import pytest

from matchwise.odds_api import Budget, summarise

EVENT = {  # shape of a The Odds API /odds response item (test fixture)
    "home_team": "Everton", "away_team": "Chelsea", "commence_time": "2026-10-17T11:30:00Z",
    "bookmakers": [
        {"key": "skybet", "last_update": "2026-10-16T09:00:00Z", "markets": [
            {"key": "h2h", "outcomes": [{"name": "Everton", "price": 3.0}, {"name": "Chelsea", "price": 2.3}, {"name": "Draw", "price": 3.4}]},
            {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5}, {"name": "Under", "price": 1.95, "point": 2.5}]}]},
        {"key": "coral", "last_update": "2026-10-16T10:00:00Z", "markets": [
            {"key": "h2h", "outcomes": [{"name": "Everton", "price": 3.2}, {"name": "Chelsea", "price": 2.25}, {"name": "Draw", "price": 3.3}]},
            {"key": "totals", "outcomes": [{"name": "Over", "price": 2.6, "point": 3.5}, {"name": "Under", "price": 1.5, "point": 3.5}]}]},
    ],
}


def test_summarise_averages_and_keeps_named_books():
    s = summarise(EVENT)
    assert s["odds_avg"] == pytest.approx([3.1, 3.35, 2.275])
    assert sum(s["market"]) == pytest.approx(1.0)
    assert s["market"][2] > s["market"][0]  # Chelsea favoured
    assert s["books"]["skybet"] == [3.0, 3.4, 2.3] and s["books"]["coral"] == [3.2, 3.3, 2.25]
    assert s["n_books"] == 2 and s["updated"] == "2026-10-16T10:00:00Z"
    # Only the 2.5 line counts for over/under; Coral's 3.5 line is ignored.
    assert s["market_o25"] == pytest.approx((1 / 1.9) / (1 / 1.9 + 1 / 1.95))


def test_event_without_match_odds_is_skipped():
    assert summarise({"home_team": "A", "away_team": "B", "bookmakers": []}) is None


def test_budget_guard():
    b = Budget()
    assert b.ok
    b.remaining = 5
    assert not b.ok
