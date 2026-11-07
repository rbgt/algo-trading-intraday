"""Stratégie A : EMA Breakout (signal M5, tendance M15).

- Tendance M15 (dernière bougie clôturée) : clôture > EMA20 > EMA50 pour un achat, l'inverse pour une vente.
- Signal M5 : la clôture repasse au-dessus de l'EMA20 (achat) ou en dessous (vente).
- RSI 14 M5 dans [50, 70] pour un achat, dans [30, 50] pour une vente.
- Entrée à l'ouverture de la bougie M5 suivante. Stop à 1,5 × ATR14 M5, objectif à 2R.
- Signaux sur les bougies ouvertes entre 8h et 12h. Au maximum 3 trades par jour,
  arrêt après 2 pertes consécutives, sortie forcée à 17h.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import resample
from ..engine import SIGNAL_COLUMNS, BaseParams
from ..indicators import atr, ema, rsi


@dataclass(frozen=True)
class Params(BaseParams):
    signal_tf: str = "5min"
    trend_tf: str = "15min"
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_len: int = 14
    rsi_long_min: float = 50.0
    rsi_long_max: float = 70.0
    rsi_short_min: float = 30.0
    rsi_short_max: float = 50.0
    atr_len: int = 14
    atr_mult: float = 1.5
    rr: float = 2.0
    entry_start_hour: int = 8
    entry_end_hour: int = 12
    max_trades_per_day: int = 3
    max_consec_losses: int = 2
    flat_hour: int = 17


def generate_signals(m1: pd.DataFrame, p: Params) -> pd.DataFrame:
    sig = resample(m1, p.signal_tf)
    trend = resample(m1, p.trend_tf)

    # Tendance : la dernière bougie de l'unité de temps tendance clôturée au plus tard
    # à la clôture de la bougie signal.
    t_fast, t_slow = ema(trend["close"], p.ema_fast), ema(trend["close"], p.ema_slow)
    t_dir = np.select(
        [(trend["close"] > t_fast) & (t_fast > t_slow), (trend["close"] < t_fast) & (t_fast < t_slow)],
        [1, -1],
        0,
    )
    left = pd.DataFrame({"close_time": sig.index + pd.Timedelta(p.signal_tf)})
    right = pd.DataFrame({"close_time": trend.index + pd.Timedelta(p.trend_tf), "trend": t_dir})
    trend_dir = pd.merge_asof(left, right, on="close_time", direction="backward")["trend"].fillna(0).to_numpy()

    close = sig["close"]
    e = ema(close, p.ema_fast)
    cross_up = ((close > e) & (close.shift(1) <= e.shift(1))).to_numpy()
    cross_dn = ((close < e) & (close.shift(1) >= e.shift(1))).to_numpy()
    r = rsi(close, p.rsi_len).to_numpy()
    a = atr(sig, p.atr_len).to_numpy()

    tod = sig.index.hour * 60 + sig.index.minute
    in_window = (tod >= p.entry_start_hour * 60) & (tod < p.entry_end_hour * 60)

    long_ = in_window & (trend_dir == 1) & cross_up & (r >= p.rsi_long_min) & (r <= p.rsi_long_max)
    short = in_window & (trend_dir == -1) & cross_dn & (r >= p.rsi_short_min) & (r <= p.rsi_short_max)

    # Entrée à l'ouverture de la bougie suivante, le même jour.
    next_open = pd.Series(sig.index, index=sig.index).shift(-1)
    day = sig.index.normalize()
    deadline = day + pd.Timedelta(hours=p.flat_hour)
    valid = next_open.notna().to_numpy() & (next_open.dt.normalize().to_numpy() == day.to_numpy())
    mask = (long_ | short) & valid & ~np.isnan(a)

    return pd.DataFrame({
        "entry_time": next_open[mask].to_numpy(),
        "direction": np.where(long_[mask], 1, -1),
        "stop_dist": p.atr_mult * a[mask],
        "stop_level": np.nan,
        "rr": p.rr,
        "deadline": deadline[mask],
        "day": day[mask],
    })[SIGNAL_COLUMNS]


# Plages de tirage pour le Monte-Carlo sur les paramètres (fixées avant le premier tirage).
PARAM_SPACE = {
    "trend_tf": ("choice", ["15min", "30min", "1h"]),
    "ema_fast": ("int", 10, 30),
    "ema_slow": ("int", 40, 100),
    "atr_mult": ("float", 1.0, 3.0),
    "rr": ("float", 1.0, 3.0),
    "entry_end_hour": ("int", 10, 12),
}
