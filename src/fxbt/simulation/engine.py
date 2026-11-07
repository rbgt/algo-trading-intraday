"""Moteur de simulation des trades sur bougies M1.

Une stratégie produit des *signaux candidats* (format décrit dans strategies/base.py). Le moteur les parcourt dans
l'ordre chronologique et applique les règles communes :
- une seule position à la fois,
- limites par jour (nombre de trades, pertes consécutives),
- taille selon le risque, plafonnée par le levier, capital composé,
- sortie sur stop, objectif ou heure limite, résolue en M1 :
  stop compté d'abord si les deux sont touchés dans la même minute,
- coût aller-retour fixe en pips (spread et glissement),
- en option, pas d'entrée autour des annonces à fort impact (filtre d'annonces).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import pandas as pd

from ..data import INSTRUMENTS, cost_in_price, pip_size
from ..strategies.base import BaseParams

@dataclass(frozen=True)
class Account:
    capital: float = 100.0
    risk_pct: float = 1.0
    max_leverage: float = 5.0
    margin_buffer: float = 0.98
    lot_step: float = 1


def account_for(pair: str, capital: float = 100.0, lot_step: float | None = None) -> Account:
    """Compte de Rick (1 % de risque) avec le levier maximal et la taille minimale de l'instrument."""
    inst = INSTRUMENTS.get(pair)
    if inst is None:
        return Account(capital=capital, lot_step=lot_step or 1)
    return Account(capital=capital, max_leverage=min(5.0, inst.max_leverage), lot_step=lot_step or inst.lot_step)


class Bars(NamedTuple):
    times: np.ndarray  # int64, nanosecondes
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray


def to_bars(m1: pd.DataFrame) -> Bars:
    return Bars(
        m1.index.as_unit("ns").asi8,
        m1["open"].to_numpy(float),
        m1["high"].to_numpy(float),
        m1["low"].to_numpy(float),
        m1["close"].to_numpy(float),
    )


class Converter:
    """Taux de change vers l'EUR, à partir des clôtures M1 disponibles."""

    def __init__(self, closes: dict[str, pd.Series]):
        self._series = {p: (s.index.as_unit("ns").asi8, s.to_numpy(float)) for p, s in closes.items()}

    def _asof(self, pair: str, t: int) -> float:
        times, values = self._series[pair]
        i = np.searchsorted(times, t, side="right") - 1
        return float(values[max(i, 0)])

    def _to_usd(self, ccy: str, t: int) -> float:
        if ccy == "USD":
            return 1.0
        if f"{ccy}USD" in self._series:
            return self._asof(f"{ccy}USD", t)
        if f"USD{ccy}" in self._series:
            return 1.0 / self._asof(f"USD{ccy}", t)
        raise ValueError(f"Conversion vers EUR impossible pour {ccy} : charger {ccy}USD ou USD{ccy}")

    def to_eur(self, ccy: str, t: int) -> float:
        if ccy == "EUR":
            return 1.0
        return self._to_usd(ccy, t) / self._asof("EURUSD", t)


_NS_MIN = 60_000_000_000
_MAX_ENTRY_DELAY = 5 * _NS_MIN
_MAX_EXIT_DELAY = 60 * _NS_MIN


def near_news(news_times: np.ndarray | None, t: int, window_min: int) -> bool:
    """Vrai si une annonce tombe à moins de window_min minutes de t (avant ou après)."""
    if news_times is None or not len(news_times):
        return False
    i = int(np.searchsorted(news_times, t))
    window = window_min * _NS_MIN
    return (i < len(news_times) and news_times[i] - t <= window) or (i > 0 and t - news_times[i - 1] <= window)


