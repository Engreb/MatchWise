from datetime import date, timedelta

import numpy as np
import pytest

from matchwise import stats
from matchwise.data import Match


def _season(rng, teams, strength, start=date(2024, 8, 1), refs=None, ref_effect=None, rounds=4):
    """Synthetic corners/cards: team i takes exp(1.6 + s_i) corners at home (x1.15) and away."""
    out, d = [], start
    for _ in range(rounds):
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                m = Match("E0", "2425", d, None, h, a, 1, 1)
                ref = refs[(len(out)) % len(refs)] if refs else None
                e = ref_effect.get(ref, 0.0) if ref_effect else 0.0
                m.hc = int(rng.poisson(np.exp(1.6 + 0.14 + strength[h] + e)))
                m.ac = int(rng.poisson(np.exp(1.6 + strength[a] + e)))
                m.hy, m.ay = int(rng.poisson(1.8 * np.exp(e))), int(rng.poisson(2.0 * np.exp(e)))
                m.referee = ref
                out.append(m)
                d += timedelta(days=1)
    return out


def test_fit_recovers_team_strength():
    rng = np.random.default_rng(1)
    teams = [f"T{i}" for i in range(8)]
    strength = {t: s for t, s in zip(teams, np.linspace(-0.3, 0.3, 8))}
    ms = _season(rng, teams, strength)
    m = stats.fit_stat(ms, "corners", ms[-1].date + timedelta(days=1), xi=0.0, ridge=0.5)
    fr = {t: m.fr[m.teams.index(t)] for t in teams}
    assert fr["T7"] > fr["T4"] > fr["T0"]
    assert m.h == pytest.approx(0.14, abs=0.06)


def test_nb_pmf_sums_to_one_with_right_mean():
    for k in (3.0, 15.0, stats.K_MAX):
        p = stats.nb_pmf(9.4, k)
        assert p.sum() == pytest.approx(1.0, abs=1e-9)
        assert (np.arange(len(p)) * p).sum() == pytest.approx(9.4, rel=1e-3)


def test_total_is_the_convolution():
    t = stats.total_pmf(5.0, 4.0, 12.0)
    assert t.sum() == pytest.approx(1.0, abs=1e-9)
    assert (np.arange(len(t)) * t).sum() == pytest.approx(9.0, rel=1e-3)
    a, b = stats.nb_pmf(5.0, 12.0), stats.nb_pmf(4.0, 12.0)
    assert t[3] == pytest.approx(sum(a[i] * b[3 - i] for i in range(4)))


def test_over_probabilities_fall_as_line_rises():
    t = stats.total_pmf(5.3, 4.6, 14.0)
    ps = [stats.p_over(t, l) for l in (7.5, 9.5, 11.5, 13.5)]
    assert all(x > y for x, y in zip(ps, ps[1:]))


def test_referee_effect_learned_and_zero_when_unknown():
    rng = np.random.default_rng(4)
    teams = [f"T{i}" for i in range(6)]
    ms = _season(rng, teams, {t: 0.0 for t in teams}, refs=["Strict", "Lenient", "Normal"],
                 ref_effect={"Strict": 0.3, "Lenient": -0.3}, rounds=6)
    m = stats.fit_stat(ms, "yellows", ms[-1].date + timedelta(days=1), xi=0.0, ridge=2.0, ref_ridge=2.0)
    assert m.refs["Strict"] > 0.15 > -0.15 > m.refs["Lenient"]
    base = m.means("T0", "T1")
    assert m.means("T0", "T1", referee="Someone new") == pytest.approx(base)
