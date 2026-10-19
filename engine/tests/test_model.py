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


def test_joint_division_gradient_is_correct():
    from scipy.optimize import check_grad
    from matchwise.model import _neg_ll
    rng = np.random.default_rng(3)
    n, m = 6, 80
    hi, ai = rng.integers(0, n, m), rng.integers(0, n, m)
    keep = hi != ai
    hi, ai = hi[keep], ai[keep]
    x, y = rng.poisson(1.4, len(hi)).astype(float), rng.poisson(1.1, len(hi)).astype(float)
    w, grp = np.ones(len(hi)), rng.integers(0, 2, len(hi))
    th = rng.normal(0, 0.1, 1 + 2 * n + 1); th[2] = -0.05
    f = lambda t: _neg_ll(t, hi, ai, x, y, w, n, 1.0, np.zeros(n), np.zeros(n), False, grp, 2)[0]
    g = lambda t: _neg_ll(t, hi, ai, x, y, w, n, 1.0, np.zeros(n), np.zeros(n), False, grp, 2)[1]
    assert check_grad(f, g, th) < 1e-4


def test_joint_fit_places_promoted_team_on_top_division_scale():
    from matchwise.model import linked_priors
    rng = np.random.default_rng(5)
    top = [f"T{i}" for i in range(8)] + ["P"]          # P is promoted into the top division
    second = [f"S{i}" for i in range(7)] + ["P", "R"]  # R went down; P came up
    strength = {**{t: s for t, s in zip(top[:8], np.linspace(-0.3, 0.4, 8))},
                **{t: s for t, s in zip(second[:7], np.linspace(-0.9, -0.3, 7))}, "P": 0.05, "R": -0.45}
    out, k = [], 0
    for div, teams, lvl in (("A", [t for t in top if t != "P"] + ["R"], 0.25), ("B", second, 0.1)):
        for _ in range(4):
            for h in teams:
                for a in teams:
                    if h != a:
                        lam = math.exp(lvl + 0.25 + strength[h] - strength[a] * 0.8)
                        mu = math.exp(lvl + strength[a] - strength[h] * 0.8)
                        out.append(Match(div, "s", date(2021, 8, 1) + timedelta(days=k // 6), None, h, a,
                                         int(rng.poisson(lam)), int(rng.poisson(mu))))
                        k += 1
    cutoff = out[-1].date + timedelta(days=1)
    top_only = fit([m for m in out if m.div == "A"], cutoff, xi=0.0, ridge=1.0, teams=top)
    joint = fit(out, cutoff, xi=0.0, ridge=1.0, divisions=["A", "B"])
    pri = linked_priors(top_only, joint, ["P"])
    ranked = sorted(top[:8], key=lambda t: strength[t])
    # P's true strength (0.05) sits mid-table; its linked attack prior should land between
    # the 2nd-weakest and 2nd-strongest established sides.
    lo = top_only.attack[top_only.index(ranked[1])]
    hi = top_only.attack[top_only.index(ranked[-2])]
    assert lo < pri["P"][0] < hi


def test_shrink_total_moves_total_and_keeps_split():
    from matchwise.model import shrink_total
    lam, mu = shrink_total(1.0, 0.5, 2.7, 0.1)
    assert abs((lam + mu) - (1.5 + 0.1 * 1.2)) < 1e-12
    assert abs(lam / mu - 2.0) < 1e-12
    assert shrink_total(1.0, 0.5, None, 0.1) == (1.0, 0.5)
    assert shrink_total(1.0, 0.5, 2.7, 0.0) == (1.0, 0.5)
