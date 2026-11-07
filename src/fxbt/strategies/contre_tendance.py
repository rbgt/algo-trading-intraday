"""Stratégie C : retour à la moyenne contre-tendance (règles : docs/regles_contre_tendance.md).

- Contexte (veille clôturée) : E = (clôture − EMA50 journalière) / ATR14 journalier.
  E ≥ +0,5 : ventes seulement ; E ≤ −0,5 : achats seulement ; sinon pas de trade.
- Déclencheur M15, bougies ouvertes entre 8h00 et 11h45 : la clôture passe sous l'EMA 20
  (vente) ou au-dessus (achat). Entrée à l'ouverture de la bougie suivante.
- Stop à 0,5 × ATR journalier (ignoré si moins de 20 pips), objectif à 1,5R, sortie forcée à 17h.
- Un trade par jour au maximum.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import daily_bars, resample
from ..engine import SIGNAL_COLUMNS, BaseParams
from ..indicators import atr, ema


@dataclass(frozen=True)
class Params(BaseParams):
    tf: str = "15min"
    ema_intraday: int = 20
    daily_ema: int = 50
    atr_len: int = 14
    stretch: float = 0.5
    stop_atr: float = 0.5
    rr: float = 1.5
    entry_start_hour: int = 8
    entry_end_hour: int = 12
    max_trades_per_day: int = 1
    max_consec_losses: int = 0
    flat_hour: int = 17
    min_stop_pips: float = 20.0


def generate_signals(m1: pd.DataFrame, p: Params) -> pd.DataFrame:
    bars = resample(m1, p.tf)
    day = bars.index.normalize()
    tod = bars.index.hour * 60 + bars.index.minute

    # Valeurs de la veille, indexées par date de trading.
    # Entre 8h et 12h à Zurich, la date de trading (clôture 17h à New York) est la date du jour.
    daily = daily_bars(m1)
    d_atr = atr(daily, p.atr_len).shift(1)
    stretch = ((daily["close"] - ema(daily["close"], p.daily_ema)) / atr(daily, p.atr_len)).shift(1)
    trade_date = day.tz_localize(None)
    e = stretch.reindex(trade_date).to_numpy()
    a = d_atr.reindex(trade_date).to_numpy()

    close = bars["close"]
    ema_i = ema(close, p.ema_intraday)
    cross_up = ((close > ema_i) & (close.shift(1) <= ema_i.shift(1))).to_numpy()
    cross_dn = ((close < ema_i) & (close.shift(1) >= ema_i.shift(1))).to_numpy()
    in_window = (tod >= p.entry_start_hour * 60) & (tod < p.entry_end_hour * 60)

    long_ = in_window & (e <= -p.stretch) & cross_up
    short = in_window & (e >= p.stretch) & cross_dn

    next_open = pd.Series(bars.index, index=bars.index).shift(-1)
    valid = next_open.notna().to_numpy() & (next_open.dt.normalize().to_numpy() == day.to_numpy())
    mask = (long_ | short) & valid & ~np.isnan(a)

    return pd.DataFrame({
        "entry_time": next_open[mask].to_numpy(),
        "direction": np.where(long_[mask], 1, -1),
        "stop_dist": p.stop_atr * a[mask],
        "stop_level": np.nan,
        "rr": p.rr,
        "deadline": (day + pd.Timedelta(hours=p.flat_hour))[mask],
        "day": day[mask],
    })[SIGNAL_COLUMNS]
