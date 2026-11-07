"""Stratégie E : rééquilibrage de fin de mois au fixing de Londres (règles : docs/regles_fixing_fin_de_mois.md).

- Le dernier jour ouvré du mois, on compare la performance du mois du S&P 500 à celle de
  l'indice européen de la paire (DAX pour EUR/USD, FTSE 100 pour GBP/USD, SMI pour USD/CHF),
  jusqu'à la veille.
- Si le S&P 500 a fait mieux, les investisseurs européens vendent du dollar au fixing : on
  achète EUR/USD ou GBP/USD, on vend USD/CHF. Sinon, l'inverse.
- Entrée à 16h00 (Zurich), sortie à 17h00 au fixing, stop de protection à 0,5 × ATR journalier.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import data
from ..data import daily_bars
from .base import SIGNAL_COLUMNS, BaseParams
from .indicators import atr

US_INDEX = "^GSPC"
FOREIGN_INDEX = {"EURUSD": "^GDAXI", "GBPUSD": "^FTSE", "USDCHF": "^SSMI"}


@dataclass(frozen=True)
class Params(BaseParams):
    entry_time: str = "16:00"
    min_diff: float = 0.0  # écart minimal de performance (0.02 = 2 %)
    stop_atr: float = 0.5
    rr: float = 1000.0  # pas d'objectif : la sortie se fait au fixing
    atr_len: int = 14
    max_trades_per_day: int = 1
    max_consec_losses: int = 0
    flat_hour: int = 17


def month_to_date_return(closes: pd.Series, day: pd.Timestamp) -> float:
    """Performance depuis la dernière clôture du mois précédent jusqu'à la dernière clôture avant `day`."""
    before = closes[closes.index < day]
    ref = closes[closes.index < day.replace(day=1)]
    if before.empty or ref.empty:
        return np.nan
    return before.iloc[-1] / ref.iloc[-1] - 1


def last_trading_days(m1: pd.DataFrame, entry_time: str) -> pd.DatetimeIndex:
    """Dernier jour de semaine de chaque mois avec une cotation à l'heure d'entrée."""
    at_entry = m1.index[m1.index.strftime("%H:%M") == entry_time]
    days = pd.DatetimeIndex(at_entry.normalize().unique())
    days = days[days.day_of_week < 5]
    return pd.DatetimeIndex(pd.Series(days, index=days).groupby([days.year, days.month]).max().to_numpy())


def generate_signals(m1: pd.DataFrame, p: Params, pair: str | None = None) -> pd.DataFrame:
    if pair not in FOREIGN_INDEX:  # pas d'indice actions de référence (par exemple le BTC)
        return pd.DataFrame(columns=SIGNAL_COLUMNS)
    # Vente de dollar : achat de la paire si l'USD est la devise de cotation, vente s'il est la devise de base.
    usd_side = 1 if pair.endswith("USD") else -1
    us = data.load_index(US_INDEX)
    foreign = data.load_index(FOREIGN_INDEX[pair])
    d_atr = atr(daily_bars(m1), p.atr_len).shift(1)

    rows = []
    for day in last_trading_days(m1, p.entry_time):
        naive = day.tz_localize(None)
        diff = month_to_date_return(us, naive) - month_to_date_return(foreign, naive)
        a = d_atr.get(naive, np.nan)
        if np.isnan(diff) or np.isnan(a) or abs(diff) < max(p.min_diff, 1e-12):
            continue
        rows.append({
            "entry_time": day + pd.Timedelta(p.entry_time + ":00"),
            "direction": usd_side * (1 if diff > 0 else -1),  # S&P 500 devant : vente de dollar
            "stop_dist": p.stop_atr * a,
            "stop_level": np.nan,
            "rr": p.rr,
            "deadline": day + pd.Timedelta(hours=p.flat_hour),
            "day": day,
        })
    return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)


# Plages de tirage pour le Monte-Carlo sur les paramètres (fixées avant le premier tirage).
PARAM_SPACE = {
    "entry_time": ("choice", ["15:00", "15:30", "16:00", "16:30"]),
    "min_diff": ("float", 0.0, 0.03),
    "stop_atr": ("float", 0.3, 1.0),
}
