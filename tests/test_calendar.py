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
