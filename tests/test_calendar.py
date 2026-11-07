import pandas as pd

from fxbt import economic_calendar as ec


def test_missing_times_are_inferred_in_home_timezone(tmp_path, monkeypatch):
    # Heure de Téhéran : 17h00 (+03:30) = 13h30 UTC = 8h30 à New York en été (EDT).
    csv = """DateTime,Currency,Impact,Event,Actual,Forecast,Previous,Detail
2020-06-05T17:00:00+04:30,USD,High Impact Expected,Non-Farm Employment Change,2.5M,-8.0M,-20.6M,x
2020-07-02T00:00:00+04:30,USD,High Impact Expected,Non-Farm Employment Change,4.8M,3.0M,2.7M,x
2020-12-04T00:00:00+03:30,USD,High Impact Expected,Non-Farm Employment Change,245K,469K,610K,x
2020-07-02T00:00:00+04:30,USD,High Impact Expected,Fed Chair Powell Speaks,,,,x
2020-07-03T00:00:00+04:30,USD,Low Impact Expected,Some Minor Data,1,1,1,x
"""
    path = tmp_path / "cal.csv"
    path.write_text(csv)
    monkeypatch.setattr(ec, "CALENDAR_PATH", path)

    cal = ec.load_calendar()
    # Le discours (non programmé) et l'annonce à faible impact sont exclus.
    assert list(cal["event"].unique()) == ["Non-Farm Employment Change"]
    # 8h30 à New York : 14h30 à Zurich en été et en hiver (sauf les semaines de décalage des changements d'heure).
    assert list(cal["time"].dt.strftime("%Y-%m-%d %H:%M")) == ["2020-06-05 14:30", "2020-07-02 14:30", "2020-12-04 14:30"]
    assert list(cal["time_source"]) == ["fichier", "déduite", "déduite"]


def test_parse_value_and_usual_effect():
    import numpy as np

    assert ec.parse_value("245K") == 245_000 and ec.parse_value("-0.3%") == -0.3
    assert ec.parse_value("<0.10%") == 0.10 and ec.parse_value("2.5M") == 2_500_000
    assert np.isnan(ec.parse_value(None)) and np.isnan(ec.parse_value("n/a"))
    assert ec.usual_effect("x | Usual Effect: 'Actual' greater than 'Forecast' is good for currency; | y") == 1
    assert ec.usual_effect("Usual Effect: 'Actual' less than 'Forecast' is good for currency;") == -1
    assert ec.usual_effect("Usual Effect: More hawkish than expected is good for currency;") == 1
    assert ec.usual_effect("Usual Effect: No consistent effect") == 0


def test_surprise_scores_are_normalized_oriented_and_summed():
    import numpy as np

    from fxbt.strategies.surprise_annonces import surprise_scores

    times = pd.date_range("2020-01-03 14:30", periods=11, freq="7D", tz="Europe/Zurich")
    surprises = [1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 3]  # écart-type passé ≈ 1, puis une grosse surprise
    rows = [{"time": t, "currency": "USD", "event": "NFP", "actual_value": 100 + s, "forecast_value": 100, "effect": 1}
            for t, s in zip(times, surprises)]
    # Chômage à la même minute : plus haut que prévu, mauvais pour la devise (effect −1).
    rows += [{"time": t, "currency": "USD", "event": "Unemployment", "actual_value": 5 + s / 10, "forecast_value": 5, "effect": -1}
             for t, s in zip(times, surprises)]
    z = surprise_scores(pd.DataFrame(rows), lookback=20, min_history=8)
    last = z[z["time"] == times[-1]]
    # NFP +3 écarts-types (bon) et chômage +3 écarts-types (mauvais) s'annulent.
    assert len(last) == 1 and np.isclose(last["z"].iloc[0], 0, atol=1e-9)
    nfp_only = surprise_scores(pd.DataFrame(rows[:11]), lookback=20, min_history=8)
    assert nfp_only["z"].iloc[-1] > 2.5 and len(nfp_only) == 3  # 8 surprises d'historique minimum
