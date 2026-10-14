"""Combine model probabilities with pre-match bookmaker probabilities.

1. Log-linear pooling: p_blend ∝ p_model^(1-w) · p_market^w, separately for home/draw/away
   and for over/under 2.5, with weights tuned on validation seasons only.
2. The blended targets are turned back into one coherent score distribution by solving for
   the home/away goal rates whose Dixon–Coles grid reproduces them, so every market
   (double chance, totals, BTTS, scorelines) agrees with every other.

Only pre-match ("opening") odds are used: closing odds would not exist when you check the app.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize

from .model import Prediction, prediction

WEIGHTS = [round(0.1 * i, 1) for i in range(11)]


def pool(p, q, w):
    p, q = np.asarray(p, float), np.asarray(q, float)
    r = np.exp((1 - w) * np.log(np.clip(p, 1e-9, 1)) + w * np.log(np.clip(q, 1e-9, 1)))
    return r / r.sum()


def pool_binary(p, q, w):
    return float(pool([p, 1 - p], [q, 1 - q], w)[0])


def coherent(lam0: float, mu0: float, rho: float, target_1x2, target_o25=None) -> Prediction:
    """Goal rates whose score distribution best matches the blended targets."""
    t = np.asarray(target_1x2)

    def loss(x):
        p = prediction(math.exp(x[0]), math.exp(x[1]), rho)
        e = np.array([p.home, p.draw, p.away]) - t
        out = float(e @ e)
        if target_o25 is not None:
            out += (p.over(2.5) - target_o25) ** 2
        return out

    res = minimize(loss, [math.log(lam0), math.log(mu0)], method="Nelder-Mead",
                   options={"xatol": 1e-5, "fatol": 1e-10, "maxiter": 400})
    return prediction(math.exp(res.x[0]), math.exp(res.x[1]), rho)


def tune_weights(rows, ll_1x2, ll_bin, is_over):
    """Pick pooling weights on validation rows (needs model + opening-odds probabilities)."""
    r1 = [r for r in rows if r.get("mkt_open")]
    w1 = min(WEIGHTS, key=lambda w: np.mean([ll_1x2(pool(r["p"], r["mkt_open"], w), r["outcome"]) for r in r1]))
    r2 = [r for r in rows if r.get("mkt_o25_open") is not None]
    w2 = min(WEIGHTS, key=lambda w: np.mean([ll_bin(pool_binary(r["o25"], r["mkt_o25_open"], w), is_over(r)) for r in r2]))
    curve = [{"w": w, "log_loss": float(np.mean([ll_1x2(pool(r["p"], r["mkt_open"], w), r["outcome"]) for r in r1]))} for w in WEIGHTS]
    return {"w_1x2": w1, "w_o25": w2, "n": len(r1), "curve": curve}


def blended_prediction(base: Prediction, market_1x2, market_o25, weights) -> Prediction:
    t1 = pool([base.home, base.draw, base.away], market_1x2, weights["w_1x2"])
    t2 = pool_binary(base.over(2.5), market_o25, weights["w_o25"]) if market_o25 is not None else None
    return coherent(base.lam, base.mu, base.rho, t1, t2)
