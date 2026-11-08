import numpy as np
import pandas as pd

from fxbt.strategies import london_breakout, smc, smc_ob

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
    from fxbt.strategies.indicators import atr, ema
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


def test_fixing_direction_follows_equity_performance_gap(monkeypatch):
    from fxbt import data
    from fxbt.strategies import fixing_fin_de_mois as fx

    m1 = synthetic_m1(days=120, seed=4)
    dates = pd.bdate_range("2019-12-02", "2020-04-30")
    # S&P 500 en hausse régulière, DAX plat : le S&P fait mieux chaque mois → achat d'EUR/USD.
    indices = {"^GSPC": pd.Series(np.linspace(100, 130, len(dates)), index=dates),
               "^GDAXI": pd.Series(100.0, index=dates)}
    monkeypatch.setattr(data, "load_index", lambda s: indices[s])

    sig = fx.generate_signals(m1, fx.Params(), "EURUSD")
    assert len(sig) >= 3 and (sig["direction"] == 1).all()
    assert (sig["entry_time"].dt.strftime("%H:%M") == "16:00").all()
    assert (sig["deadline"].dt.strftime("%H:%M") == "17:00").all()
    # Un signal par mois, le dernier jour de semaine du mois.
    assert sig["day"].dt.strftime("%Y-%m").is_unique
    assert ((sig["day"] + pd.offsets.BDay(1)).dt.month != sig["day"].dt.month).all()

    indices["^GSPC"] = pd.Series(np.linspace(130, 100, len(dates)), index=dates)
    assert (fx.generate_signals(m1, fx.Params(), "EURUSD")["direction"] == -1).all()


def test_month_to_date_return_uses_only_past_closes():
    from fxbt.strategies.fixing_fin_de_mois import month_to_date_return

    closes = pd.Series([100.0, 110.0, 121.0, 999.0], index=pd.to_datetime(["2020-01-31", "2020-02-27", "2020-02-28", "2020-02-29"]))
    # Signal le 28 février : référence = 31 janvier, dernière clôture connue = 27 février.
    assert np.isclose(month_to_date_return(closes, pd.Timestamp("2020-02-28")), 0.10)


def test_surprise_direction_per_pair(monkeypatch):
    from fxbt import economic_calendar
    from fxbt.strategies import surprise_annonces as sa

    m1 = synthetic_m1(days=120, seed=5)
    days = pd.bdate_range("2020-01-06", periods=60, tz=TZ)
    rows = []
    for i, d in enumerate(days):
        # Une annonce USD à 14h30 et une annonce EUR à 10h00 chaque jour ; la dernière de chaque est une grosse surprise.
        big = 4 if i == len(days) - 1 else (1 if i % 2 else -1)
        rows.append({"time": d + pd.Timedelta("14:30:00"), "currency": "USD", "event": "NFP",
                     "actual_value": 100 + big, "forecast_value": 100, "effect": 1})
        rows.append({"time": d + pd.Timedelta("10:00:00"), "currency": "EUR", "event": "Ifo",
                     "actual_value": 100 + big, "forecast_value": 100, "effect": 1})
    monkeypatch.setattr(economic_calendar, "load_calendar", lambda *a, **k: pd.DataFrame(rows))

    sig = sa.generate_signals(m1, sa.Params(z_threshold=2.0), "EURUSD")
    last_day = days[-1]
    usd = sig[sig["entry_time"] == last_day + pd.Timedelta("14:45:00")]
    eur = sig[sig["entry_time"] == last_day + pd.Timedelta("10:15:00")]
    assert usd["direction"].tolist() == [-1]   # bonne surprise pour le dollar : vente d'EUR/USD
    assert eur["direction"].tolist() == [1]    # bonne surprise pour l'euro : achat d'EUR/USD
    assert (sig["deadline"].dt.strftime("%H:%M") == "17:00").all()


def test_fixing_direction_is_reversed_when_usd_is_base(monkeypatch):
    from fxbt import data
    from fxbt.strategies import fixing_fin_de_mois as fx

    m1 = synthetic_m1(days=120, seed=4)
    dates = pd.bdate_range("2019-12-02", "2020-04-30")
    indices = {"^GSPC": pd.Series(np.linspace(100, 130, len(dates)), index=dates),
               "^SSMI": pd.Series(100.0, index=dates)}
    monkeypatch.setattr(data, "load_index", lambda s: indices[s])
    # S&P 500 devant : vente de dollar, donc vente d'USD/CHF.
    assert (fx.generate_signals(m1, fx.Params(), "USDCHF")["direction"] == -1).all()
    assert fx.generate_signals(m1, fx.Params(), "BTCUSD").empty


def test_smc_signals_follow_sweep_and_zone_rules():
    m1 = synthetic_m1(days=120, seed=3)
    for module in (smc, smc_ob):
        sig = module.generate_signals(m1, module.Params(), "EURUSD")
        assert len(sig) > 0
        assert (sig["entry_time"].dt.hour.between(8, 12)).all()
        assert not sig.duplicated(["day", "direction"]).any()  # un setup par côté et par jour
        for s in sig.itertuples():
            day = m1[m1.index.normalize() == s.day]
            asia = day[day.index.hour < 7]
            before = day[(day.index >= s.day + pd.Timedelta(hours=8)) & (day.index < s.entry_time)]
            if s.direction == 1:
                # Stop sous le bas asiatique : extrême du sweep (atteint avant l'entrée) moins 1 pip.
                assert s.stop_level < asia["low"].min()
                assert before["low"].min() - 0.0001 <= s.stop_level + 1e-9
            else:
                assert s.stop_level > asia["high"].max()
                assert before["high"].max() + 0.0001 >= s.stop_level - 1e-9
