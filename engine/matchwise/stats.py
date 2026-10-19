"""Match stats: shots, shots on target, corners, fouls and yellow cards.

Each stat gets the same kind of model as goals, one per league:
    log(home mean) = c + h + for[home] + against[away] (+ g * closeness + ref[referee])
    log(away mean) = c +     for[away] + against[home] (+ g * closeness + ref[referee])
fitted by time-weighted Poisson likelihood with ridge shrinkage (sum-to-zero ratings, as in
model.py). Counts vary more than a Poisson allows, so probabilities use a negative binomial
with a per-league dispersion estimated from the training residuals.

Yellow cards can also use how close the match should be (closeness = -|log home goal rate -
log away goal rate| from the goals model fitted at the same cutoff) and, in the British leagues,
the referee. Each extra is kept only if the backtest shows it helps.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

STATS = {"shots": ("hs", "as_"), "sot": ("hst", "ast"), "corners": ("hc", "ac"),
         "fouls": ("hf", "af"), "yellows": ("hy", "ay")}
LABELS = {"shots": "Shots", "sot": "Shots on target", "corners": "Corners", "fouls": "Fouls", "yellows": "Yellow cards"}
REF_DIVS = {"E0", "E1", "E2", "E3", "SC0", "SC1"}
WINDOW_DAYS = 1460
K_MAX = 1e4  # dispersion cap: effectively Poisson


@dataclass
class StatModel:
    stat: str
    teams: list[str]
    fr: np.ndarray  # "for" rating
    ag: np.ndarray  # "against" rating (higher = concedes more)
    c: float
    h: float
    k: float  # negative-binomial dispersion: var = m + m^2 / k
    cutoff: date
    g: float = 0.0
    cl_mean: float = 0.0
    refs: dict[str, float] = field(default_factory=dict)
    team_weight: dict[str, float] = field(default_factory=dict)
    theta: np.ndarray | None = None

    def means(self, home: str, away: str, cl: float | None = None, referee: str | None = None) -> tuple[float, float]:
        i, j = self.teams.index(home), self.teams.index(away)
        extra = (self.g * ((cl if cl is not None else self.cl_mean) - self.cl_mean)
                 + self.refs.get(referee or "", 0.0))
        return (math.exp(self.c + self.h + self.fr[i] + self.ag[j] + extra),
                math.exp(self.c + self.fr[j] + self.ag[i] + extra))

    def team_rates(self, team: str) -> tuple[float, float]:
        """Per-match for/against against an average opponent, halfway between home and away."""
        i = self.teams.index(team)
        return math.exp(self.c + self.h / 2 + self.fr[i]), math.exp(self.c + self.h / 2 + self.ag[i])


# ---------- distributions ----------
def nb_logpmf(x, m, k):
    x, m = np.asarray(x, float), np.asarray(m, float)
    if k >= K_MAX:
        return x * np.log(m) - m - gammaln(x + 1)
    return (gammaln(x + k) - gammaln(k) - gammaln(x + 1)
            + k * np.log(k / (k + m)) + x * np.log(m / (k + m)))


def nb_pmf(m: float, k: float, n: int | None = None) -> np.ndarray:
    n = n or int(m + 12 * math.sqrt(m + m * m / k) + 20)
    p = np.exp(nb_logpmf(np.arange(n), m, k))
    return p / p.sum()


def total_pmf(mh: float, ma: float, k: float) -> np.ndarray:
    return np.convolve(nb_pmf(mh, k), nb_pmf(ma, k))


def p_over(pmf: np.ndarray, line: float) -> float:
    return float(pmf[int(math.floor(line)) + 1:].sum())


# ---------- fitting ----------
def _rows(matches, stat, cutoff):
    hk, ak = STATS[stat]
    return [m for m in matches if m.played and m.date < cutoff and (cutoff - m.date).days <= WINDOW_DAYS
            and getattr(m, hk) is not None and getattr(m, ak) is not None]


def _neg_ll(theta, hi, ai, ri, x, y, cl, w, n, nr, ridge, rref, a0, d0, use_g):
    c, h, g = theta[0], theta[1], (theta[2] if use_g else 0.0)
    fa, da = theta[3:2 + n], theta[2 + n:1 + 2 * n]
    F, D = np.append(fa, -fa.sum()), np.append(da, -da.sum())
    R = np.append(theta[1 + 2 * n:], 0.0)  # last slot = unknown referee, fixed at 0
    base = c + g * cl + R[ri]
    lh, la = base + h + F[hi] + D[ai], base + F[ai] + D[hi]
    mh, ma = np.exp(lh), np.exp(la)
    f = -np.sum(w * (x * lh - mh + y * la - ma)) + ridge * (np.sum((F - a0) ** 2) + np.sum((D - d0) ** 2))
    f += rref * np.sum(R[:-1] ** 2)
    gl, gm = w * (x - mh), w * (y - ma)
    gF = -(np.bincount(hi, gl, n) + np.bincount(ai, gm, n)) + 2 * ridge * (F - a0)
    gD = -(np.bincount(ai, gl, n) + np.bincount(hi, gm, n)) + 2 * ridge * (D - d0)
    grad = np.empty_like(theta)
    grad[0] = -np.sum(gl + gm)
    grad[1] = -np.sum(gl)
    grad[2] = -np.sum((gl + gm) * cl) if use_g else 0.0
    grad[3:2 + n] = gF[:-1] - gF[-1]
    grad[2 + n:1 + 2 * n] = gD[:-1] - gD[-1]
    if nr:
        grad[1 + 2 * n:] = -np.bincount(ri, gl + gm, nr + 1)[:-1] + 2 * rref * R[:-1]
    return f, grad


def fit_stat(matches, stat: str, cutoff: date, xi: float, ridge: float, *, teams=None, priors=None,
             closeness=None, ref_ridge: float | None = None, init: StatModel | None = None) -> StatModel:
    """Fit on matches strictly before `cutoff`. `closeness(home, away, date) -> float` adds the
    closeness term; `ref_ridge` adds shrunk referee effects."""
    train = _rows(matches, stat, cutoff)
    if not train:
        raise ValueError(f"no {stat} data before {cutoff}")
    hk, ak = STATS[stat]
    names = sorted(set(teams or []) | {m.home for m in train} | {m.away for m in train})
    idx = {t: i for i, t in enumerate(names)}
    n = len(names)
    use_ref = ref_ridge is not None
    refs = sorted({m.referee for m in train if m.referee}) if use_ref else []
    ridx = {r: i for i, r in enumerate(refs)}
    nr = len(refs)
    hi = np.array([idx[m.home] for m in train])
    ai = np.array([idx[m.away] for m in train])
    ri = np.array([ridx.get(m.referee, nr) if use_ref else 0 for m in train])
    x = np.array([getattr(m, hk) for m in train], float)
    y = np.array([getattr(m, ak) for m in train], float)
    w = np.exp(-xi * np.array([(cutoff - m.date).days for m in train], float))
    use_g = closeness is not None
    cl = np.array([closeness(m.home, m.away, m.date) for m in train], float) if use_g else np.zeros(len(train))
    cl_mean = float(np.average(cl, weights=w)) if use_g else 0.0
    cl = cl - cl_mean
    priors = priors or {}
    a0 = np.array([priors.get(t, (0.0, 0.0))[0] for t in names])
    d0 = np.array([priors.get(t, (0.0, 0.0))[1] for t in names])
    a0 -= a0.mean()
    d0 -= d0.mean()
    theta0 = np.zeros(1 + 2 * n + nr)
    theta0[0] = math.log(max(np.average((x + y) / 2, weights=w), 0.1))
    theta0[1] = 0.1
    if init is not None and init.teams == names and init.theta is not None and len(init.theta) == len(theta0):
        theta0 = init.theta.copy()
    res = minimize(_neg_ll, theta0, args=(hi, ai, ri, x, y, cl, w, n, nr, ridge, ref_ridge or 0.0, a0, d0, use_g),
                   jac=True, method="L-BFGS-B", options={"maxiter": 3000})
    th = res.x
    F = np.append(th[3:2 + n], -th[3:2 + n].sum())
    D = np.append(th[2 + n:1 + 2 * n], -th[2 + n:1 + 2 * n].sum())
    R = np.append(th[1 + 2 * n:], 0.0)
    base = th[0] + (th[2] if use_g else 0.0) * cl + R[ri]
    mh, ma = np.exp(base + th[1] + F[hi] + D[ai]), np.exp(base + F[ai] + D[hi])
    # Method-of-moments dispersion: E[(x - m)^2] = m + m^2 / k.
    num = np.sum(w * (mh ** 2 + ma ** 2))
    den = np.sum(w * ((x - mh) ** 2 - mh + (y - ma) ** 2 - ma))
    k = float(min(num / den, K_MAX)) if den > 0 else K_MAX
    team_weight = {t: 0.0 for t in names}
    for m, wi in zip(train, w):
        team_weight[m.home] += wi
        team_weight[m.away] += wi
    return StatModel(stat=stat, teams=names, fr=F, ag=D, c=float(th[0]), h=float(th[1]), k=k, cutoff=cutoff,
                     g=float(th[2]) if use_g else 0.0, cl_mean=cl_mean,
                     refs={r: float(R[i]) for i, r in enumerate(refs)}, team_weight=team_weight, theta=th)


def priors_for_season(matches, season: str, stat: str, xi: float, ridge: float, extra_teams=()) -> tuple[list[str], dict]:
    """Teams in `season` and priors for newcomers: the average of the sides that left."""
    from .data import SEASONS
    teams = {t for m in matches if m.season == season for t in (m.home, m.away)} | set(extra_teams)
    i = SEASONS.index(season)
    in_season = [m.date for m in matches if m.season == season]
    if i == 0 or not in_season:
        return sorted(teams), {}
    prev = {t for m in matches if m.season == SEASONS[i - 1] for t in (m.home, m.away)}
    new, gone = sorted(teams - prev), sorted(prev - teams)
    if not new or not gone:
        return sorted(teams), {}
    try:
        base = fit_stat(matches, stat, min(in_season), xi, ridge)
    except ValueError:
        return sorted(teams), {}
    gone = [t for t in gone if t in base.teams]
    if not gone:
        return sorted(teams), {}
    f = float(np.mean([base.fr[base.teams.index(t)] for t in gone]))
    a = float(np.mean([base.ag[base.teams.index(t)] for t in gone]))
    return sorted(teams), {t: (f, a) for t in new}


# ---------- closeness from the goals model ----------
def closeness_fn(goals_model):
    """-|log(home rate) - log(away rate)| from a goals model; unknown teams get the median gap."""
    teams = set(goals_model.teams)
    cache: dict = {}
    fallback = []

    def f(home, away, _date=None):
        key = (home, away)
        if key not in cache:
            if home in teams and away in teams:
                lam, mu = goals_model.rates(home, away)
                cache[key] = -abs(math.log(lam / mu))
            else:
                cache[key] = None
        v = cache[key]
        if v is None:
            if not fallback:
                vals = [-abs(math.log(r[0] / r[1])) for r in
                        (goals_model.rates(h, a) for h in goals_model.teams[:12] for a in goals_model.teams[:12] if h != a)]
                fallback.append(float(np.median(vals)) if vals else -0.4)
            return fallback[0]
        return v
    return f


# ---------- backtest ----------
YELLOW_VARIANTS = {"base": (False, False), "closeness": (True, False), "referee": (False, True), "both": (True, True)}
GRID = [(xi, ridge) for xi in (0.002, 0.003, 0.005, 0.008, 0.012, 0.02) for ridge in (5.0, 15.0, 40.0, 100.0)]
REF_RIDGE = 10.0


def _baseline(matches, stat, cutoff):
    """League averages over the previous 365 days, as a negative binomial."""
    hk, ak = STATS[stat]
    rec = [m for m in _rows(matches, stat, cutoff) if (cutoff - m.date).days <= 365]
    if len(rec) < 30:
        return None
    x = np.array([getattr(m, hk) for m in rec], float)
    y = np.array([getattr(m, ak) for m in rec], float)
    mh, ma = x.mean(), y.mean()
    den = ((x - mh) ** 2).sum() - len(x) * mh + ((y - ma) ** 2).sum() - len(y) * ma
    k = float(min(len(x) * (mh ** 2 + ma ** 2) / den, K_MAX)) if den > 0 else K_MAX
    return mh, ma, k


def replay_stat(matches, season: str, stat: str, xi: float, ridge: float, *, cfg_goals=None,
                use_cl=False, use_ref=False, with_baseline=False):
    """Yield one record per played match in `season`, each predicted from a model fitted on
    results before that match's 7-day block (same blocking as backtest.replay)."""
    from .backtest import BLOCK_DAYS, preseason_priors
    from .model import fit as fit_goals
    hk, ak = STATS[stat]
    teams, priors = priors_for_season(matches, season, stat, xi, ridge)
    played = sorted([m for m in matches if m.season == season and m.played
                     and getattr(m, hk) is not None and getattr(m, ak) is not None], key=lambda m: m.date)
    if use_cl:
        gteams, gpriors, _ = preseason_priors(matches, season, cfg_goals["xi"], cfg_goals["ridge"])
    ref_ridge = REF_RIDGE if (use_ref and matches and matches[0].div in REF_DIVS) else None
    i, model = 0, None
    while i < len(played):
        start = played[i].date
        cl = None
        if use_cl:
            cl = closeness_fn(fit_goals(matches, start, cfg_goals["xi"], cfg_goals["ridge"], teams=gteams, priors=gpriors))
        model = fit_stat(matches, stat, start, xi, ridge, teams=teams, priors=priors, closeness=cl,
                         ref_ridge=ref_ridge, init=model)
        base = _baseline(matches, stat, start) if with_baseline else None
        end = start + timedelta(days=BLOCK_DAYS)
        while i < len(played) and played[i].date < end:
            m = played[i]
            assert model.cutoff <= m.date, "leakage"
            mh, ma = model.means(m.home, m.away, cl(m.home, m.away) if cl else None, m.referee)
            yield {"div": m.div, "season": m.season, "x": getattr(m, hk), "y": getattr(m, ak),
                   "mh": mh, "ma": ma, "k": model.k, "base": base}
            i += 1


