from datetime import date

import pytest

from matchwise.data import Match
from matchwise.projections import project, standings


def _m(h, a, hg, ag):
    return Match("E0", "2627", date(2026, 8, 20), None, h, a, hg, ag)


def test_standings_points_and_goals():
    t = standings([_m("A", "B", 2, 0), _m("B", "C", 1, 1)], ["A", "B", "C"])
    assert (t["A"]["pts"], t["B"]["pts"], t["C"]["pts"]) == (3, 1, 1)
    assert t["B"]["gf"] == 1 and t["B"]["ga"] == 3


def test_projection_probabilities_are_consistent():
    teams = [f"T{i}" for i in range(20)]
    rem = [(h, a) for h in teams for a in teams if h != a][:200]
    out = project("E0", [], rem, teams, lambda h, a: (1.5, 1.1) if h == "T0" else (1.3, 1.2))
    rows = out["rows"]
    assert sum(r["title"] for r in rows) == pytest.approx(1.0, abs=1e-9)
    assert sum(r["top"] for r in rows) == pytest.approx(4.0, abs=1e-9)
    assert sum(r["rel"] for r in rows) == pytest.approx(3.0, abs=1e-9)
    assert max(rows, key=lambda r: r["title"])["team"] == "T0"


def test_completed_season_is_certain():
    res = [_m("A", "B", 3, 0), _m("B", "A", 0, 1)]
    out = project("SC0", res, [], ["A", "B"], lambda h, a: (1.0, 1.0))
    a = next(r for r in out["rows"] if r["team"] == "A")
    assert a["title"] == 1.0 and a["xpts"] == 6


def test_position_distribution_sums_to_one():
    teams = [f"T{i}" for i in range(6)]
    rem = [(h, a) for h in teams for a in teams if h != a]
    rows = project("SC0", [], rem, teams, lambda h, a: (1.4, 1.1))["rows"]
    for r in rows:
        assert sum(r["dist"]) == pytest.approx(1.0, abs=0.01) and len(r["dist"]) == 6
