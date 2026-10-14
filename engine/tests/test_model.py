import math
from datetime import date, timedelta

import numpy as np
import pytest
from scipy.stats import poisson

from matchwise.data import Match, implied
from matchwise.model import feasible_rho, fit, prediction, tau


def test_tau_matches_dixon_coles_definition():
    lam, mu, rho = 1.4, 1.1, -0.1
    assert tau(0, 0, lam, mu, rho) == pytest.approx(1 - lam * mu * rho)
    assert tau(0, 1, lam, mu, rho) == pytest.approx(1 + lam * rho)
    assert tau(1, 0, lam, mu, rho) == pytest.approx(1 + mu * rho)
    assert tau(1, 1, lam, mu, rho) == pytest.approx(1 - rho)
    assert tau(2, 3, lam, mu, rho) == 1.0


@pytest.mark.parametrize("lam,mu,rho", [(1.5, 1.1, -0.1), (0.4, 3.2, 0.05), (2.8, 0.3, -0.2)])
def test_grid_is_a_valid_distribution(lam, mu, rho):
    p = prediction(lam, mu, rho)
    assert (p.grid >= 0).all()
    assert p.grid.sum() + p.tail_mass == pytest.approx(1.0, abs=1e-9)
    assert p.tail_mass < 1e-8
    assert p.home + p.draw + p.away == pytest.approx(1.0, abs=1e-8)
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        assert 0 <= p.over(line) <= 1
    assert p.over(0.5) >= p.over(1.5) >= p.over(2.5) >= p.over(3.5) >= p.over(4.5)


def test_rho_zero_recovers_independent_poisson():
    lam, mu = 1.7, 0.9
    p = prediction(lam, mu, 0.0)
    n = p.grid.shape[0]
    expected = np.outer(poisson.pmf(np.arange(n), lam), poisson.pmf(np.arange(n), mu))
    assert np.allclose(p.grid, expected)


def test_correction_preserves_total_mass():
    a, b = prediction(1.3, 1.2, -0.15), prediction(1.3, 1.2, 0.0)
    assert a.grid.sum() == pytest.approx(b.grid.sum(), abs=1e-12)
    assert a.draw > b.draw  # negative rho inflates low-score draws


def test_infeasible_rho_is_clipped():
    assert feasible_rho(3.0, 3.0, 0.25) == pytest.approx(1 / 9)
    p = prediction(3.0, 3.0, 0.25)
    assert (p.grid >= 0).all()


def test_implied_removes_margin():
    probs = implied((2.0, 3.4, 3.8))
    assert sum(probs) == pytest.approx(1.0)
    assert probs[0] > probs[1] > probs[2]


def _synthetic(seed=0, seasons=3):
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(10)]
    att = np.linspace(-0.4, 0.4, 10)
    dfn = -np.linspace(-0.3, 0.3, 10)
    att -= att.mean(); dfn -= dfn.mean()
    c, h, rho = 0.2, 0.25, 0.0
    out, k = [], 0
    for _ in range(seasons * 2):
        for i in range(10):
            for j in range(10):
                if i == j:
                    continue
                lam = math.exp(c + h + att[i] + dfn[j]); mu = math.exp(c + att[j] + dfn[i])
                d = date(2020, 8, 1) + timedelta(days=k // 5)
                out.append(Match("X", "s", d, None, teams[i], teams[j], int(rng.poisson(lam)), int(rng.poisson(mu))))
                k += 1
    return out, att, dfn, c, h, d + timedelta(days=1)


def test_fit_recovers_synthetic_parameters():
    matches, att, dfn, c, h, end = _synthetic(seasons=8)
    m = fit(matches, end, xi=0.0, ridge=0.0, window_days=10_000)
    assert m.converged
    assert abs(m.attack.sum()) < 1e-9 and abs(m.defence.sum()) < 1e-9
    assert m.home_adv == pytest.approx(h, abs=0.06)
    assert m.intercept == pytest.approx(c, abs=0.08)
    assert np.corrcoef(m.attack, att)[0, 1] > 0.9
    assert np.corrcoef(m.defence, dfn)[0, 1] > 0.9


def test_fit_ignores_matches_on_or_after_cutoff():
    matches, *_ , end = _synthetic(seasons=1)
    cutoff = matches[100].date
    m1 = fit(matches, cutoff, ridge=1.0)
    future = [Match("X", "s", cutoff + timedelta(days=k), None, "T0", "T1", 9, 0) for k in range(5)]
    m2 = fit(matches + future, cutoff, ridge=1.0)
    assert m1.n_matches == m2.n_matches
    assert np.allclose(m1.attack, m2.attack)


def test_team_without_matches_takes_prior():
    matches, *_ , end = _synthetic(seasons=1)
    m = fit(matches, end, ridge=3.0, teams=["NEW"], priors={"NEW": (-0.3, 0.3)})
    i = m.index("NEW")
    assert m.attack[i] < -0.1 and m.defence[i] > 0.1
