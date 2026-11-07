import zipfile

import pandas as pd

from fxbt import data


def test_import_histdata_converts_new_york_time_to_zurich(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data, "HIST_DIR", tmp_path / "histdata")
    (tmp_path / "histdata").mkdir()
    csv = "20200102 170000;1.121270;1.121290;1.121260;1.121280;0\n20200702 030000;1.12;1.13;1.11;1.125;0\n"
    with zipfile.ZipFile(tmp_path / "histdata" / "HISTDATA_COM_ASCII_EURUSD_M1_2020.zip", "w") as z:
        z.writestr("DAT_ASCII_EURUSD_M1_2020.csv", csv)

    paths = data.import_histdata("EURUSD")
    assert [p.name for p in paths] == ["EURUSD_HIST_M1_2020-01.parquet", "EURUSD_HIST_M1_2020-07.parquet"]

    m1 = data.load_m1("EURUSD", source="histdata")
    # Heure de New York : 17h00 EST → 22h00 UTC → 23h00 à Zurich ; 03h00 EDT → 07h00 UTC → 09h00 à Zurich.
    assert list(m1.index) == [
        pd.Timestamp("2020-01-02 23:00", tz=data.TZ),
        pd.Timestamp("2020-07-02 09:00", tz=data.TZ),
    ]
    assert m1.iloc[0]["close"] == 1.12128


def test_histdata_timezone_rule_changes_in_2019():
    local = pd.DatetimeIndex(["2018-03-13 03:00", "2020-03-10 03:00", "2020-07-02 03:00", "2020-11-03 03:00"])
    utc = data._histdata_to_utc(local)
    assert list(utc.strftime("%H:%M")) == [
        "07:00",  # 2018 : heure de New York (EDT, UTC−4) pendant l'écart États-Unis / Europe
        "08:00",  # 2020 : UTC−5, l'Europe n'est pas encore à l'heure d'été
        "07:00",  # 2020 : heure d'été européenne
        "08:00",  # 2020 : de nouveau UTC−5 après fin octobre
    ]
