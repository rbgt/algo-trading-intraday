import numpy as np
import pandas as pd
import pytest

from fxbt.simulation.engine import Account, Converter, run
from fxbt.strategies.base import BaseParams

TZ = "Europe/Zurich"
DAY = pd.Timestamp("2020-03-02", tz=TZ)  # un lundi


def make_m1(prices, start="08:00"):
    """prices : liste de (open, high, low, close), une par minute."""
    idx = pd.date_range(DAY + pd.Timedelta(start + ":00"), periods=len(prices), freq="1min")
    return pd.DataFrame(prices, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


def flat_until_17(prices, px):
    """Complète avec des minutes plates jusqu'à 17h05."""
    n = 9 * 60 + 5 - len(prices)
    return prices + [(px, px, px, px)] * n


def signal(direction=1, stop_dist=0.0010, rr=2.0, time="08:00", stop_level=np.nan):
    return pd.DataFrame([{
        "entry_time": DAY + pd.Timedelta(time + ":00"),
        "direction": direction,
        "stop_dist": stop_dist if np.isnan(stop_level) else np.nan,
        "stop_level": stop_level,
        "rr": rr,
        "deadline": DAY + pd.Timedelta(hours=17),
        "day": DAY,
    }])


def converter(m1):
    # EUR/USD fixé à 1.0 pour simplifier les montants.
    return Converter({"EURUSD": m1["close"] * 0 + 1.0})


def backtest(sig, m1, cost=0.0, params=BaseParams(max_trades_per_day=5), account=Account(max_leverage=1000)):
    return run(sig, m1, "EURUSD", params, account, cost, converter(m1))


def test_long_hits_target():
    m1 = make_m1(flat_until_17([(1.1000, 1.1005, 1.0995, 1.1000), (1.1000, 1.1021, 1.0999, 1.1020)], 1.1020))
    t = backtest(signal(), m1).iloc[0]
    assert t.reason == "target" and t.exit == pytest.approx(1.1020) and t.r == pytest.approx(2.0)


def test_stop_counted_first_when_both_hit_in_same_minute():
    m1 = make_m1(flat_until_17([(1.1000, 1.1030, 1.0980, 1.1000)], 1.1000))
    t = backtest(signal(), m1).iloc[0]
    assert t.reason == "stop" and t.r == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000), (1.0980, 1.0985, 1.0975, 1.0980)], 1.0980))
    t = backtest(signal(), m1).iloc[0]
    assert t.reason == "stop" and t.exit == pytest.approx(1.0980) and t.r == pytest.approx(-2.0)


def test_short_and_cost():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000), (1.1000, 1.1000, 1.0979, 1.0980)], 1.0980))
    t = backtest(signal(direction=-1), m1, cost=1.0).iloc[0]
    assert t.reason == "target" and t.r == pytest.approx(1.9)


def test_forced_exit_at_deadline():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000)], 1.1004))
    t = backtest(signal(), m1).iloc[0]
    assert t.reason == "time" and t.exit_time == DAY + pd.Timedelta(hours=17)
    assert t.r == pytest.approx(0.4)


def test_stop_level_on_wrong_side_is_skipped():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000)], 1.1000))
    assert backtest(signal(stop_level=1.1005), m1).empty


def test_sizing_risk_and_leverage_cap():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000)], 1.1000))
    # 1 € de risque / 0,0010 → 1 000 unités, sans plafond.
    assert backtest(signal(), m1).iloc[0].units == 1000
    # Levier 1:5 sur 100 € → 100 × 5 × 0,98 = 490 unités.
    assert backtest(signal(), m1, account=Account()).iloc[0].units == 490


def test_daily_limits_and_one_position_at_a_time():
    # Trois signaux perdants, puis un quatrième pendant que la position est ouverte.
    prices = []
    for _ in range(3):
        prices += [(1.1000, 1.1001, 1.0999, 1.1000)] * 4 + [(1.1000, 1.1000, 1.0985, 1.1000)]
    m1 = make_m1(flat_until_17(prices, 1.1000))
    sigs = pd.concat([signal(time=f"08:{m:02d}") for m in (0, 2, 5, 10)], ignore_index=True)
    t = backtest(sigs, m1, params=BaseParams(max_trades_per_day=3, max_consec_losses=2))
    # 08:00 → stop à 08:04 ; 08:02 ignoré (position ouverte) ; 08:05 → stop à 08:09 ; 08:10 bloqué (2 pertes).
    assert list(t.entry_time.dt.strftime("%H:%M")) == ["08:00", "08:05"]


def test_min_stop_guard():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000)], 1.1000))
    params = BaseParams(max_trades_per_day=5, min_stop_pips=20)
    assert backtest(signal(stop_dist=0.0019), m1, params=params).empty
    assert len(backtest(signal(stop_dist=0.0020), m1, params=params)) == 1


def test_target_level_and_min_target_r():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000), (1.1000, 1.1031, 1.0999, 1.1030)], 1.1030))
    params = BaseParams(max_trades_per_day=5, min_target_r=1.0)
    sig = signal(stop_dist=0.0010).assign(target_level=1.1030)
    t = backtest(sig, m1, params=params).iloc[0]
    assert t.reason == "target" and t.r == pytest.approx(3.0)
    # Objectif à 0,5 R : ignoré.
    assert backtest(signal(stop_dist=0.0010).assign(target_level=1.1005), m1, params=params).empty


