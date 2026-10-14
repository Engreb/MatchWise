"""League tables: current standings plus a Monte Carlo projection of the final table.

Each remaining scheduled fixture is played N_SIMS times. Goals are drawn from the model's
expected goals, and each simulated season also gets its own small random shift in every team's
strength (STRENGTH_SD on the log scale) so the projection reflects that ratings drift over a
season rather than treating today's ratings as certain. Ties on points are split by goal difference, then
goals scored, then at random (real tie-breakers vary by league; noted in the app).
"""
from __future__ import annotations

import numpy as np

N_SIMS = 10_000
STRENGTH_SD = 0.12

# Zones shown in the app: (label, positions as 1-based inclusive range)
ZONES = {
    "E0": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 18, 20)},
    "SP1": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 18, 20)},
    "I1": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 18, 20)},
    "D1": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 17, 18)},
    "F1": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 17, 18)},
    "E1": {"title": (1, 1), "top": ("Promotion", 1, 2), "playoff": ("Play-offs", 3, 6), "rel": ("Relegation", 22, 24)},
    "SC0": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 12, 12)},
    "N1": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 17, 18)},
    "P1": {"title": (1, 1), "top": ("Top 4", 1, 4), "rel": ("Relegation", 17, 18)},
}
NOTES = {"SC0": "Projection covers the 33 games before the league splits into top and bottom six."}


def standings(results, teams) -> dict[str, dict]:
    t = {n: {"team": n, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for n in teams}
    for m in results:
        for side, gf, ga in ((m.home, m.hg, m.ag), (m.away, m.ag, m.hg)):
            r = t.setdefault(side, {"team": side, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0})
            r["p"] += 1; r["gf"] += gf; r["ga"] += ga
            if gf > ga: r["w"] += 1; r["pts"] += 3
            elif gf == ga: r["d"] += 1; r["pts"] += 1
            else: r["l"] += 1
    return t


def _rank(pts, gd, gf, rng):
    # Larger is better; tiny random jitter breaks remaining ties.
    key = pts * 1e6 + gd * 1e3 + gf + rng.random(pts.shape) * 0.5
    order = np.argsort(-key, axis=1)
    pos = np.empty_like(order)
    rows = np.arange(order.shape[0])[:, None]
    pos[rows, order] = np.arange(order.shape[1])[None, :]
    return pos + 1  # 1-based position of each team in each simulation


def project(div, results, remaining, teams, rates_for, seed=11, strength_sd=STRENGTH_SD) -> dict:
    """`remaining` is a list of (home, away); `rates_for(home, away)` returns expected goals (home, away)."""
    rng = np.random.default_rng(seed)
    table = standings(results, teams)
    names = sorted(table)
    idx = {n: i for i, n in enumerate(names)}
    T = len(names)
    pts = np.tile([table[n]["pts"] for n in names], (N_SIMS, 1)).astype(float)
    gf = np.tile([table[n]["gf"] for n in names], (N_SIMS, 1)).astype(float)
    ga = np.tile([table[n]["ga"] for n in names], (N_SIMS, 1)).astype(float)
    shock = rng.normal(0.0, strength_sd, (N_SIMS, T))  # one strength shift per team per season
    for h, a in remaining:
        lam, mu = rates_for(h, a)
        i, j = idx[h], idx[a]
        x = rng.poisson(lam * np.exp(shock[:, i] - shock[:, j]))
        y = rng.poisson(mu * np.exp(shock[:, j] - shock[:, i]))
        gf[:, i] += x; ga[:, i] += y; gf[:, j] += y; ga[:, j] += x
        pts[:, i] += np.where(x > y, 3, np.where(x == y, 1, 0))
        pts[:, j] += np.where(y > x, 3, np.where(x == y, 1, 0))
    pos = _rank(pts, gf - ga, gf, rng)
    z = ZONES[div]

    def p_in(lo, hi):
        return ((pos >= lo) & (pos <= hi)).mean(axis=0)

    proj = {"title": p_in(1, 1), "top": p_in(z["top"][1], z["top"][2]), "rel": p_in(z["rel"][1], z["rel"][2])}
    if "playoff" in z:
        proj["playoff"] = p_in(z["playoff"][1], z["playoff"][2])
    rows = []
    for n in names:
        i, r = idx[n], table[n]
        dist = np.bincount(pos[:, i] - 1, minlength=T) / N_SIMS  # chance of finishing in each position
        rows.append({**r, "gd": r["gf"] - r["ga"], "xpts": round(float(pts[:, i].mean()), 1),
                     "xpos": round(float(pos[:, i].mean()), 1), "dist": [round(float(v), 3) for v in dist],
                     **{k: round(float(v[i]), 4) for k, v in proj.items()}})
    rows.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"]))
    for k, r in enumerate(rows, 1):
        r["pos"] = k
    return {"zones": {k: list(v) if isinstance(v, tuple) else v for k, v in z.items()},
            "remaining": len(remaining), "sims": N_SIMS, "note": NOTES.get(div), "rows": rows}
