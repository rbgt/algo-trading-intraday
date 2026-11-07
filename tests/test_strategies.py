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
    }, index=pd.DatetimeIndex(idx, name="time"))


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


def test_ema_signals_respect_rules():
    from fxbt.strategies import ema_breakout

    m1 = synthetic_m1(days=60, seed=1)
    p = ema_breakout.Params()
    sig = ema_breakout.generate_signals(m1, p)
    assert len(sig) > 0
    tod = sig["entry_time"].dt.hour * 60 + sig["entry_time"].dt.minute
    # Signal sur une bougie M5 ouverte entre 8h et 11h55, donc entrée entre 8h05 et 12h.
    assert tod.between(8 * 60 + 5, 12 * 60).all()
    assert (sig["stop_dist"] > 0).all() and sig["stop_level"].isna().all()


def test_contre_tendance_trades_against_daily_stretch():
    from fxbt.data import daily_bars
    from fxbt.indicators import atr, ema
    from fxbt.strategies import contre_tendance

    m1 = synthetic_m1(days=200, seed=2)
    p = contre_tendance.Params(min_stop_pips=0)
    sig = contre_tendance.generate_signals(m1, p)
    assert len(sig) > 0
    tod = sig["entry_time"].dt.hour * 60 + sig["entry_time"].dt.minute
    assert tod.between(8 * 60 + 15, 12 * 60).all()

    # Vérification à la main : la vente suit une veille étirée vers le haut, l'achat l'inverse.
    daily = daily_bars(m1)
    e = ((daily["close"] - ema(daily["close"], 50)) / atr(daily, 14)).shift(1)
    a = atr(daily, 14).shift(1)
    for s in sig.itertuples():
        d = s.day.tz_localize(None)
        assert (e[d] >= 0.5) if s.direction == -1 else (e[d] <= -0.5)
        assert np.isclose(s.stop_dist, 0.5 * a[d])


def h1_frame(rows):
    idx = pd.date_range("2020-03-02 00:00", periods=len(rows), freq="1h", tz=TZ)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


def test_breakout_zone_needs_force_candle_and_kills_weak_crossings():
    from fxbt.strategies import breakout_price_action as bpa

    # 20 bougies calmes pour l'ATR, un sommet à 1.1050 (bougie 22), puis une cassure.
    calm = [(1.1000, 1.1010, 1.0990, 1.1000)] * 20
    swing = [(1.1000, 1.1020, 1.0995, 1.1015), (1.1015, 1.1030, 1.1010, 1.1025),
             (1.1025, 1.1050, 1.1020, 1.1030), (1.1030, 1.1035, 1.1010, 1.1015),
             (1.1015, 1.1020, 1.1000, 1.1005), (1.1005, 1.1010, 1.0995, 1.1000)]
    force = [(1.1000, 1.1072, 1.0998, 1.1070)]   # corps de 70 pips, clôture près du plus haut
    weak = [(1.1040, 1.1080, 1.1000, 1.1055)]    # clôture au-dessus, mais corps faible
    p = bpa.Params(swing_n=2, atr_len=5)

    zones = bpa.find_zones(h1_frame(calm + swing + force + calm[:3]), p)
    up = [z for z in zones if z["direction"] == 1 and z["level"] == 1.1050]
    assert len(up) == 1 and up[0]["bar"] == 26
    assert np.isclose(up[0]["high"] - up[0]["level"], up[0]["level"] - up[0]["low"])

    zones = bpa.find_zones(h1_frame(calm + swing + weak + force + calm[:3]), p)
    # La bougie faible a tué le niveau : la bougie de force suivante ne crée pas de zone à 1.1050.
    assert not [z for z in zones if z["direction"] == 1 and z["level"] == 1.1050]


def test_breakout_signals_invariants():
    from fxbt.strategies import breakout_price_action as bpa

    m1 = synthetic_m1(days=150, seed=3)
    p = bpa.Params(force_body_atr=0.3)
    sig = bpa.generate_signals(m1, p)
    assert len(sig) > 0
    tod = sig["entry_time"].dt.hour * 60 + sig["entry_time"].dt.minute
    assert tod.between(8 * 60 + 5, 12 * 60).all()
    m5 = m1.resample("5min").agg({"high": "max", "low": "min"})
    for s in sig.itertuples():
        pin = m5.loc[s.entry_time - pd.Timedelta("5min")]
        if s.direction == 1:
            assert np.isclose(s.stop_level, pin["low"] - 0.0002) and s.target_level >= pin["high"]
        else:
            assert np.isclose(s.stop_level, pin["high"] + 0.0002) and s.target_level <= pin["low"]


def test_trendline_with_three_touches_creates_sloped_zone():
    from fxbt.strategies import breakout_price_action as bpa

    rows = [(1.1000, 1.1010, 1.0990, 1.1000)] * 45
    for i, peak in ((22, 1.1060), (28, 1.1050), (34, 1.1040)):  # 3 sommets alignés, pente −10 pips / 6 bougies
        rows[i] = (1.1000, peak, 1.0995, 1.1005)
    rows[40] = (1.1000, 1.1036, 1.0999, 1.1035)  # cassure de l'oblique (≈ 1.1030 ici), sous l'horizontale 1.1040
    p = bpa.Params(swing_n=2, atr_len=5, use_trendlines=True)

    zones = bpa.find_zones(h1_frame(rows), p, tf="1h")
    up = [z for z in zones if z["direction"] == 1 and z["bar"] == 40]
    assert len(up) == 1
    assert np.isclose(up[0]["slope"], -0.0010 / 6) and np.isclose(up[0]["level"], 1.1030)

    # Sans les obliques, la même bougie ne casse que les petits niveaux à 1.1010.
    zones = bpa.find_zones(h1_frame(rows), bpa.Params(swing_n=2, atr_len=5), tf="1h")
    assert all(z["level"] < 1.102 for z in zones if z["bar"] == 40)
