"""Stratégie D : Breakout Price Action (règles : docs/regles_breakout_price_action.md).

Version 1 (réglages par défaut) : tendance H4, niveaux H1, déclencheur M5, lignes horizontales.
La version 2 (module breakout_pa_v2) réutilise ce code en H1 / M15 / M5, avec les obliques à 3 touches.

- Tendance : les 2 derniers sommets et les 2 derniers creux confirmés montent (haussière) ou
  descendent (baissière). Achats seulement en tendance haussière, ventes seulement en baissière.
- Lignes : sommets et creux confirmés (horizontales), et en option obliques passant par au moins
  3 sommets ou creux. Le premier passage d'une clôture au-delà de la ligne est soit une cassure
  (bougie de force), soit la mort de la ligne.
- Zone de chasse : ligne (prolongée si oblique) ± zone_atr × ATR, annulée par une clôture de l'autre
  côté de la zone ou après pullback_bars bougies. Une zone ne sert qu'une fois.
- Signal : pin bar M5 dans la zone, sur une bougie ouverte entre 8h00 et 11h55.
  Entrée à l'ouverture suivante, stop 2 pips au-delà de la mèche, objectif sur l'extrême
  atteint depuis la cassure (ignoré si à moins de 1R). Sortie forcée à 17h.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import OHLCV, TZ, resample
from .base import SIGNAL_COLUMNS, BaseParams
from .indicators import atr, swing_points


@dataclass(frozen=True)
class Params(BaseParams):
    trend_tf: str = "4h"
    level_tf: str = "1h"
    swing_n: int = 3
    level_max_age: int = 150  # bougies de l'unité de temps des niveaux
    use_trendlines: bool = False
    touch_atr: float = 0.1  # tolérance d'une touche sur une oblique
    force_body_atr: float = 0.7
    force_close_frac: float = 0.25  # clôture dans le quart extrême de la bougie
    zone_atr: float = 0.2
    pullback_bars: int = 24  # bougies de l'unité de temps des niveaux
    use_trend_filter: bool = True
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


def trend_bars(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    return h4_bars(m1) if pd.Timedelta(tf) == pd.Timedelta("4h") else resample(m1, tf)


def swing_trend(bars: pd.DataFrame, n: int, tf: str) -> pd.DataFrame:
    """Tendance (+1, −1 ou 0), datée de la clôture qui confirme le dernier sommet ou creux."""
    is_high, is_low = swing_points(bars, n)
    confirm = pd.Series(bars.index, index=bars.index).shift(-n) + pd.Timedelta(tf)
    events = pd.concat([
        pd.DataFrame({"time": confirm[is_high].to_numpy(), "kind": "high", "value": bars["high"][is_high].to_numpy()}),
        pd.DataFrame({"time": confirm[is_low].to_numpy(), "kind": "low", "value": bars["low"][is_low].to_numpy()}),
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


def _new_trendlines(swings: list[tuple[int, float]], i: int, price: float, tol: float,
                    closes: np.ndarray, side: int) -> list[dict]:
    """Obliques qui se terminent au nouveau sommet (side=1) ou creux (side=-1) i.

    Chaque oblique part d'un sommet A antérieur et passe à moins de tol d'au moins un sommet
    intermédiaire, soit 3 touches. Aucune clôture ne doit l'avoir franchie entre A et i.
    """
    if len(swings) < 2:
        return []
    idx = np.array([s[0] for s in swings], dtype=float)
    px = np.array([s[1] for s in swings])
    slopes = (price - px) / (i - idx)                        # une droite par point de départ A
    line_at = px[:, None] + slopes[:, None] * (idx[None, :] - idx[:, None])
    between = (idx[None, :] > idx[:, None])                   # sommets B strictement entre A et i
    touches = (np.abs(px[None, :] - line_at) <= tol) & between
    lines = []
    for a in np.flatnonzero(touches.any(axis=1)):
        a_idx = int(idx[a])
        seg = np.arange(a_idx, i + 1)
        values = px[a] + slopes[a] * (seg - a_idx)
        crossed = (closes[seg] > values) if side == 1 else (closes[seg] < values)
        if not crossed.any():
            lines.append({"a": a_idx, "p": float(px[a]), "slope": float(slopes[a]), "last": i})
    return lines


def find_zones(bars: pd.DataFrame, p: Params, tf: str | None = None) -> list[dict]:
    """Parcourt les bougies des niveaux et renvoie les zones de chasse créées par les cassures."""
    tf_delta = pd.Timedelta(tf or p.level_tf)
    n = p.swing_n
    is_high, is_low = (s.to_numpy() for s in swing_points(bars, n))
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))
    a = atr(bars, p.atr_len).to_numpy()
    times = bars.index
    # Une ligne : valeur p à la bougie a, pente slope par bougie ; last = dernière touche.
    resistances: list[dict] = []
    supports: list[dict] = []
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []
    zones = []

    def value(line, b):
        return line["p"] + line["slope"] * (b - line["a"])

    for b in range(len(bars)):
        # Sommets et creux confirmés à la clôture de la bougie précédente.
        i = b - 1 - n
        if i >= 0 and is_high[i]:
            if p.use_trendlines and not np.isnan(a[i]):
                recent = [s for s in swing_highs if i - s[0] <= p.level_max_age]
                resistances += _new_trendlines(recent, i, h[i], p.touch_atr * a[i], c, side=1)
            resistances.append({"a": i, "p": h[i], "slope": 0.0, "last": i})
            swing_highs.append((i, h[i]))
        if i >= 0 and is_low[i]:
            if p.use_trendlines and not np.isnan(a[i]):
                recent = [s for s in swing_lows if i - s[0] <= p.level_max_age]
                supports += _new_trendlines(recent, i, l[i], p.touch_atr * a[i], c, side=-1)
            supports.append({"a": i, "p": l[i], "slope": 0.0, "last": i})
            swing_lows.append((i, l[i]))
        resistances = [r for r in resistances if b - r["last"] <= p.level_max_age]
        supports = [s for s in supports if b - s["last"] <= p.level_max_age]
        swing_highs = [s for s in swing_highs if b - s[0] <= p.level_max_age]
        swing_lows = [s for s in swing_lows if b - s[0] <= p.level_max_age]
        if np.isnan(a[b]):
            continue

        rng = h[b] - l[b]
        body = abs(c[b] - o[b])
        force_up = c[b] > o[b] and body >= p.force_body_atr * a[b] and rng > 0 and (h[b] - c[b]) <= p.force_close_frac * rng
        force_dn = c[b] < o[b] and body >= p.force_body_atr * a[b] and rng > 0 and (c[b] - l[b]) <= p.force_close_frac * rng

        # Premier passage d'une clôture au-delà de la ligne : cassure si bougie de force, sinon ligne morte.
        crossed = [r for r in resistances if c[b] > value(r, b)]
        resistances = [r for r in resistances if c[b] <= value(r, b)]
        if crossed and force_up:
            zones.append({"direction": 1, "line": max(crossed, key=lambda r: value(r, b)), "bar": b})
        crossed = [s for s in supports if c[b] < value(s, b)]
        supports = [s for s in supports if c[b] >= value(s, b)]
        if crossed and force_dn:
            zones.append({"direction": -1, "line": min(crossed, key=lambda s: value(s, b)), "bar": b})

    for z in zones:
        b, d, line = z["bar"], z["direction"], z["line"]
        z["level"] = value(line, b)
        z["anchor"], z["anchor_price"], z["slope"] = line["a"], line["p"], line["slope"]
        z["width"] = p.zone_atr * a[b]
        z["low"], z["high"] = z["level"] - z["width"], z["level"] + z["width"]
        z["breakout_open"] = times[b]
        z["start"] = times[b] + tf_delta
        last = min(b + p.pullback_bars, len(bars) - 1)
        end = times[last] + tf_delta
        # Fausse cassure : clôture de l'autre côté de la zone (prolongée si oblique).
        seg = np.arange(b + 1, last + 1)
        center = line["p"] + line["slope"] * (seg - line["a"])
        failed = np.flatnonzero(c[seg] < center - z["width"]) if d == 1 else np.flatnonzero(c[seg] > center + z["width"])
        if failed.size:
            end = times[seg[failed[0]]] + tf_delta
        z["end"] = end
        del z["line"]
    return zones


def generate_signals(m1: pd.DataFrame, p: Params) -> pd.DataFrame:
    levels = resample(m1, p.level_tf)
    m5 = resample(m1, "5min")
    zones = find_zones(levels, p)
    tf_delta = pd.Timedelta(p.level_tf)

    o, h, l, c = (m5[k].to_numpy() for k in ("open", "high", "low", "close"))
    rng = h - l
    body = np.abs(c - o)
    lower_wick = np.minimum(o, c) - l
    upper_wick = h - np.maximum(o, c)
    pin_up = (rng > 0) & (lower_wick >= p.pin_wick_body * body) & (lower_wick >= p.pin_wick_range * rng) & (c >= l + 2 / 3 * rng)
    pin_dn = (rng > 0) & (upper_wick >= p.pin_wick_body * body) & (upper_wick >= p.pin_wick_range * rng) & (c <= h - 2 / 3 * rng)

    tod = m5.index.hour * 60 + m5.index.minute
    in_window = (tod >= p.entry_start_hour * 60) & (tod < p.entry_end_hour * 60)

    if p.use_trend_filter:
        trend_tbl = swing_trend(trend_bars(m1, p.trend_tf), p.swing_n, p.trend_tf)
        close_times = pd.DataFrame({"time": m5.index + pd.Timedelta(minutes=5)})
        trend = pd.merge_asof(close_times, trend_tbl, on="time", direction="backward")["trend"].fillna(0).to_numpy()
    else:
        trend = None

    # Position de chaque bougie M5 en « numéro de bougie » des niveaux, pour prolonger les obliques.
    lvl_times = levels.index
    k_lvl = lvl_times.searchsorted(m5.index, side="right") - 1
    pos = np.asarray(k_lvl + (m5.index - lvl_times[np.maximum(k_lvl, 0)]) / tf_delta, dtype=float)

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
        center = z["anchor_price"] + z["slope"] * (pos[sl] - z["anchor"])
        lo_z, hi_z = center - z["width"], center + z["width"]
        if d == 1:
            ok = pin_up[sl] & (l[sl] <= hi_z) & (c[sl] > lo_z)
        else:
            ok = pin_dn[sl] & (h[sl] >= lo_z) & (c[sl] < hi_z)
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


# Plages de tirage pour le Monte-Carlo sur les paramètres (fixées avant le premier tirage).
PARAM_SPACE = {
    "swing_n": ("int", 2, 5),
    "force_body_atr": ("float", 0.4, 1.2),
    "zone_atr": ("float", 0.1, 0.4),
    "pullback_bars": ("int", 12, 48),
    "use_trend_filter": ("choice", [True, False]),
    "stop_buffer_pips": ("float", 1.0, 5.0),
    "min_target_r": ("float", 0.5, 2.0),
}
