from datetime import date

import numpy as np

from matchwise import cups
from matchwise.model import DCModel
from matchwise.pipeline import cup_note
from matchwise.teams import canonical


def _event(status, hs, as_, goals=(), shootout=None, slug="third-round"):
    side = lambda ha, tid, name, score, so: {"homeAway": ha, "team": {"id": tid, "displayName": name}, "score": str(score),
                                             **({"shootoutScore": so} if so is not None else {})}
    so = shootout or (None, None)
    return {"id": "1", "date": "2026-01-10T15:00Z", "season": {"slug": slug},
            "status": {"type": {"name": status, "state": "post"}},
            "competitions": [{"competitors": [side("home", "10", "Leeds United", hs, so[0]), side("away", "20", "Hull City", as_, so[1])],
                              "details": [{"scoringPlay": True, "team": {"id": t}, "clock": {"displayValue": c}} for t, c in goals]}]}


def test_ninety_minute_score_from_goal_minutes():
    e = _event("STATUS_FINAL_AET", 2, 1, goals=[("10", "30'"), ("20", "90'+4'"), ("10", "105'")])
    m = cups.to_match("facup", cups.parse_event("facup", e))
    assert (m.ft_h, m.ft_a, m.h90, m.a90) == (2, 1, 1, 1)
    assert m.extra_time and m.outcome == 1  # level after 90 minutes counts as a draw


def test_incomplete_goal_minutes_leave_ninety_minute_score_unknown():
    e = _event("STATUS_FINAL_AET", 2, 1, goals=[("10", "30'")])
    m = cups.to_match("facup", cups.parse_event("facup", e))
    assert m.h90 is None and m.outcome == 1


def test_penalties_without_extra_time():
    e = _event("STATUS_FINAL_PEN", 1, 1, goals=[("10", "12'"), ("20", "80'")], shootout=(4, 5))
    m = cups.to_match("eflcup", cups.parse_event("eflcup", e))
    assert (m.h90, m.a90) == (1, 1) and m.pens == (4, 5) and m.outcome == 1
    assert cup_note(m, "Leeds", "Hull") == "Hull won 5–4 on penalties"


def test_normal_time_result_and_season():
    m = cups.to_match("facup", cups.parse_event("facup", _event("STATUS_FULL_TIME", 0, 2)))
    assert m.outcome == 2 and not m.extra_time and cup_note(m, "Leeds", "Hull") is None
    assert m.season == "2526" and cups.season_of(date(2026, 8, 1)) == "2627"


def test_neutral_venues():
    final = cups.to_match("eflcup", cups.parse_event("eflcup", _event("STATUS_FULL_TIME", 1, 0, slug="final")))
    fa_semi = cups.to_match("facup", cups.parse_event("facup", _event("STATUS_FULL_TIME", 1, 0, slug="semifinals")))
    efl_semi = cups.to_match("eflcup", cups.parse_event("eflcup", _event("STATUS_FULL_TIME", 1, 0, slug="semifinals")))
    assert final.neutral and fa_semi.neutral and not efl_semi.neutral


def test_neutral_prediction_drops_home_advantage_and_uses_mean_division_level():
    n = 2
    theta = np.zeros(1 + 2 * n + 3)
    theta[1 + 2 * n:] = [0.1, 0.2, 0.3]  # E1, E2, E3 goal levels relative to E0
    m = DCModel(teams=["A", "B"], attack=np.zeros(2), defence=np.zeros(2), intercept=0.0, home_adv=0.3, rho=0.0,
                cutoff=date(2026, 1, 1), xi=0.002, ridge=2.0, n_matches=1, theta=theta)
    home = cups.predict(m, "A", "B", "E0", "E2", neutral=False)
    flat = cups.predict(m, "A", "B", "E0", "E2", neutral=True)
    assert np.isclose(home.lam, np.exp(0.3 + 0.1)) and np.isclose(flat.lam, np.exp(0.1)) and np.isclose(flat.lam, flat.mu)


def test_espn_names_map_to_football_data():
    known = {"Brighton", "Man City", "Forest Green", "Leeds"}
    assert canonical("Brighton & Hove Albion", known) == "Brighton"
    assert canonical("Manchester City", known) == "Man City"
    assert canonical("Forest Green Rovers", known) == "Forest Green"
    assert canonical("Oxford City", known | {"Oxford"}) is None  # non-league side, never guessed
