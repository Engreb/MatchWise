import pytest

from matchwise.blend import blended_prediction, coherent, pool, pool_binary
from matchwise.model import prediction


def test_pool_endpoints_and_normalisation():
    p, q = [0.5, 0.3, 0.2], [0.4, 0.3, 0.3]
    assert pool(p, q, 0.0) == pytest.approx(p)
    assert pool(p, q, 1.0) == pytest.approx(q)
    assert pool(p, q, 0.5).sum() == pytest.approx(1.0)
    assert pool_binary(0.6, 0.4, 0.5) == pytest.approx(0.5)


def test_coherent_distribution_reproduces_targets():
    target = [0.55, 0.25, 0.20]
    b = coherent(1.4, 1.1, -0.08, target, 0.52)
    assert [b.home, b.draw, b.away] == pytest.approx(target, abs=0.01)
    assert b.over(2.5) == pytest.approx(0.52, abs=0.01)
    assert b.grid.sum() + b.tail_mass == pytest.approx(1.0)


def test_full_market_weight_follows_bookmakers():
    base = prediction(1.2, 1.2, -0.08)
    market = [0.60, 0.22, 0.18]
    b = blended_prediction(base, market, None, {"w_1x2": 1.0, "w_o25": 1.0})
    assert b.home == pytest.approx(0.60, abs=0.01)
    assert b.lam > b.mu
