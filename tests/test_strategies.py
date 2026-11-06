import numpy as np
import pandas as pd

from fxbt.strategies import london_breakout

TZ = "Europe/Zurich"


def synthetic_m1(days=30, seed=0):
    """Marche aléatoire M1, du lundi au vendredi."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-06", periods=days * 1440, freq="1min", tz=TZ)
    idx = idx[idx.day_of_week < 5]
    close = 1.10 + np.cumsum(rng.normal(0, 0.00005, len(idx)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    spread = np.abs(rng.normal(0, 0.00003, len(idx)))
    return pd.DataFrame({
        "open": open_,
        "high": np.maximum(open_, close) + spread,
        "low": np.minimum(open_, close) - spread,
        "close": close,
        "volume": 1.0,
    }, index=idx)


def test_london_signals_respect_rules():
    m1 = synthetic_m1()
    p = london_breakout.Params(min_ratio=0.0, max_ratio=10.0)
    sig = london_breakout.generate_signals(m1, p)
    assert len(sig) > 0
    tod = sig["entry_time"].dt.hour * 60 + sig["entry_time"].dt.minute
    # Signal sur une clôture entre 8h et 10h45, donc entrée entre 8h15 et 11h.
    assert tod.between(8 * 60 + 15, 11 * 60).all()

    # Vérification à la main d'un signal : la clôture précédente croise la zone asiatique.
    s = sig.iloc[0]
    day = m1[m1.index.normalize() == s["day"]]
    asia = day[day.index.hour < 7]
    bar = day.resample("15min").agg({"close": "last"}).loc[s["entry_time"] - pd.Timedelta("15min")]
    level = asia["high"].max() if s["direction"] == 1 else asia["low"].min()
    assert (bar["close"] - level) * s["direction"] > 0
    assert np.isclose(s["stop_level"], (asia["high"].max() + asia["low"].min()) / 2)
