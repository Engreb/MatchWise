from datetime import date, datetime, timedelta, timezone

from matchwise import health

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def _sched(days, scored):
    ko = NOW + timedelta(days=days)
    return {"home": "A", "away": "B", "kickoff_utc": ko, "date": ko.date(), "hg": 1 if scored else None, "ag": 0 if scored else None}


def _meta(fixtures, through="2026-11-02"):
    return {"leagues": [{"key": "serieb", "name": "Serie B", "data_through": through}], "fixtures": fixtures}


def test_missing_fixtures_is_an_error(monkeypatch):
    monkeypatch.setattr(health, "load_schedule", lambda div, include_played=True: [_sched(1, False), _sched(2, False)])
    out = health.league_checks(_meta([]), NOW)
    assert [c["level"] for c in out] == ["error"] and "2 games" in out[0]["message"]


def test_results_lag_counts_scored_games_only(monkeypatch):
    postponed, played = _sched(-12, False), _sched(-6, True)
    monkeypatch.setattr(health, "load_schedule", lambda div, include_played=True: [postponed, played])
    out = health.league_checks(_meta([], through="2026-10-25"), NOW)
    assert len(out) == 1 and out[0]["area"] == "results" and out[0]["level"] == "warn" and "6 days" in out[0]["message"]


def test_stale_source_and_low_credits_warn():
    src = {"football-data results": "2026-11-06T05:00:00Z", "ESPN cups": "2026-11-02T05:00:00Z"}
    out = health.source_checks(NOW, src)
    assert len(out) == 1 and "ESPN cups" in out[0]["message"]
    assert health.odds_checks({"odds": {"credits_remaining": 10}})[0]["level"] == "error"
    assert health.odds_checks({"odds": {"credits_remaining": 400}}) == []


def test_drift_flags_only_a_clear_gap():
    acc = {"table": [{"key": "blend", "x12": {"log_loss": 0.999}}, {"key": "market", "x12": {"log_loss": 0.995}}]}
    row = lambda p: {"source": "saved", "date": "2026-11-01", "outcome": 0, "p": p, "mkt": [0.5, 0.3, 0.2]}
    same = health.drift([row([0.5, 0.3, 0.2])] * 200, acc, NOW)
    assert not same["flag"] and abs(same["gap"]) < 1e-9
    worse = health.drift([row([0.3, 0.3, 0.4]), row([0.32, 0.3, 0.38])] * 100, acc, NOW)
    assert worse["flag"]
