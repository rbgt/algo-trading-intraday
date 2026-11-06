"""Indicateurs, calculés comme dans TradingView (lissage de Wilder pour RSI et ATR)."""

from __future__ import annotations

import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Moyenne de Wilder, équivalente à ta.rma."""
    return s.ewm(alpha=1 / n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = rma(delta.clip(lower=0), n)
    down = rma(-delta.clip(upper=0), n)
    return 100 - 100 / (1 + up / down)


def atr(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [bars["high"] - bars["low"], (bars["high"] - prev_close).abs(), (bars["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return rma(tr, n)
