"""Stratégie G : Smart Money Concepts (règles : docs/regles_smc.md).

- Liquidité : plus haut et plus bas de la zone asiatique (00h00–07h00, Zurich).
- Sweep entre 8h00 et 10h55 : dépassement en M5 puis clôture revenue dans la zone (6 bougies au plus).
- CHoCH M5 : clôture au-delà du dernier sommet (ou creux) de swing confirmé avant l'extrême du sweep.
- Zone d'entrée : dernier FVG de la jambe impulsive (G), ou order block ICT (G-OB, module smc_ob).
- Signal au premier contact M1 avec la zone, entrée à l'ouverture de la minute suivante, avant 11h55.
- Stop au-delà de l'extrême du sweep (1 pip), au moins 8 pips ; objectif à 2R ; sortie à 17h.

Le cœur (`find_setups`) sert aussi à la version swing (repo algo-trading-swing). Il raisonne à l'achat :
la vente passe par les prix inversés (plus haut ↔ −plus bas).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import daily_bars, pip_size, resample
from .base import SIGNAL_COLUMNS, BaseParams
from .indicators import ema, swing_points


@dataclass(frozen=True)
class Params(BaseParams):
    tf: str = "5min"
    asia_start_hour: int = 0
    asia_end_hour: int = 7
    setup_start_hour: int = 8
    setup_end_hour: int = 11  # sweep et CHoCH sur des bougies ouvertes avant 11h00
    entry_end_hour: int = 12  # contact avec la zone avant 12h00
    min_asia_minutes: int = 300  # garde-fou contre les trous de données (420 minutes attendues)
    swing_n: int = 2
    reclaim_bars: int = 6
    choch_bars: int = 24
    retest_bars: int = 12
    entry_zone: str = "fvg"  # fvg, ob ou ob_mid
    ob_lookback: int = 5
    buffer_pips: float = 1.0
    rr: float = 2.0
    target: str = "rr"  # rr, ou opposite : côté opposé de la zone asiatique
    use_bias: bool = False
    bias_ema: int = 50
    min_stop_pips: float = 8.0
    min_target_r: float = 1.0  # avec target=opposite
    max_trades_per_day: int = 2
    max_consec_losses: int = 2
    flat_hour: int = 17


def _side_setups(o, h, l, c, sess, level, other, ok, bias, swing_hi, p) -> list[tuple]:
    """Setups à l'achat (prix éventuellement inversés). Renvoie (bougie du CHoCH, niveau d'entrée, extrême, objectif)."""
    sh = np.flatnonzero(swing_hi)
    n = len(c)
    out = []
    seen = set()
    for k in np.flatnonzero(ok & (l < level)):
        if sess[k] in seen:
            continue
        seen.add(sess[k])  # seul le premier dépassement de la session compte
        if not bias[k]:
            continue
        lvl = level[k]
        last = k
        while last + 1 < n and last + 1 < k + p.choch_bars and sess[last + 1] == sess[k] and ok[last + 1]:
            last += 1
        reclaim = next((j for j in range(k, min(k + p.reclaim_bars, last + 1)) if c[j] > lvl), None)
        if reclaim is None:
            continue
        e, ext, choch = k, l[k], None
        for j in range(k, last + 1):
            if l[j] < ext:
                e, ext = j, l[j]
            if j < reclaim:
                continue
            pos = np.searchsorted(sh, min(e - 1, j - p.swing_n), side="right") - 1
            if pos >= 0 and c[j] > h[sh[pos]]:
                choch = j
                break
        if choch is None:
            continue
        fvg = next((i for i in range(choch, e + 1, -1) if h[i - 2] < l[i]), None)
        if fvg is None:
            continue
        if p.entry_zone == "fvg":
            zone = l[fvg]
        else:
            ob = next((i for i in range(e, max(e - p.ob_lookback, 0) - 1, -1) if c[i] < o[i]), None)
            if ob is None:
                continue
            zone = h[ob] if p.entry_zone == "ob" else (h[ob] + l[ob]) / 2
        out.append((choch, zone, ext, other[k]))
    return out


def find_setups(bars: pd.DataFrame, m1: pd.DataFrame, sess, level_hi, level_lo, ok, bias_long, bias_short,
                buffer, retest_end, p) -> list[dict]:
    """Setups SMC des deux côtés. Les tableaux sont alignés sur `bars` ; retest_end est en ns (int64).

    Renvoie pour chaque setup : sens, heure d'entrée (minute qui suit le contact), stop, objectif opposé.
    """
    tf_ns = pd.Timedelta(p.tf).value
    times = bars.index.as_unit("ns").asi8
    m1_times = m1.index.as_unit("ns").asi8
    hi, lo = swing_points(bars, p.swing_n)
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sides = [
        (1, (o, h, l, c), level_lo, level_hi, bias_long, hi.to_numpy(), m1["low"].to_numpy(float)),
        (-1, (-o, -l, -h, -c), -level_hi, -level_lo, bias_short, lo.to_numpy(), -m1["high"].to_numpy(float)),
    ]
    out = []
    for d, (so, sh_, sl, sc), level, other, bias, swing, m1_low in sides:
        for choch, zone, ext, target in _side_setups(so, sh_, sl, sc, sess, level, other, ok, bias, swing, p):
            start = times[choch] + tf_ns
            end = min(start + p.retest_bars * tf_ns, retest_end[choch])
            i0, i1 = np.searchsorted(m1_times, [start, end])
            touch = np.flatnonzero(m1_low[i0:i1] <= zone)
            if not touch.size or i0 + touch[0] + 1 >= len(m1_times):
                continue
            out.append({
                "direction": d,
                "entry_time": m1.index[i0 + touch[0] + 1],
                "stop_level": d * (ext - buffer[choch]),
                "target_level": d * target,
            })
    return out


def generate_signals(m1: pd.DataFrame, p: Params, pair: str | None = None) -> pd.DataFrame:
    bars = resample(m1, p.tf)
    day = bars.index.normalize()
    tod = bars.index.hour * 60 + bars.index.minute

    m1_tod = m1.index.hour * 60 + m1.index.minute
    asia = m1[(m1_tod >= p.asia_start_hour * 60) & (m1_tod < p.asia_end_hour * 60)]
    zone = asia.groupby(asia.index.normalize()).agg(hi=("high", "max"), lo=("low", "min"), n=("open", "size"))
    zone = zone[zone["n"] >= p.min_asia_minutes].reindex(day)
    hi, lo = zone["hi"].to_numpy(), zone["lo"].to_numpy()
    ok = ~np.isnan(hi) & (tod >= p.setup_start_hour * 60) & (tod < p.setup_end_hour * 60)

    if p.use_bias:
        daily = daily_bars(m1)
        prev_close = daily["close"].shift(1)
        prev_ema = ema(daily["close"], p.bias_ema).shift(1)
        date = day.tz_localize(None)
        above = (prev_close > prev_ema).reindex(date).eq(True).to_numpy()
        below = (prev_close < prev_ema).reindex(date).eq(True).to_numpy()
    else:
        above = below = np.ones(len(bars), bool)

    retest_end = (day + pd.Timedelta(hours=p.entry_end_hour)).as_unit("ns").asi8
    buffer = np.full(len(bars), p.buffer_pips * pip_size(pair or "EURUSD"))
    sess = day.asi8
    setups = find_setups(bars, m1, sess, hi, lo, ok, above, below, buffer, retest_end, p)

    return to_signals(setups, p, lambda entry: entry.normalize() + pd.Timedelta(hours=p.flat_hour))


def to_signals(setups: list[dict], p, deadline) -> pd.DataFrame:
    """Setups → DataFrame de signaux ; deadline(heures d'entrée) donne la sortie forcée."""
    if not setups:
        return pd.DataFrame(columns=SIGNAL_COLUMNS + ["target_level"])
    sig = pd.DataFrame(setups)
    entry = pd.DatetimeIndex(sig["entry_time"])
    sig_day = entry.normalize()
    sig["day"] = sig_day
    sig["deadline"] = deadline(entry)
    sig["stop_dist"] = np.nan
    sig["rr"] = p.rr
    if p.target != "opposite":
        sig["target_level"] = np.nan
    return sig[SIGNAL_COLUMNS + ["target_level"]].sort_values("entry_time", ignore_index=True)


# Plages de tirage pour le Monte-Carlo sur les paramètres (fixées avant le premier tirage).
PARAM_SPACE = {
    "swing_n": ("int", 1, 3),
    "reclaim_bars": ("int", 3, 12),
    "choch_bars": ("int", 12, 48),
    "retest_bars": ("int", 6, 24),
    "min_stop_pips": ("float", 5.0, 12.0),
    "rr": ("float", 1.5, 3.0),
    "use_bias": ("choice", [False, True]),
}