def test_montecarlo_sampling_respects_space():
    from fxbt.simulation.montecarlo import sample_params

    space = {"a": ("int", 2, 5), "b": ("float", 0.1, 0.4), "c": ("choice", [True, False])}
    samples = sample_params(space, 200, seed=1)
    assert all(2 <= s["a"] <= 5 and 0.1 <= s["b"] <= 0.4 and s["c"] in (True, False) for s in samples)
    assert {s["a"] for s in samples} == {2, 3, 4, 5}
    assert sample_params(space, 5, seed=1) == samples[:5]  # reproductible


def test_news_filter_blocks_entries_near_announcements():
    m1 = make_m1(flat_until_17([(1.1000, 1.1001, 1.0999, 1.1000)], 1.1000))
    news = np.array([(DAY + pd.Timedelta("08:20:00")).as_unit("ns").value])
    sig = pd.concat([signal(time="08:00"), signal(time="09:00")], ignore_index=True)
    sig["deadline"] = [DAY + pd.Timedelta("08:30:00"), DAY + pd.Timedelta(hours=17)]
    t = run(sig, m1, "EURUSD", BaseParams(max_trades_per_day=5), Account(max_leverage=1000), 0.0, converter(m1), news, 30)
    # 8h00 est à 20 min de l'annonce de 8h20 : bloqué. 9h00 est à 40 min : autorisé.
    assert list(t.entry_time.dt.strftime("%H:%M")) == ["09:00"]


def test_converter_goes_through_usd_for_any_currency():
    idx = pd.date_range("2020-01-01", periods=2, freq="1min", tz=TZ)
    conv = Converter({"EURUSD": pd.Series(1.25, index=idx), "USDCHF": pd.Series(0.8, index=idx),
                      "BTCUSD": pd.Series(10_000.0, index=idx)})
    t = idx[-1].as_unit("ns").value
    assert conv.to_eur("USD", t) == pytest.approx(0.8)          # 1 / 1,25
    assert conv.to_eur("CHF", t) == pytest.approx(1.0)          # (1 / 0,8) / 1,25
    assert conv.to_eur("BTC", t) == pytest.approx(8_000.0)      # 10 000 / 1,25


def test_btc_cost_in_percent_and_fractional_size():
    from fxbt.data import cost_in_price
    from fxbt.simulation.engine import account_for

    assert cost_in_price("BTCUSD", 0.2, 30_000) == pytest.approx(60.0)
    assert cost_in_price("EURUSD", 1.1, 1.1) == pytest.approx(0.00011)
    acc = account_for("BTCUSD")
    assert acc.max_leverage == 2.0 and acc.lot_step == 0.0001
    idx = pd.date_range(DAY + pd.Timedelta("08:00:00"), periods=9 * 60 + 5, freq="1min")
    m1 = pd.DataFrame({"open": 10_000.0, "high": 10_001.0, "low": 9_999.0, "close": 10_000.0, "volume": 1.0}, index=idx)
    conv = Converter({"EURUSD": m1["close"] * 0 + 1.0, "BTCUSD": m1["close"]})
    t = run(signal(stop_dist=100.0), m1, "BTCUSD", BaseParams(), acc, 0.2, conv).iloc[0]
    # 1 € de risque / 100 $ de stop = 0,01 BTC ; plafond de levier 100 × 2 × 0,98 / 10 000 = 0,0196 BTC.
    assert t.units == pytest.approx(0.01)
    assert t.r == pytest.approx(-20.0 / 100.0)  # sortie à plat à 17h, coût de 0,2 % de 10 000 $ = 20 $


def test_rollovers_and_financing():
    from fxbt.data import financing_in_price, rollovers

    ny = "America/New_York"
    mon = pd.Timestamp("2020-03-09 10:00", tz=ny)
    # Intraday (avant 17h à New York) : pas de swap.
    assert rollovers("EURUSD", mon, mon + pd.Timedelta(hours=5)) == 0
    # Du lundi au lundi suivant : lun, mar, mer (×3), jeu, ven = 7 swaps pour le forex ; 7 nuits pour le BTC.
    assert rollovers("EURUSD", mon, mon + pd.Timedelta(days=7)) == 7
    assert rollovers("BTCUSD", mon, mon + pd.Timedelta(days=7)) == 7
    # Du vendredi au lundi : 1 swap forex (vendredi), 3 nuits BTC.
    fri = pd.Timestamp("2020-03-13 10:00", tz=ny)
    assert rollovers("EURUSD", fri, fri + pd.Timedelta(days=3)) == 1
    assert rollovers("BTCUSD", fri, fri + pd.Timedelta(days=3)) == 3
    # 3 %/an sur 365 swaps = 3 % du prix.
    assert financing_in_price("EURUSD", mon, mon + pd.Timedelta(days=7), 1.0) == pytest.approx(0.03 * 7 / 365)
