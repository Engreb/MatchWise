from datetime import date

import pytest

from matchwise.backtest import shot_mixed
from matchwise.data import Match


def _m(d, hg, ag, hst, ast):
    return Match("X", "s", d, None, "A", "B", hg, ag, hst=hst, ast=ast)


def test_alpha_one_leaves_goals_unchanged():
    ms = [_m(date(2024, 1, 1), 2, 1, 6, 3)]
    assert shot_mixed(ms, 1.0, date(2025, 1, 1)) is ms


def test_mix_uses_goals_per_shot_from_before_cutoff_only():
    past = _m(date(2024, 1, 1), 3, 1, 8, 4)          # 4 goals / 12 shots on target -> k = 1/3
    future = _m(date(2024, 6, 1), 9, 9, 1, 1)         # must not influence k
    out = shot_mixed([past, future], 0.5, date(2024, 3, 1))
    assert out[0].hg == pytest.approx(0.5 * 3 + 0.5 * (1 / 3) * 8)
    assert out[0].ag == pytest.approx(0.5 * 1 + 0.5 * (1 / 3) * 4)
    assert past.hg == 3  # originals untouched


def test_xg_mix_uses_ratios_from_before_cutoff_and_falls_back_without_xg():
    from matchwise.backtest import mix_targets
    a = _m(date(2024, 1, 1), 2, 0, 6, 2); a.hxg, a.axg = 1.5, 0.5   # 2 goals / 2.0 xG -> kx = 1
    b = _m(date(2024, 2, 1), 1, 1, 4, 4)                              # no xG: goals + shots only
    out = mix_targets([a, b], (0.5, 0.0, 0.5), date(2024, 3, 1))
    assert out[0].hg == pytest.approx(0.5 * 2 + 0.5 * 1.5) and out[0].ag == pytest.approx(0.25)
    assert out[1].hg == 1 and out[1].ag == 1  # nothing to mix with, so goals unchanged
