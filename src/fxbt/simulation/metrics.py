"""Mesures de performance, en R et en EUR."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _max_drawdown(curve: np.ndarray, start: float) -> float:
    curve = np.concatenate([[start], curve])
    return float((np.maximum.accumulate(curve) - curve).max())


def summarize(trades: pd.DataFrame, capital: float) -> dict:
    if trades.empty:
        return {"trades": 0}
    r = trades["r"].to_numpy()
    gains, pertes = r[r > 0].sum(), -r[r < 0].sum()
    equity = trades["equity"].to_numpy()
    peak = np.maximum.accumulate(np.concatenate([[capital], equity]))
    dd_pct = float(((peak - np.concatenate([[capital], equity])) / peak).max() * 100)
    return {
        "trades": len(r),
        "réussite_%": round(float((r > 0).mean() * 100), 1),
        "R_moyen": round(float(r.mean()), 3),
        "R_total": round(float(r.sum()), 1),
        "profit_factor": round(float(gains / pertes), 2) if pertes > 0 else np.inf,
        "DD_max_R": round(_max_drawdown(np.cumsum(r), 0.0), 1),
        "DD_max_%": round(dd_pct, 1),
        "capital_final": round(float(equity[-1]), 2),
        "risque_moyen_%": round(float((trades["risk_eur"] / (trades["equity"] - trades["pnl_eur"])).mean() * 100), 2),
    }


def by_year(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    g = trades.groupby(trades["entry_time"].dt.year)["r"]
    out = pd.DataFrame({
        "trades": g.size(),
        "réussite_%": (g.apply(lambda r: (r > 0).mean()) * 100).round(1),
        "R_moyen": g.mean().round(3),
        "R_total": g.sum().round(1),
    })
    out.index.name = "année"
    return out