def score(rows, key="model"):
    """Mean log score of the match total (lower is better), per-team log score, MAE of the total,
    and the over-line calibration gap (line = expected total rounded down + 0.5)."""
    tot_ll, team_ll, mae, cal = [], [], [], []
    for r in rows:
        if key == "model":
            mh, ma, k = r["mh"], r["ma"], r["k"]
        else:
            if not r["base"]:
                continue
            mh, ma, k = r["base"]
        pmf = total_pmf(mh, ma, k)
        t = r["x"] + r["y"]
        tot_ll.append(-math.log(max(pmf[t] if t < len(pmf) else 0.0, 1e-12)))
        team_ll.append(-float(nb_logpmf(r["x"], mh, k) + nb_logpmf(r["y"], ma, k)))
        mae.append(abs(t - (mh + ma)))
        line = math.floor(mh + ma) + 0.5
        cal.append((p_over(pmf, line), int(t > line)))
    return tot_ll, team_ll, mae, cal


def run(data: dict, cfg_goals: dict, log=print) -> dict:
    """Tune each stat on the validation season (tuning leagues only), then test on the held-out
    seasons in every league against league averages."""
    from .backtest import TEST, VALIDATION, bootstrap_diff, calibration
    from .data import LEAGUES, TUNING_DIVS
    t0 = time.time()
    out = {"stats": {}, "validation_seasons": VALIDATION, "test_seasons": TEST}
    chosen = {}
    for stat in STATS:
        tried = []
        for xi, ridge in GRID:
            rows = [r for d in TUNING_DIVS for s in VALIDATION for r in replay_stat(data[d], s, stat, xi, ridge)]
            obj = float(np.mean(score(rows)[0]))
            tried.append({"xi": xi, "ridge": ridge, "log_score": obj})
            log(f"  {stat} xi={xi} ridge={ridge}: validation log score {obj:.4f}")
        best = min(tried, key=lambda t: t["log_score"])
        chosen[stat] = {"xi": best["xi"], "ridge": best["ridge"]}
        out["stats"][stat] = {"label": LABELS[stat], "tried": tried, **chosen[stat]}

    # Yellow cards: closeness and referee, chosen on validation with the chosen xi/ridge.
    y = chosen["yellows"]
    var_val = {}
    for name, (use_cl, use_ref) in YELLOW_VARIANTS.items():
        rows = [r for d in TUNING_DIVS for s in VALIDATION
                for r in replay_stat(data[d], s, "yellows", y["xi"], y["ridge"], cfg_goals=cfg_goals, use_cl=use_cl, use_ref=use_ref)]
        var_val[name] = float(np.mean(score(rows)[0]))
        log(f"  yellows {name}: validation log score {var_val[name]:.4f}")
    best_var = min(var_val, key=var_val.get)

    for stat in STATS:
        c = chosen[stat]
        variants = {"base": (False, False)}
        if stat == "yellows" and best_var != "base":
            variants[best_var] = YELLOW_VARIANTS[best_var]
        rows_by = {}
        for name, (use_cl, use_ref) in variants.items():
            rows_by[name] = []
            for d in LEAGUES:
                for s in TEST:
                    rows_by[name] += list(replay_stat(data[d], s, stat, c["xi"], c["ridge"], cfg_goals=cfg_goals,
                                                     use_cl=use_cl, use_ref=use_ref, with_baseline=True))
        base_rows = rows_by["base"]
        res = out["stats"][stat]
        final_rows = base_rows
        if stat == "yellows":
            yv = {"validation": var_val, "best": best_var, "adopt": False}
            if best_var != "base":
                v_tot, all_base = score(rows_by[best_var])[0], score(base_rows)[0]
                assert len(rows_by[best_var]) == len(base_rows)
                d_all = bootstrap_diff(v_tot, all_base)
                ref_idx = [i for i, r in enumerate(base_rows) if r["div"] in REF_DIVS]
                yv["test"] = d_all
                yv["test_ref_leagues"] = bootstrap_diff([v_tot[i] for i in ref_idx], [all_base[i] for i in ref_idx]) if ref_idx else None
                yv["adopt"] = var_val[best_var] < var_val["base"] and d_all["mean"] <= 0
                log(f"  yellows {best_var} vs base on test: change {d_all['mean']:+.4f} "
                    f"(95% {d_all['lo']:+.4f} to {d_all['hi']:+.4f}) -> {'ADOPT' if yv['adopt'] else 'keep base'}")
                if yv["adopt"]:
                    final_rows = rows_by[best_var]  # report the version the app uses
            res["extras"] = yv
            chosen["yellows"]["closeness"] = bool(yv["adopt"] and YELLOW_VARIANTS[best_var][0])
            chosen["yellows"]["referee"] = bool(yv["adopt"] and YELLOW_VARIANTS[best_var][1])
        keep = [i for i, r in enumerate(final_rows) if r["base"]]
        m_tot, m_team, m_mae, m_cal = score([final_rows[i] for i in keep])
        b_tot, b_team, b_mae, b_cal = score([final_rows[i] for i in keep], "base")
        cal_m, ece_m = calibration(m_cal)
        _, ece_b = calibration(b_cal)
        res.update({
            "n_test": len(keep), "avg_total": float(np.mean([final_rows[i]["x"] + final_rows[i]["y"] for i in keep])),
            "log_score": float(np.mean(m_tot)), "log_score_base": float(np.mean(b_tot)),
            "vs_base": bootstrap_diff(m_tot, b_tot), "team_vs_base": bootstrap_diff(m_team, b_team),
            "mae": float(np.mean(m_mae)), "mae_base": float(np.mean(b_mae)),
            "ece": ece_m, "ece_base": ece_b, "calibration": cal_m,
            "by_league": {LEAGUES[d][0]: {"name": LEAGUES[d][1], "n": len(idx), "change": float(np.mean([m_tot[j] for j in idx]) - np.mean([b_tot[j] for j in idx]))}
                          for d in LEAGUES for idx in [[j for j, i in enumerate(keep) if final_rows[i]["div"] == d]] if idx},
        })
        res["adopt"] = res["vs_base"]["hi"] < 0
        log(f"  {stat}: test log score {res['log_score']:.4f} vs league average {res['log_score_base']:.4f} "
            f"(change {res['vs_base']['mean']:+.4f}, 95% {res['vs_base']['lo']:+.4f} to {res['vs_base']['hi']:+.4f}); "
            f"MAE {res['mae']:.2f} vs {res['mae_base']:.2f}; calibration gap {ece_m:.3f} -> {'SHOW' if res['adopt'] else 'hide'}")
        chosen[stat]["show"] = bool(res["adopt"])
    out["config"] = chosen
    out["runtime_s"] = round(time.time() - t0, 1)
    return out


