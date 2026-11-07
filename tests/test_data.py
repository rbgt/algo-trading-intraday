import zipfile

import pandas as pd

from fxbt import data


def test_import_histdata_converts_fixed_est_to_zurich(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data, "HIST_DIR", tmp_path / "histdata")
    (tmp_path / "histdata").mkdir()
    csv = "20200102 170000;1.121270;1.121290;1.121260;1.121280;0\n20200702 030000;1.12;1.13;1.11;1.125;0\n"
    with zipfile.ZipFile(tmp_path / "histdata" / "HISTDATA_COM_ASCII_EURUSD_M1_2020.zip", "w") as z:
        z.writestr("DAT_ASCII_EURUSD_M1_2020.csv", csv)

    paths = data.import_histdata("EURUSD")
    assert [p.name for p in paths] == ["EURUSD_HIST_M1_2020-01.parquet", "EURUSD_HIST_M1_2020-07.parquet"]

    m1 = data.load_m1("EURUSD", source="histdata")
    # UTC−5 fixe : 17h00 → 22h00 UTC → 23h00 en hiver à Zurich ; 03h00 → 08h00 UTC → 10h00 en été.
    assert list(m1.index) == [
        pd.Timestamp("2020-01-02 23:00", tz=data.TZ),
        pd.Timestamp("2020-07-02 10:00", tz=data.TZ),
    ]
    assert m1.iloc[0]["close"] == 1.12128
