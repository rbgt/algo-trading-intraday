"""Stratégie F : poursuite après une surprise macroéconomique (règles : docs/regles_surprise_annonces.md).

- Surprise normalisée : z = (réel − consensus) / écart-type des 20 surprises précédentes du même
  événement, orientée pour que z > 0 soit toujours bon pour la devise.
- Les z d'une même devise publiés à la même minute s'additionnent. Pour une paire, le score est
  z(devise de base) − z(devise de cotation) : positif, on achète la paire.
- Signal si |score| ≥ 1, pour une annonce entre 8h00 et 16h15. Entrée 15 minutes après, sortie à 17h00,
  stop de protection à 0,5 × ATR journalier.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import economic_calendar
from ..data import daily_bars
from .base import SIGNAL_COLUMNS, BaseParams
from .indicators import atr


@dataclass(frozen=True)
class Params(BaseParams):
    z_threshold: float = 1.0
    lookback: int = 20  # surprises passées pour l'écart-type
    min_history: int = 8
    entry_delay_min: int = 15
    exit_after_min: int = 0  # 0 = sortie à flat_hour ; sinon N minutes après l'entrée (au plus tard flat_hour)
    confirm_initial_move: bool = False
    stop_atr: float = 0.5
    rr: float = 1000.0  # pas d'objectif : sortie à l'heure
    first_event: str = "08:00"
    last_event: str = "16:15"
    atr_len: int = 14
    max_trades_per_day: int = 2
    max_consec_losses: int = 2
    flat_hour: int = 17


def surprise_scores(cal: pd.DataFrame, lookback: int, min_history: int) -> pd.DataFrame:
    """Surprises normalisées et orientées (z > 0 : bon pour la devise), additionnées par devise et par minute."""
    cal = cal[(cal["effect"] != 0) & cal["actual_value"].notna() & cal["forecast_value"].notna()].copy()
    cal["surprise"] = cal["actual_value"] - cal["forecast_value"]
    cal = cal.sort_values("time")
    # Écart-type des surprises précédentes du même événement (sans l'annonce en cours).
    scale = cal.groupby(["currency", "event"])["surprise"].transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=min_history).std())
    cal["z"] = cal["surprise"] / scale.replace(0, np.nan) * cal["effect"]
    cal = cal.dropna(subset=["z"])
    return cal.groupby(["time", "currency"], as_index=False)["z"].sum()


def generate_signals(m1: pd.DataFrame, p: Params, pair: str | None = None) -> pd.DataFrame:
    base, quote = pair[:3], pair[3:]
    scores = surprise_scores(economic_calendar.load_calendar(), p.lookback, p.min_history)
    scores = scores[scores["currency"].isin([base, quote])]
    # Score de la paire : bon pour la devise de base → achat ; bon pour la devise de cotation → vente.
    scores["signed"] = np.where(scores["currency"] == base, scores["z"], -scores["z"])
    by_time = scores.groupby("time")["signed"].sum()

    tod = by_time.index.strftime("%H:%M")
    by_time = by_time[(tod >= p.first_event) & (tod <= p.last_event) & (by_time.abs() >= p.z_threshold)]
    by_time = by_time[(by_time.index >= m1.index[0]) & (by_time.index <= m1.index[-1])]

    d_atr = atr(daily_bars(m1), p.atr_len).shift(1)
    opens = m1["open"]
    rows = []
    for event_time, score in by_time.items():
        day = event_time.normalize()
        entry = event_time.floor("min") + pd.Timedelta(minutes=p.entry_delay_min)
        flat = day + pd.Timedelta(hours=p.flat_hour)
        deadline = flat if not p.exit_after_min else min(flat, entry + pd.Timedelta(minutes=p.exit_after_min))
        a = d_atr.get(day.tz_localize(None), np.nan)
        if entry >= deadline or np.isnan(a):
            continue
        direction = 1 if score > 0 else -1
        if p.confirm_initial_move:
            # Mouvement entre l'annonce et l'entrée : doit aller dans le sens de la surprise.
            i0, i1 = opens.index.searchsorted(event_time), opens.index.searchsorted(entry)
            if i1 >= len(opens) or i0 >= i1 or np.sign(opens.iloc[i1] - opens.iloc[i0]) != direction:
                continue
        rows.append({
            "entry_time": entry,
            "direction": direction,
            "stop_dist": p.stop_atr * a,
            "stop_level": np.nan,
            "rr": p.rr,
            "deadline": deadline,
            "day": day,
        })
    return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)


# Plages de tirage pour le Monte-Carlo sur les paramètres (fixées avant le premier tirage).
PARAM_SPACE = {
    "z_threshold": ("float", 0.5, 2.0),
    "entry_delay_min": ("int", 5, 30),
    "exit_after_min": ("choice", [0, 60, 120, 240]),
    "stop_atr": ("float", 0.3, 1.0),
    "confirm_initial_move": ("choice", [False, True]),
}