def resolve_exit(b: Bars, i0: int, i1: int, d: int, stop: float, target: float, deadline: int):
    """Cherche la sortie entre les minutes i0 (incluse) et i1 (exclue).

    Retourne (indice de la minute de sortie, prix, motif).
    """
    o, h, l = b.open[i0:i1], b.high[i0:i1], b.low[i0:i1]
    hit_s = l <= stop if d == 1 else h >= stop
    hit_t = h >= target if d == 1 else l <= target
    n = i1 - i0
    js = int(np.argmax(hit_s)) if hit_s.any() else n
    jt = int(np.argmax(hit_t)) if hit_t.any() else n

    if js == n and jt == n:
        # Sortie forcée à l'ouverture de la minute de l'heure limite, sinon à la dernière clôture connue.
        if i1 < len(b.times) and b.times[i1] - deadline <= _MAX_EXIT_DELAY:
            return i1, float(b.open[i1]), "time"
        return i1 - 1, float(b.close[i1 - 1]), "time"

    opens_past_target = jt < n and (o[jt] >= target if d == 1 else o[jt] <= target)
    if jt < js or (jt == js and opens_past_target):
        # Ordre limite : exécuté au mieux si la minute ouvre déjà au-delà.
        price = max(target, o[jt]) if d == 1 else min(target, o[jt])
        return i0 + jt, float(price), "target"
    # Stop : exécuté à l'ouverture si la minute ouvre au-delà (gap).
    price = min(stop, o[js]) if d == 1 else max(stop, o[js])
    return i0 + js, float(price), "stop"


def run(
    signals: pd.DataFrame,
    m1: pd.DataFrame,
    pair: str,
    params: BaseParams,
    account: Account,
    cost: float,  # coût aller-retour dans l'unité de l'instrument (pips, ou % du prix)
    converter: Converter,
    news_times: np.ndarray | None = None,
    news_window_min: int = 0,
) -> pd.DataFrame:
    """Simule les signaux. news_times : heures des annonces (int64, ns, triées) ; aucune entrée à moins
    de news_window_min minutes avant ou après l'une d'elles."""
    b = to_bars(m1)
    pip = pip_size(pair)
    base, quote = pair[:3], pair[3:]
    equity = account.capital
    busy_until = -1
    cur_day = None
    n_today = losses = 0
    rows = []

    for s in signals.sort_values("entry_time").itertuples(index=False):
        t = s.entry_time.as_unit("ns").value
        if t <= busy_until:
            continue
        if news_window_min and near_news(news_times, t, news_window_min):
            continue
        if s.day != cur_day:
            cur_day, n_today, losses = s.day, 0, 0
        if n_today >= params.max_trades_per_day:
            continue
        if params.max_consec_losses and losses >= params.max_consec_losses:
            continue

        i0 = int(np.searchsorted(b.times, t, side="left"))
        if i0 >= len(b.times) or b.times[i0] - t > _MAX_ENTRY_DELAY:
            continue
        deadline = s.deadline.as_unit("ns").value
        i1 = int(np.searchsorted(b.times, deadline, side="left"))
        if i1 <= i0:
            continue

        d = int(s.direction)
        entry = float(b.open[i0])
        dist = s.stop_dist if not math.isnan(s.stop_dist) else d * (entry - s.stop_level)
        if not dist > 0 or dist / pip < params.min_stop_pips:
            continue
        stop = entry - d * dist
        target_level = getattr(s, "target_level", math.nan)
        if math.isnan(target_level):
            target = entry + d * s.rr * dist
        elif d * (target_level - entry) >= max(params.min_target_r * dist, 1e-12):
            target = target_level
        else:
            continue

        quote_eur = converter.to_eur(quote, t)
        base_eur = converter.to_eur(base, t)
        raw_units = equity * account.risk_pct / 100 / (dist * quote_eur)
        cap_units = equity * account.max_leverage * account.margin_buffer / base_eur
        units = math.floor(min(raw_units, cap_units) / account.lot_step) * account.lot_step
        if units <= 0:
            continue

        j, exit_px, reason = resolve_exit(b, i0, i1, d, stop, target, deadline)
        move = d * (exit_px - entry) - cost_in_price(pair, cost, entry)
        pnl = move * units * quote_eur  # conversion au taux d'entrée
        equity += pnl
        n_today += 1
        losses = losses + 1 if pnl < 0 else 0
        busy_until = int(b.times[j])

        rows.append({
            "pair": pair,
            "direction": d,
            "entry_time": s.entry_time,
            "exit_time": pd.Timestamp(b.times[j], tz="UTC").tz_convert(m1.index.tz),
            "entry": entry,
            "exit": exit_px,
            "stop": stop,
            "target": target,
            "stop_pips": dist / pip,
            "reason": reason,
            "r": move / dist,
            "units": units,
            "risk_eur": dist * units * quote_eur,
            "pnl_eur": pnl,
            "equity": equity,
        })

    return pd.DataFrame(rows)
