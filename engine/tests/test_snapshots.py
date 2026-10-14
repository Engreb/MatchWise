import json

from matchwise.pipeline import _snapshot_index, saved_extras

FX = {"div": "E0", "date": "2026-10-17", "kickoff": "2026-10-17T11:30:00Z", "home": "Everton", "away": "Chelsea"}


def _save(d, name, created, **probs):
    (d / name).write_text(json.dumps({"created": created, "fixtures": [{**FX, **probs}]}))


def test_latest_save_before_kickoff_wins(tmp_path):
    _save(tmp_path, "2026-10-14.json", "2026-10-14T06:00:00Z", H=0.30, D=0.30, A=0.40)        # old daily name
    _save(tmp_path, "2026-10-16T1500.json", "2026-10-16T15:00:00Z", H=0.33, D=0.28, A=0.39)
    _save(tmp_path, "2026-10-17T1300.json", "2026-10-17T13:00:00Z", H=0.90, D=0.05, A=0.05)  # after kick-off
    s = _snapshot_index(tmp_path)[("E0", "2026-10-17", "Everton", "Chelsea")]
    assert s["H"] == 0.33 and s["saved_at"] == "2026-10-16T15:00:00Z"
    assert s["saves"] == 2  # the post-kick-off save is ignored


def test_odds_adjusted_prediction_is_carried_to_history():
    s = {**FX, "H": 0.35, "D": 0.28, "A": 0.37, "bH": 0.3, "bD": 0.27, "bA": 0.43, "bo25": 0.55,
         "market": [0.3, 0.27, 0.43], "odds_source": "The Odds API", "saved_at": "2026-10-16T15:00:00Z", "saves": 3}
    out = saved_extras(s)
    assert out["pb"] == [0.3, 0.27, 0.43] and out["pb_odds"] == "The Odds API" and out["saves"] == 3


def test_model_only_save_has_no_odds_adjusted_fields():
    out = saved_extras({**FX, "H": 0.35, "D": 0.28, "A": 0.37, "saved_at": "x"})
    assert "pb" not in out and out["saves"] == 1
