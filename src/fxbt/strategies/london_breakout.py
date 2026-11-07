"""Stratégie B : London Breakout v2 (cassure de la zone asiatique, M15).

- Zone asiatique : plus haut et plus bas des bougies M15 ouvertes entre 00h00 et 07h00 (Zurich).
- Filtre : taille de la zone entre 0,15 et 0,60 × ATR14 journalier (celui de la veille).
- Entrée entre 8h et 11h : première clôture M15 qui croise au-dessus du haut (achat)
  ou en dessous du bas (vente). Entrée à l'ouverture suivante, un seul trade par jour.
- Stop au milieu de la zone, objectif à 1,5R, sortie forcée à 17h.
- Filtre de tendance optionnel : EMA 50 journalière de la veille (désactivé par défaut).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import daily_bars, resample
from .base import SIGNAL_COLUMNS, BaseParams
from .indicators import atr, ema


@dataclass(frozen=True)
class Params(BaseParams):
    tf: str = "15min"
    asia_start_hour: int = 0
    asia_end_hour: int = 7
    entry_start_hour: int = 8
    entry_end_hour: int = 11
    atr_len: int = 14
    min_ratio: float = 0.15
    max_ratio: float = 0.60
    rr: float = 1.5
    use_trend: bool = False
    trend_ema: int = 50
    min_asia_bars: int = 20  # garde-fou contre les trous de données (28 bougies attendues)
    max_trades_per_day: int = 1
    max_consec_losses: int = 0
    flat_hour: int = 17


def generate_signals(m1: pd.DataFrame, p: Params, pair: str | None = None) -> pd.DataFrame:
    bars = resample(m1, p.tf)
    day = bars.index.normalize()
    tod = bars.index.hour * 60 + bars.index.minute

    asia = bars[(tod >= p.asia_start_hour * 60) & (tod < p.asia_end_hour * 60)]
    zone = asia.groupby(asia.index.normalize()).agg(
        hi=("high", "max"), lo=("low", "min"), n=("open", "size")
    )

    # Valeurs journalières de la veille, indexées par date de trading.
    # À 8h à Zurich, la date de trading (clôture 17h à New York) est la date du jour.
    daily = daily_bars(m1)
    d_atr = atr(daily, p.atr_len).shift(1)
    d_ema = ema(daily["close"], p.trend_ema).shift(1)
    trade_date = zone.index.tz_localize(None)
    zone["atr"] = d_atr.reindex(trade_date).to_numpy()
    zone["ema"] = d_ema.reindex(trade_date).to_numpy()
    ratio = (zone["hi"] - zone["lo"]) / zone["atr"]
    zone["ok"] = (ratio >= p.min_ratio) & (ratio <= p.max_ratio) & (zone["n"] >= p.min_asia_bars)

    z = zone.reindex(day)
    hi, lo = z["hi"].to_numpy(), z["lo"].to_numpy()
    ok = z["ok"].eq(True).to_numpy()
    close = bars["close"].to_numpy()
    prev_close = bars["close"].shift(1).to_numpy()

    cross_up = (close > hi) & (prev_close <= hi)
    cross_dn = (close < lo) & (prev_close >= lo)
    in_window = (tod >= p.entry_start_hour * 60) & (tod < p.entry_end_hour * 60)
    if p.use_trend:
        trend_long, trend_short = close > z["ema"].to_numpy(), close < z["ema"].to_numpy()
    else:
        trend_long = trend_short = np.ones(len(bars), bool)

    long_ = in_window & ok & cross_up & trend_long
    short = in_window & ok & cross_dn & trend_short

    next_open = pd.Series(bars.index, index=bars.index).shift(-1)
    valid = next_open.notna().to_numpy() & (next_open.dt.normalize().to_numpy() == day.to_numpy())
    mask = (long_ | short) & valid

    return pd.DataFrame({
        "entry_time": next_open[mask].to_numpy(),
        "direction": np.where(long_[mask], 1, -1),
        "stop_dist": np.nan,
        "stop_level": ((hi + lo) / 2)[mask],
        "rr": p.rr,
        "deadline": (day + pd.Timedelta(hours=p.flat_hour))[mask],
        "day": day[mask],
    })[SIGNAL_COLUMNS]


# Plages de tirage pour le Monte-Carlo sur les paramètres (fixées avant le premier tirage).
PARAM_SPACE = {
    "asia_end_hour": ("int", 6, 7),
    "entry_end_hour": ("int", 9, 12),
    "min_ratio": ("float", 0.05, 0.30),
    "max_ratio": ("float", 0.40, 1.00),
    "rr": ("float", 1.0, 3.0),
    "use_trend": ("choice", [False, True]),
}