# ---------- app output ----------
def league_payload(matches, cfg_stats: dict, cutoff: date, teams: list[str], season: str,
                   goals_model=None, fixtures=()) -> dict | None:
    """Ratings, every pair's expected counts and upcoming-fixture referee adjustments for one
    league, for the stats the backtest showed are worth showing."""
    shown = [s for s in STATS if cfg_stats.get(s, {}).get("show")]
    if not shown:
        return None
    out = {"stats": shown, "labels": {s: LABELS[s] for s in shown}, "k": {}, "avg": {}, "teams": {t: {} for t in teams},
           "pairs": {}, "fixtures": {}}
    models = {}
    for s in shown:
        c = cfg_stats[s]
        y = s == "yellows"
        cl = closeness_fn(goals_model) if (y and c.get("closeness") and goals_model) else None
        ref = REF_RIDGE if (y and c.get("referee") and matches and matches[0].div in REF_DIVS) else None
        tm, pr = priors_for_season(matches, season, s, c["xi"], c["ridge"], extra_teams=teams)
        try:
            m = fit_stat(matches, s, cutoff, c["xi"], c["ridge"], teams=tm, priors=pr, closeness=cl, ref_ridge=ref)
        except ValueError:
            continue
        models[s] = (m, cl)
        out["k"][s] = round(m.k, 2)
        out["avg"][s] = [round(math.exp(m.c + m.h), 2), round(math.exp(m.c), 2)]
        rates = {t: m.team_rates(t) for t in teams}
        by_for = sorted(teams, key=lambda t: -rates[t][0])
        by_ag = sorted(teams, key=lambda t: -rates[t][1])
        for t in teams:
            out["teams"][t][s] = [round(rates[t][0], 2), round(rates[t][1], 2), by_for.index(t) + 1, by_ag.index(t) + 1]
    out["stats"] = [s for s in shown if s in models]
    for h in teams:
        for a in teams:
            if h != a:
                v = []
                for s in out["stats"]:
                    m, cl = models[s]
                    v += [round(x, 2) for x in m.means(h, a, cl(h, a) if cl else None)]
                out["pairs"][f"{h}|{a}"] = v
    if "yellows" in models:
        m, cl = models["yellows"]
        done = {(x.date, x.home, x.away) for x in matches if x.played}
        for f in fixtures:
            # Only matches still to be played: a referee from an old fixture list mustn't stick
            # to a later meeting of the same two teams.
            if f.referee and f.home in teams and f.away in teams and (f.date, f.home, f.away) not in done and f.date >= cutoff:
                e = m.refs.get(f.referee)
                mh, ma = m.means(f.home, f.away, cl(f.home, f.away) if cl else None, f.referee)
                out["fixtures"][f"{f.home}|{f.away}"] = {
                    "referee": f.referee, "ref_pct": round((math.exp(e) - 1) * 100) if e is not None else None,
                    "yellows": [round(mh, 2), round(ma, 2)] if e is not None else None}
    return out
