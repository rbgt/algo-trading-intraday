"""Stratégie D : Breakout Price Action H4 / H1 / M5 (règles : docs/regles_breakout_price_action.md).

- Tendance H4 : les 2 derniers sommets et les 2 derniers creux confirmés montent (haussière)
  ou descendent (baissière). Achats seulement en tendance haussière, ventes seulement en baissière.
- Niveaux H1 : sommets et creux confirmés de moins de 150 bougies H1. Le premier passage d'une
  clôture au-delà du niveau est soit une cassure (bougie de force), soit la mort du niveau.
- Zone de chasse : niveau cassé ± 0,2 × ATR14 H1, annulée par une clôture H1 de l'autre côté de
  la zone ou après 24 bougies H1. Une zone ne sert qu'une fois.
- Signal : pin bar M5 dans la zone, sur une bougie ouverte entre 8h00 et 11h55.
  Entrée à l'ouverture suivante, stop 2 pips au-delà de la mèche, objectif sur l'extrême
  atteint depuis la cassure (ignoré si à moins de 1R). Sortie forcée à 17h.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import OHLCV, TZ, resample
from ..engine import SIGNAL_COLUMNS, BaseParams
from ..indicators import atr, swing_points


@dataclass(frozen=True)
class Params(BaseParams):
    swing_n: int = 3
    level_max_age: int = 150  # bougies H1
    force_body_atr: float = 0.7
    force_close_frac: float = 0.25  # clôture dans le quart extrême de la bougie
    zone_atr: float = 0.2
    pullback_bars: int = 24  # bougies H1
    use_h4_filter: bool = True
    pin_wick_body: float = 2.0
    pin_wick_range: float = 0.6
    stop_buffer_pips: float = 2.0
    pip: float = 0.0001  # 0.01 pour les paires en JPY
    atr_len: int = 14
    entry_start_hour: int = 8
    entry_end_hour: int = 12
    max_trades_per_day: int = 2
    max_consec_losses: int = 2
    flat_hour: int = 17
    min_target_r: float = 1.0


def h4_bars(m1: pd.DataFrame) -> pd.DataFrame:
    """Bougies H4 alignées sur la journée forex : 17h, 21h, 1h, 5h, 9h et 13h à New York."""
    ny = m1.tz_convert("America/New_York")
    h4 = ny.resample("4h", offset="1h", label="left", closed="left").agg(OHLCV).dropna(subset=["open"])
    h4.index = h4.index.tz_convert(TZ)
    return h4


def h4_trend(h4: pd.DataFrame, n: int) -> pd.DataFrame:
    """Tendance H4 (+1, −1 ou 0), datée de la clôture qui confirme le dernier sommet ou creux."""
    is_high, is_low = swing_points(h4, n)
    confirm = pd.Series(h4.index, index=h4.index).shift(-n) + pd.Timedelta(hours=4)
    events = pd.concat([
        pd.DataFrame({"time": confirm[is_high].to_numpy(), "kind": "high", "value": h4["high"][is_high].to_numpy()}),
        pd.DataFrame({"time": confirm[is_low].to_numpy(), "kind": "low", "value": h4["low"][is_low].to_numpy()}),
    ], ignore_index=True).dropna(subset=["time"]).sort_values("time", kind="stable")

    highs, lows, rows = [], [], []
    for e in events.itertuples(index=False):
        (highs if e.kind == "high" else lows).append(e.value)
        trend = 0
        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                trend = 1
            elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                trend = -1
        rows.append((e.time, trend))
    return pd.DataFrame(rows, columns=["time", "trend"]).drop_duplicates("time", keep="last")


def find_zones(h1: pd.DataFrame, p: Params) -> list[dict]:
    """Parcourt les bougies H1 et renvoie les zones de chasse créées par les cassures."""
    n = p.swing_n
    is_high, is_low = (s.to_numpy() for s in swing_points(h1, n))
    o, h, l, c = (h1[k].to_numpy() for k in ("open", "high", "low", "close"))
    a = atr(h1, p.atr_len).to_numpy()
    times = h1.index
    resistances: list[tuple[float, int]] = []
    supports: list[tuple[float, int]] = []
    zones = []

    for b in range(len(h1)):
        # Sommets et creux confirmés à la clôture de la bougie précédente.
        i = b - 1 - n
        if i >= 0 and is_high[i]:
            resistances.append((h[i], i))
        if i >= 0 and is_low[i]:
            supports.append((l[i], i))
        resistances = [(lv, j) for lv, j in resistances if b - j <= p.level_max_age]
        supports = [(lv, j) for lv, j in supports if b - j <= p.level_max_age]
        if np.isnan(a[b]):
            continue

        rng = h[b] - l[b]
        body = abs(c[b] - o[b])
        force_up = c[b] > o[b] and body >= p.force_body_atr * a[b] and rng > 0 and (h[b] - c[b]) <= p.force_close_frac * rng
        force_dn = c[b] < o[b] and body >= p.force_body_atr * a[b] and rng > 0 and (c[b] - l[b]) <= p.force_close_frac * rng

        # Premier passage d'une clôture au-delà du niveau : cassure si bougie de force, sinon niveau mort.
        crossed = [lv for lv, _ in resistances if c[b] > lv]
        resistances = [(lv, j) for lv, j in resistances if c[b] <= lv]
        if crossed and force_up:
            zones.append({"direction": 1, "level": max(crossed), "bar": b})
        crossed = [lv for lv, _ in supports if c[b] < lv]
        supports = [(lv, j) for lv, j in supports if c[b] >= lv]
        if crossed and force_dn:
            zones.append({"direction": -1, "level": min(crossed), "bar": b})

    one_hour = pd.Timedelta(hours=1)
    for z in zones:
        b, d = z["bar"], z["direction"]
        w = p.zone_atr * a[b]
        z["low"], z["high"] = z["level"] - w, z["level"] + w
        z["breakout_open"] = times[b]
        z["start"] = times[b] + one_hour
        last = min(b + p.pullback_bars, len(h1) - 1)
        end = times[last] + one_hour
        # Fausse cassure : clôture H1 de l'autre côté de la zone.
        after = c[b + 1:last + 1]
        failed = np.flatnonzero(after < z["low"]) if d == 1 else np.flatnonzero(after > z["high"])
        if failed.size:
            end = times[b + 1 + failed[0]] + one_hour
        z["end"] = end
    return zones


def generate_signals(m1: pd.DataFrame, p: Params) -> pd.DataFrame:
    h1 = resample(m1, "1h")
    m5 = resample(m1, "5min")
    zones = find_zones(h1, p)

    o, h, l, c = (m5[k].to_numpy() for k in ("open", "high", "low", "close"))
    rng = h - l
    body = np.abs(c - o)
    lower_wick = np.minimum(o, c) - l
    upper_wick = h - np.maximum(o, c)
    pin_up = (rng > 0) & (lower_wick >= p.pin_wick_body * body) & (lower_wick >= p.pin_wick_range * rng) & (c >= l + 2 / 3 * rng)
    pin_dn = (rng > 0) & (upper_wick >= p.pin_wick_body * body) & (upper_wick >= p.pin_wick_range * rng) & (c <= h - 2 / 3 * rng)

    tod = m5.index.hour * 60 + m5.index.minute
    in_window = (tod >= p.entry_start_hour * 60) & (tod < p.entry_end_hour * 60)

    if p.use_h4_filter:
        trend_tbl = h4_trend(h4_bars(m1), p.swing_n)
        close_times = pd.DataFrame({"time": m5.index + pd.Timedelta(minutes=5)})
        trend = pd.merge_asof(close_times, trend_tbl, on="time", direction="backward")["trend"].fillna(0).to_numpy()
    else:
        trend = None

    times = m5.index
    day = times.normalize()
    rows = []
    for z in zones:
        d = z["direction"]
        i0 = times.searchsorted(z["start"])
        i1 = times.searchsorted(z["end"])  # bougies M5 ouvertes avant la fin de la zone
        if i1 <= i0:
            continue
        sl = slice(i0, i1)
        if d == 1:
            ok = pin_up[sl] & (l[sl] <= z["high"]) & (c[sl] > z["low"])
        else:
            ok = pin_dn[sl] & (h[sl] >= z["low"]) & (c[sl] < z["high"])
        ok &= in_window[sl]
        if trend is not None:
            ok &= trend[sl] == d
        hits = np.flatnonzero(ok)
        if not hits.size:
            continue
        k = i0 + hits[0]  # une zone ne sert qu'une fois
        if k + 1 >= len(times) or day[k + 1] != day[k]:
            continue

        # Objectif : extrême atteint depuis l'ouverture de la bougie de cassure jusqu'au signal inclus.
        j0 = times.searchsorted(z["breakout_open"])
        target = h[j0:k + 1].max() if d == 1 else l[j0:k + 1].min()
        stop = l[k] - p.stop_buffer_pips * p.pip if d == 1 else h[k] + p.stop_buffer_pips * p.pip
        rows.append({
            "entry_time": times[k + 1],
            "direction": d,
            "stop_dist": np.nan,
            "stop_level": stop,
            "rr": np.nan,
            "deadline": day[k] + pd.Timedelta(hours=p.flat_hour),
            "day": day[k],
            "target_level": target,
        })

    if not rows:
        return pd.DataFrame(columns=SIGNAL_COLUMNS + ["target_level"])
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
