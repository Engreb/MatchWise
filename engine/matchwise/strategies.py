"""Betting-strategy backtest: what would £1 per bet have returned on the held-out seasons?

Every prediction comes from the same leakage-safe weekly replay used to measure accuracy, so it
only uses results from before each match. Bets are settled at real pre-match prices from
football-data.co.uk: the average across bookmakers (what a typical bookmaker offered), the best
price available (shopping around), and Bet365 as a single real bookmaker.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .backtest import SEASON_LABEL, TEST, load_config, mix_for, replay
from .blend import pool
from .data import LEAGUES, load_results

PRICES = {"avg": "Average bookmaker", "max": "Best price available", "b365": "Bet365"}
EDGES = (0.0, 0.05, 0.10, 0.20)


def collect(log=print) -> list[dict]:
    cfg = load_config()
    rows = []
    for div in LEAGUES:
        ms = load_results(div)
        for season in TEST:
            log(f"  replaying {div} {season}")
            for m, p, _, _ in replay(ms, season, cfg["xi"], cfg["ridge"], mix=mix_for(cfg, div)):
                if not (m.odds_avg and m.market_open):
                    continue
                model = [p.home, p.draw, p.away]
                rows.append({
                    "div": div, "season": season,
                    "outcome": 0 if m.hg > m.ag else 1 if m.hg == m.ag else 2,
                    "model": model,
                    "adj": list(pool(model, m.market_open, cfg["blend"]["w_1x2"])),
                    "avg": list(m.odds_avg), "max": list(m.odds_max or m.odds_avg),
                    "b365": list(m.odds_b365) if m.odds_b365 else None,
                })
    return rows


def _argmax(v):
    return int(np.argmax(v))


def strategies() -> list[tuple[str, str, callable]]:
    """(key, label, pick(row, prices) -> outcome index or None)."""
    out = [
        ("model_top", "Model's top pick", lambda r, o: _argmax(r["model"])),
        ("adj_top", "Odds-adjusted top pick (what the app highlights)", lambda r, o: _argmax(r["adj"])),
        ("favourite", "Bookmaker favourite (shortest odds)", lambda r, o: _argmax([-x for x in o])),
        ("home", "Every home win", lambda r, o: 0),
        ("draw", "Every draw", lambda r, o: 1),
        ("away", "Every away win", lambda r, o: 2),
    ]
    for e in EDGES:
        def value(r, o, e=e):
            ev = [r["model"][k] * o[k] - 1 for k in range(3)]
            k = _argmax(ev)
            return k if ev[k] >= e else None
        out.append((f"value_{int(e * 100)}", f"'Value' bets: model's chance × odds beats 1 by {int(e * 100)}%+", value))
    return out


def evaluate(rows, price: str, seed: int = 3) -> list[dict]:
    rng = np.random.default_rng(seed)
    res = []
    for key, label, pick in strategies():
        returns, odds_taken = [], []
        for r in rows:
            o = r[price]
            if not o:
                continue
            k = pick(r, o)
            if k is None:
                continue
            odds_taken.append(o[k])
            returns.append(o[k] - 1 if k == r["outcome"] else -1.0)
        n = len(returns)
        if not n:
            continue
        ret = np.array(returns)
        boot = ret[rng.integers(0, n, (2000, n))].mean(axis=1)
        res.append({
            "key": key, "label": label, "bets": n, "wins": int((ret > 0).sum()),
            "hit_rate": float((ret > 0).mean()), "avg_odds": float(np.mean(odds_taken)),
            "profit": float(ret.sum()), "roi": float(ret.mean()),
            "roi_lo": float(np.percentile(boot, 2.5)), "roi_hi": float(np.percentile(boot, 97.5)),
        })
    return res


def run(out_dir: Path, log=print) -> dict:
    rows = collect(log)
    by_price = {p: evaluate(rows, p) for p in PRICES}
    by_league = {}
    for div, (key, name) in LEAGUES.items():
        sub = [r for r in rows if r["div"] == div]
        if sub:
            by_league[key] = {"name": name, "results": [x for x in evaluate(sub, "max") if x["key"] in ("adj_top", "favourite", "value_10")]}
    margin = float(np.mean([sum(1 / x for x in r["avg"]) - 1 for r in rows]))
    margin_max = float(np.mean([sum(1 / x for x in r["max"]) - 1 for r in rows]))
    out = {"seasons": [SEASON_LABEL[s] for s in TEST], "matches": len(rows), "prices": PRICES,
           "by_price": by_price, "by_league": by_league, "avg_margin": margin, "best_price_margin": margin_max}
    (out_dir / "strategies.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for p, label in PRICES.items():
        log(f"\n{label} odds")
        for x in by_price[p]:
            log(f"  {x['label'][:62]:62} bets {x['bets']:5}  hit {x['hit_rate']:5.1%}  avg odds {x['avg_odds']:5.2f}  "
                f"profit {x['profit']:+8.1f}  ROI {x['roi']:+6.1%} (95% {x['roi_lo']:+.1%} to {x['roi_hi']:+.1%})")
    log(f"\nAverage bookmaker margin: {margin:.1%}; best-price margin: {margin_max:.1%}")
    return out
