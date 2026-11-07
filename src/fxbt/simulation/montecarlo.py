"""Monte-Carlo : est-ce le paramétrage ou la stratégie qui n'est pas bonne ?

1. Monte-Carlo sur les paramètres : on tire au hasard des jeux de réglages dans PARAM_SPACE
   (défini dans chaque stratégie) et on regarde la distribution des résultats. On lit la
   distribution d'ensemble, pas le meilleur tirage, qui est flatteur par construction.
2. Test contre le hasard : on garde exactement les trades de la stratégie (heures, stops,
   objectifs) mais on tire le sens à pile ou face. Si la stratégie ne fait pas mieux que ces
   trades au hasard, son signal ne prévoit pas la direction.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from .. import data
from ..data import INSTRUMENTS, cost_in_price
from ..strategies import STRATEGIES
from . import metrics
from .engine import Converter, account_for, resolve_exit, run, to_bars

_WORKER: dict = {}


def _cost(pair: str, cost: float | None) -> float:
    """Coût demandé, sinon le niveau de base de l'instrument."""
    return cost if cost is not None else (INSTRUMENTS[pair].costs[0] if pair in INSTRUMENTS else 1.1)


def sample_params(space: dict, n: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n):
        values = {}
        for key, spec in space.items():
            if spec[0] == "int":
                values[key] = int(rng.integers(spec[1], spec[2] + 1))
            elif spec[0] == "float":
                values[key] = round(float(rng.uniform(spec[1], spec[2])), 3)
            else:
                values[key] = spec[1][int(rng.integers(len(spec[1])))]
        samples.append(values)
    return samples


def load(pairs: list[str], load_start: str, end: str | None, source: str):
    m1s = {p: data.load_m1(p, load_start, end, source) for p in sorted(set(pairs) | {"EURUSD"})}
    return m1s, Converter({p: df["close"] for p, df in m1s.items()})


def _init_worker(pairs, load_start, end, start, source, cost):
    m1s, converter = load(pairs, load_start, end, source)
    _WORKER.update(m1s=m1s, converter=converter, start=pd.Timestamp(start, tz=data.TZ), pairs=pairs, cost=cost)


def _evaluate(job: tuple[str, dict]) -> dict:
    strategy, values = job
    module = STRATEGIES[strategy]
    params = module.Params(**values)
    w = _WORKER
    row = dict(values)
    for pair in w["pairs"]:
        signals = module.generate_signals(w["m1s"][pair], params, pair)
        account = account_for(pair)
        trades = run(signals[signals["entry_time"] >= w["start"]], w["m1s"][pair], pair, params, account,
                     _cost(pair, w["cost"]), w["converter"])
        m = metrics.summarize(trades, account.capital)
        row[f"{pair}_trades"] = m["trades"]
        row[f"{pair}_R"] = m.get("R_moyen", np.nan)
        row[f"{pair}_PF"] = m.get("profit_factor", np.nan)
    return row


def param_montecarlo(strategy: str, samples: int, seed: int, pairs, load_start, end, start, source, cost, workers) -> pd.DataFrame:
    space = STRATEGIES[strategy].PARAM_SPACE
    jobs = [(strategy, v) for v in sample_params(space, samples, seed)]
    with ProcessPoolExecutor(workers, initializer=_init_worker,
                             initargs=(pairs, load_start, end, start, source, cost)) as ex:
        rows = list(ex.map(_evaluate, jobs, chunksize=4))
    return pd.DataFrame(rows)


def summarize_montecarlo(table: pd.DataFrame, pairs: list[str], min_trades: int = 150) -> dict:
    r = table[[f"{p}_R" for p in pairs]]
    n = table[[f"{p}_trades" for p in pairs]]
    both_pos = (r > 0).all(axis=1)
    passes = (r >= 0.05).all(axis=1) & (n >= min_trades).all(axis=1)
    out = {"tirages": len(table), "positifs_toutes_paires_%": round(100 * both_pos.mean(), 1),
           "≥+0,05R_et_≥150_trades_%": round(100 * passes.mean(), 1)}
    for p in pairs:
        q = table[f"{p}_R"].quantile([0.1, 0.5, 0.9])
        out[f"{p}_R_p10/médiane/p90"] = f"{q[0.1]:+.3f} / {q[0.5]:+.3f} / {q[0.9]:+.3f}"
        out[f"{p}_trades_médian"] = int(table[f"{p}_trades"].median())
    return out


def _trade_r(b, pair: str, entry_time, deadline, d: int, dist: float, rr: float, cost: float) -> float:
    t = entry_time.as_unit("ns").value
    dl = deadline.as_unit("ns").value
    i0 = int(np.searchsorted(b.times, t))
    i1 = int(np.searchsorted(b.times, dl))
    entry = float(b.open[i0])
    stop, target = entry - d * dist, entry + d * rr * dist
    _, exit_px, _ = resolve_exit(b, i0, i1, d, stop, target, dl)
    return (d * (exit_px - entry) - cost_in_price(pair, cost, entry)) / dist


def direction_null(strategy: str, params, m1s: dict, converter: Converter, start: pd.Timestamp,
                   pairs: list[str], cost: float, flips: int, seed: int) -> pd.DataFrame:
    """Compare le R moyen réel au R moyen des mêmes trades avec un sens tiré au hasard."""
    module = STRATEGIES[strategy]
    rng = np.random.default_rng(seed)
    rows = []
    for pair in pairs:
        m1 = m1s[pair]
        signals = module.generate_signals(m1, params, pair)
        pair_cost = _cost(pair, cost)
        trades = run(signals[signals["entry_time"] >= start], m1, pair, params, account_for(pair), pair_cost, converter)
        if trades.empty:
            continue
        b = to_bars(m1)
        dist = (trades["entry"] - trades["stop"]).abs().to_numpy()
        rr = ((trades["target"] - trades["entry"]).abs().to_numpy()) / dist
        deadline = trades["entry_time"].dt.normalize() + pd.Timedelta(hours=params.flat_hour)
        # Chaque trade simulé indépendamment, dans les deux sens, au même coût.
        r_long = np.array([_trade_r(b, pair, t, dl, 1, s, k, pair_cost) for t, dl, s, k in zip(trades["entry_time"], deadline, dist, rr)])
        r_short = np.array([_trade_r(b, pair, t, dl, -1, s, k, pair_cost) for t, dl, s, k in zip(trades["entry_time"], deadline, dist, rr)])
        actual = np.where(trades["direction"].to_numpy() == 1, r_long, r_short).mean()
        coins = rng.integers(0, 2, size=(flips, len(trades))).astype(bool)
        null = np.where(coins, r_long, r_short).mean(axis=1)
        rows.append({
            "paire": pair,
            "trades": len(trades),
            "R_stratégie": round(float(actual), 3),
            "R_hasard_médian": round(float(np.median(null)), 3),
            "R_hasard_p95": round(float(np.quantile(null, 0.95)), 3),
            "part_du_hasard_qui_fait_mieux_%": round(float((null >= actual).mean() * 100), 1),
        })
    return pd.DataFrame(rows)


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 2)
