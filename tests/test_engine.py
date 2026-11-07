import numpy as np
import pandas as pd
import pytest

from fxbt.engine import Account, BaseParams, Converter, run

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
    from fxbt.montecarlo import sample_params

    space = {"a": ("int", 2, 5), "b": ("float", 0.1, 0.4), "c": ("choice", [True, False])}
    samples = sample_params(space, 200, seed=1)
    assert all(2 <= s["a"] <= 5 and 0.1 <= s["b"] <= 0.4 and s["c"] in (True, False) for s in samples)
    assert {s["a"] for s in samples} == {2, 3, 4, 5}
    assert sample_params(space, 5, seed=1) == samples[:5]  # reproductible
