"""Dixon–Coles (1997) goals model with time-decay weighting.

Convention (documented in docs/MODEL.md):
    log(lambda_home) = intercept + home_adv + attack[home] + defence[away]
    log(lambda_away) = intercept + attack[away] + defence[home]
    sum(attack) = 0, sum(defence) = 0
`defence` is a defensive *weakness*: higher means the team concedes more.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

RHO_BOUNDS = (-0.25, 0.25)
TAIL_TOL = 1e-10


@dataclass
class DCModel:
    teams: list[str]
    attack: np.ndarray
    defence: np.ndarray
    intercept: float
    home_adv: float
    rho: float
    cutoff: date
    xi: float
    ridge: float
    n_matches: int
    team_weight: dict[str, float] = field(default_factory=dict)
    prior_teams: set[str] = field(default_factory=set)
    converged: bool = True
    theta: np.ndarray | None = None

    def index(self, team: str) -> int:
        return self.teams.index(team)

    def rates(self, home: str, away: str) -> tuple[float, float]:
        h, a = self.index(home), self.index(away)
        lam = math.exp(self.intercept + self.home_adv + self.attack[h] + self.defence[a])
        mu = math.exp(self.intercept + self.attack[a] + self.defence[h])
        return lam, mu

    def predict(self, home: str, away: str) -> "Prediction":
        lam, mu = self.rates(home, away)
        return prediction(lam, mu, self.rho)


def tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def feasible_rho(lam: float, mu: float, rho: float) -> float:
    """Clip rho to the range where every corrected probability stays non-negative."""
    lo = max(-1 / lam, -1 / mu)
    hi = min(1 / (lam * mu), 1.0)
    return min(max(rho, lo), hi)


@dataclass
class Prediction:
    lam: float
    mu: float
    rho: float
    grid: np.ndarray  # grid[x, y] = P(home x, away y)
    tail_mass: float  # probability outside the grid (not renormalised)

    @property
    def home(self) -> float:
        return float(np.tril(self.grid, -1).sum())

    @property
    def draw(self) -> float:
        return float(np.trace(self.grid))

    @property
    def away(self) -> float:
        return float(np.triu(self.grid, 1).sum())

    def over(self, line: float) -> float:
        n = self.grid.shape[0]
        tot = np.add.outer(np.arange(n), np.arange(n))
        # Mass outside the grid always has more than `line` goals for the lines we use.
        return float(self.grid[tot > line].sum() + self.tail_mass)

    @property
    def btts(self) -> float:
        return float(self.grid[1:, 1:].sum())


def prediction(lam: float, mu: float, rho: float) -> Prediction:
    rho = feasible_rho(lam, mu, rho)
    n = int(max(poisson.isf(TAIL_TOL, lam), poisson.isf(TAIL_TOL, mu), 10)) + 1
    ph = poisson.pmf(np.arange(n), lam)
    pa = poisson.pmf(np.arange(n), mu)
    grid = np.outer(ph, pa)
    grid[0, 0] *= tau(0, 0, lam, mu, rho)
    grid[0, 1] *= tau(0, 1, lam, mu, rho)
    grid[1, 0] *= tau(1, 0, lam, mu, rho)
    grid[1, 1] *= tau(1, 1, lam, mu, rho)
    tail = max(0.0, 1.0 - float(grid.sum()))
    return Prediction(lam, mu, rho, grid, tail)


def _neg_ll(theta, hi, ai, x, y, w, n, ridge, a0, d0, fix_rho):
    c, h, rho = theta[0], theta[1], (0.0 if fix_rho else theta[2])
    af, df = theta[3:2 + n], theta[2 + n:1 + 2 * n]
    A = np.append(af, -af.sum())
    D = np.append(df, -df.sum())
    loglam = c + h + A[hi] + D[ai]
    logmu = c + A[ai] + D[hi]
    lam, mu = np.exp(loglam), np.exp(logmu)

    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    t = np.ones_like(lam)
    t[m00] = 1 - lam[m00] * mu[m00] * rho
    t[m01] = 1 + lam[m01] * rho
    t[m10] = 1 + mu[m10] * rho
    t[m11] = 1 - rho
    if np.any(t <= 1e-12):
        g = np.zeros_like(theta)
        g[2] = 1e4 * np.sign(rho)
        return 1e12, g

    ll = np.log(t) + x * loglam - lam + y * logmu - mu
    pen = ridge * (np.sum((A - a0) ** 2) + np.sum((D - d0) ** 2))
    f = -np.sum(w * ll) + pen

    dt_dl = np.zeros_like(lam)
    dt_dm = np.zeros_like(lam)
    dt_dr = np.zeros_like(lam)
    dt_dl[m00] = -lam[m00] * mu[m00] * rho
    dt_dm[m00] = -lam[m00] * mu[m00] * rho
    dt_dr[m00] = -lam[m00] * mu[m00]
    dt_dl[m01] = lam[m01] * rho
    dt_dr[m01] = lam[m01]
    dt_dm[m10] = mu[m10] * rho
    dt_dr[m10] = mu[m10]
    dt_dr[m11] = -1.0

    gl = w * (x - lam + dt_dl / t)
    gm = w * (y - mu + dt_dm / t)
    gA = np.bincount(hi, gl, n) + np.bincount(ai, gm, n)
    gD = np.bincount(ai, gl, n) + np.bincount(hi, gm, n)
    gA = -gA + 2 * ridge * (A - a0)
    gD = -gD + 2 * ridge * (D - d0)

    g = np.empty_like(theta)
    g[0] = -np.sum(gl + gm)
    g[1] = -np.sum(gl)
    g[2] = 0.0 if fix_rho else -np.sum(w * dt_dr / t)
    g[3:2 + n] = gA[:-1] - gA[-1]
    g[2 + n:1 + 2 * n] = gD[:-1] - gD[-1]
    return f, g


def fit(matches, cutoff: date, xi: float = 0.002, ridge: float = 2.0, *,
        teams: list[str] | None = None, priors: dict[str, tuple[float, float]] | None = None,
        fix_rho: bool = False, window_days: int = 1460, init: DCModel | None = None) -> DCModel:
    """Fit on matches strictly before `cutoff`.

    `teams` may include teams with no matches in the window (e.g. promoted sides); their
    ratings are then set by the ridge prior. `priors` maps team -> (attack, defence) targets
    for the ridge penalty; other teams shrink towards the league average (0).
    """
    train = [m for m in matches if m.played and m.date < cutoff and (cutoff - m.date).days <= window_days]
    if not train:
        raise ValueError("no training matches before cutoff")
    names = sorted(set(teams or []) | {m.home for m in train} | {m.away for m in train})
    idx = {t: i for i, t in enumerate(names)}
    n = len(names)
    hi = np.array([idx[m.home] for m in train])
    ai = np.array([idx[m.away] for m in train])
    x = np.array([m.hg for m in train], dtype=float)
    y = np.array([m.ag for m in train], dtype=float)
    age = np.array([(cutoff - m.date).days for m in train], dtype=float)
    w = np.exp(-xi * age)
    priors = priors or {}
    a0 = np.array([priors.get(t, (0.0, 0.0))[0] for t in names])
    d0 = np.array([priors.get(t, (0.0, 0.0))[1] for t in names])
    # Keep targets consistent with the sum-to-zero constraint.
    a0 -= a0.mean()
    d0 -= d0.mean()

    theta0 = np.zeros(1 + 2 * n)
    theta0[0] = math.log(max(np.average((x + y) / 2, weights=w), 0.1))
    theta0[1] = 0.2
    theta0[2] = 0.0 if fix_rho else -0.05
    if init is not None and init.teams == names and init.theta is not None:
        theta0 = init.theta.copy()
        if fix_rho:
            theta0[2] = 0.0

    bounds = [(None, None), (None, None), (0.0, 0.0) if fix_rho else RHO_BOUNDS] + [(None, None)] * (2 * (n - 1))
    res = minimize(_neg_ll, theta0, args=(hi, ai, x, y, w, n, ridge, a0, d0, fix_rho),
                   jac=True, method="L-BFGS-B", bounds=bounds, options={"maxiter": 2000})
    th = res.x
    af, df = th[3:2 + n], th[2 + n:1 + 2 * n]
    team_weight = {t: 0.0 for t in names}
    for m, wi in zip(train, w):
        team_weight[m.home] += wi
        team_weight[m.away] += wi
    return DCModel(
        teams=names, attack=np.append(af, -af.sum()), defence=np.append(df, -df.sum()),
        intercept=float(th[0]), home_adv=float(th[1]), rho=0.0 if fix_rho else float(th[2]),
        cutoff=cutoff, xi=xi, ridge=ridge, n_matches=len(train), team_weight=team_weight,
        prior_teams=set(priors), converged=bool(res.success), theta=th,
    )


def promoted_priors(model: DCModel, relegated: list[str], promoted: list[str]) -> dict[str, tuple[float, float]]:
    """Promoted sides start at the average rating of the sides that went down."""
    rel = [t for t in relegated if t in model.teams]
    if not rel or not promoted:
        return {}
    a = float(np.mean([model.attack[model.index(t)] for t in rel]))
    d = float(np.mean([model.defence[model.index(t)] for t in rel]))
    return {t: (a, d) for t in promoted}
