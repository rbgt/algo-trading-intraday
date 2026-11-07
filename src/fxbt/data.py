"""Téléchargement, import et chargement des bougies M1.

Deux sources, stockées en parquet mensuel (UTC) dans data/raw/ :

- Dukascopy (téléchargée par `download`) : fichiers journaliers (UTC), compressés en
  LZMA. Chaque enregistrement fait 24 octets, en big-endian : secondes depuis minuit,
  ouverture, clôture, plus bas, plus haut (entiers en points) et volume (float).
- HistData.com (téléchargée à la main, importée par `import-histdata`) : CSV « Generic
  ASCII » `AAAAMMJJ HHMMSS;open;high;low;close;volume`, en heure de New York (avec heure
  d'été, contrairement à ce qu'annonce le site).
"""

from __future__ import annotations

import http.client
import lzma
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "Europe/Zurich"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HIST_DIR = DATA_DIR / "histdata"
INDEX_DIR = DATA_DIR / "indices"
INDICES = {"^GSPC": "S&P 500", "^GDAXI": "DAX", "^FTSE": "FTSE 100"}
SOURCES = {"dukascopy": "BID", "histdata": "HIST"}  # source → étiquette des fichiers
HOST = "datafeed.dukascopy.com"
PATH = "/datafeed/{pair}/{y}/{m:02d}/{d:02d}/{side}_candles_min_1.bi5"
OHLCV = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

_DTYPE = np.dtype([
    ("t", ">u4"), ("open", ">u4"), ("close", ">u4"),
    ("low", ">u4"), ("high", ">u4"), ("volume", ">f4"),
])


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def _point(pair: str) -> float:
    return 1e3 if pair.endswith("JPY") else 1e5


class _Client:
    """Connexion HTTPS persistante, une requête à la fois.

    Dukascopy répond 503 dès qu'on va trop vite, puis 429 (bannissement temporaire)
    si on insiste : on attend de plus en plus longtemps, et 15 minutes sur un 429.
    """

    def __init__(self, pause: float = 0.5):
        self.pause = pause
        self.conn: http.client.HTTPSConnection | None = None

    def get(self, path: str) -> bytes | None:
        for attempt in range(12):
            wait = min(300, 10 * 2 ** attempt)
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(HOST, timeout=30)
                self.conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0"})
                resp = self.conn.getresponse()
                body = resp.read()
                if resp.status == 200:
                    time.sleep(self.pause)
                    return body
                if resp.status == 404:
                    return None
                if resp.status == 429:
                    wait = 900
                err = f"HTTP {resp.status}"
            except (OSError, http.client.HTTPException) as e:
                err = repr(e)
                self.conn = None
            print(f"  {path} : {err}, nouvelle tentative dans {wait} s", flush=True)
            time.sleep(wait)
        raise RuntimeError(f"Échec du téléchargement de {path}")


def _fetch_day(client: _Client, pair: str, day: date, side: str) -> pd.DataFrame | None:
    # Les mois commencent à 0 dans les URL Dukascopy.
    raw = client.get(PATH.format(pair=pair, y=day.year, m=day.month - 1, d=day.day, side=side))
    if not raw:
        return None
    rec = np.frombuffer(lzma.decompress(raw), dtype=_DTYPE)
    p = _point(pair)
    index = pd.Timestamp(day.isoformat(), tz="UTC") + pd.to_timedelta(rec["t"].astype("int64"), unit="s")
    return pd.DataFrame(
        {
            "open": rec["open"] / p,
            "high": rec["high"] / p,
            "low": rec["low"] / p,
            "close": rec["close"] / p,
            "volume": rec["volume"].astype("float64"),
        },
        index=index,
    )


def month_path(pair: str, year: int, month: int, side: str = "BID") -> Path:
    return DATA_DIR / "raw" / f"{pair}_{side}_M1_{year}-{month:02d}.parquet"


def download_month(client: _Client, pair: str, year: int, month: int, side: str = "BID") -> Path | None:
    """Télécharge un mois de M1 en parquet (UTC). Un mois terminé n'est jamais retéléchargé."""
    path = month_path(pair, year, month, side)
    today = datetime.now(timezone.utc).date()
    first = date(year, month, 1)
    last = (pd.Timestamp(first) + pd.offsets.MonthEnd(0)).date()
    if first >= today or (path.exists() and last < today):
        return path if path.exists() else None

    frames = []
    for d in pd.date_range(first.isoformat(), min(last, today - timedelta(days=1)).isoformat()):
        if d.day_of_week == 5:  # samedi : marché fermé
            continue
        f = _fetch_day(client, pair, d.date(), side)
        if f is not None and len(f):
            frames.append(f)
    if not frames:
        return None

    df = pd.concat(frames).sort_index()
    # Dukascopy remplit les heures de marché fermé avec des bougies plates de volume nul.
    df = df[df["volume"] > 0]
    df = df[~df.index.duplicated()]
    df.index.name = "time"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return path


def download(pair: str, start_year: int, end_year: int, side: str = "BID"):
    client = _Client()
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            path = download_month(client, pair, year, month, side)
            if path:
                print(f"{pair} {year}-{month:02d} : ok", flush=True)


def _save_monthly(df: pd.DataFrame, pair: str, tag: str) -> list[Path]:
    paths = []
    for (y, m), part in df.groupby([df.index.year, df.index.month]):
        path = DATA_DIR / "raw" / f"{pair}_{tag}_M1_{y}-{m:02d}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        part.to_parquet(path)
        paths.append(path)
    return paths


# Jusqu'en 2018, HistData est en heure de New York. Ensuite, c'est UTC−5 avec l'heure d'été
# européenne : pendant les semaines où les États-Unis et l'Europe ne sont pas à la même heure,
# le marché « rouvre » à 16h au lieu de 17h. Vérifié contre Dukascopy (`compare`) et sur
# l'heure de réouverture du dimanche.
_HIST_EU_DST_FROM = pd.Timestamp("2019-01-01")


def _histdata_to_utc(local: pd.DatetimeIndex) -> pd.DatetimeIndex:
    ny = local.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
    fixed = local.tz_localize("Etc/GMT+5").tz_convert("UTC")  # UTC−5 (« Etc/GMT+5 » a le signe inversé)
    # Heure d'été européenne : Londres est alors à UTC+1.
    eu_dst = fixed.tz_convert("Europe/London").tz_localize(None) - fixed.tz_localize(None)
    eu = fixed - eu_dst
    return ny.where(local < _HIST_EU_DST_FROM, eu)


def _read_histdata_csv(fh) -> pd.DataFrame:
    df = pd.read_csv(fh, sep=";", header=None, names=["time", "open", "high", "low", "close", "volume"])
    local = pd.DatetimeIndex(pd.to_datetime(df.pop("time"), format="%Y%m%d %H%M%S"))
    df.index = _histdata_to_utc(local)
    # Les heures ambiguës ou inexistantes tombent le dimanche vers 2h du matin, marché fermé.
    df = df[df.index.notna()]
    df.index.name = "time"
    return df.astype("float64")


_HIST_PAGE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair}/{period}"


def _histdata_zip(pair: str, year: int, month: int | None) -> bytes | None:
    """Récupère un zip HistData : la page contient un jeton à renvoyer au formulaire de téléchargement."""
    period = f"{year}/{month}" if month else f"{year}"
    page_url = _HIST_PAGE.format(pair=pair.lower(), period=period)
    headers = {"User-Agent": "Mozilla/5.0"}
    with urllib.request.urlopen(urllib.request.Request(page_url, headers=headers), timeout=60) as resp:
        html = resp.read().decode("utf-8", "replace")
    tk = re.search(r'id="tk" value="([0-9a-f]+)"', html)
    if not tk:
        return None
    form = urllib.parse.urlencode({
        "tk": tk.group(1),
        "date": str(year),
        "datemonth": f"{year}{month:02d}" if month else str(year),
        "platform": "ASCII",
        "timeframe": "M1",
        "fxpair": pair.upper(),
    }).encode()
    req = urllib.request.Request("https://www.histdata.com/get.php", data=form, headers={**headers, "Referer": page_url})
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read()
    return body if body[:2] == b"PK" else None


def download_histdata(pair: str, start_year: int, pause: float = 3.0) -> list[Path]:
    """Télécharge les années complètes, puis les mois terminés de l'année en cours."""
    today = datetime.now(timezone.utc).date()
    periods = [(y, None) for y in range(start_year, today.year)] + [(today.year, m) for m in range(1, today.month)]
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for year, month in periods:
        name = f"HISTDATA_COM_ASCII_{pair}_M1{year}{month:02d}.zip" if month else f"HISTDATA_COM_ASCII_{pair}_M1{year}.zip"
        path = HIST_DIR / name
        if not path.exists():
            body = _histdata_zip(pair, year, month)
            if body is None:
                print(f"  {pair} {year}{'-%02d' % month if month else ''} : pas de fichier", flush=True)
                continue
            path.write_bytes(body)
            time.sleep(pause)
        print(f"{pair} {year}{'-%02d' % month if month else ''} : ok", flush=True)
        saved.append(path)
    return saved


def import_histdata(pair: str) -> list[Path]:
    """Convertit les zip/CSV HistData de data/histdata/ en parquet mensuels."""
    frames = []
    for f in sorted(HIST_DIR.glob(f"*{pair}*")):
        if f.suffix.lower() == ".zip":
            with zipfile.ZipFile(f) as z:
                for name in z.namelist():
                    if name.lower().endswith(".csv"):
                        with z.open(name) as fh:
                            frames.append(_read_histdata_csv(fh))
        elif f.suffix.lower() == ".csv":
            frames.append(_read_histdata_csv(f))
    if not frames:
        raise FileNotFoundError(f"Aucun fichier HistData pour {pair} dans {HIST_DIR}")
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated()]
    return _save_monthly(df, pair, SOURCES["histdata"])


def download_indices(symbols=tuple(INDICES), start: str = "2014-01-01") -> list[Path]:
    """Clôtures journalières des indices actions (Yahoo Finance), datées dans le fuseau de leur bourse."""
    import json

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    period2 = int(pd.Timestamp.now(tz="UTC").timestamp())
    paths = []
    for symbol in symbols:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
               f"?period1={period1}&period2={period2}&interval=1d")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as resp:
            result = json.load(resp)["chart"]["result"][0]
        tz = result["meta"]["exchangeTimezoneName"]
        dates = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(tz).tz_localize(None).normalize()
        closes = pd.Series(result["indicators"]["quote"][0]["close"], index=dates, name="close").dropna()
        path = INDEX_DIR / f"{symbol.lstrip('^')}.csv"
        closes[~closes.index.duplicated(keep="last")].to_csv(path, index_label="date")
        paths.append(path)
    return paths


def load_index(symbol: str) -> pd.Series:
    """Clôtures journalières d'un indice, indexées par date de bourse (sans fuseau horaire)."""
    path = INDEX_DIR / f"{symbol.lstrip('^')}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Indice {symbol} absent. Lancer d'abord : python -m fxbt download-indices")
    return pd.read_csv(path, index_col="date", parse_dates=["date"])["close"]


def load_m1(pair: str, start: str | None = None, end: str | None = None, source: str = "histdata") -> pd.DataFrame:
    """Bougies M1 en heure de Zurich, sur [start, end)."""
    files = sorted((DATA_DIR / "raw").glob(f"{pair}_{SOURCES[source]}_M1_*.parquet"))
    if not files:
        raise FileNotFoundError(f"Aucune donnée {source} pour {pair} (voir le README, section Données)")
    df = pd.concat(pd.read_parquet(f) for f in files).sort_index()
    df.index = df.index.tz_convert(TZ)
    if start:
        df = df[df.index >= pd.Timestamp(start, tz=TZ)]
    if end:
        df = df[df.index < pd.Timestamp(end, tz=TZ)]
    return df


def compare_sources(a: pd.DataFrame, b: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Compare deux sources minute par minute sur leur période commune.

    Un décalage horaire mal géré se voit tout de suite : l'écart est minimal
    pour un décalage de 0 minute et grandit pour ±60 minutes.
    """
    lo, hi = max(a.index[0], b.index[0]), min(a.index[-1], b.index[-1])
    a, b = a.loc[lo:hi, "close"], b.loc[lo:hi, "close"]
    rows = []
    for shift in (-60, 0, 60):
        joined = pd.concat([a, b.shift(freq=pd.Timedelta(minutes=shift))], axis=1, keys=["a", "b"], join="inner")
        diff = (joined["a"] - joined["b"]).abs() / pip_size(pair)
        rows.append({
            "décalage_min": shift,
            "minutes_communes": len(joined),
            "écart_médian_pips": round(float(diff.median()), 2),
            "écart_p99_pips": round(float(diff.quantile(0.99)), 2),
        })
    return pd.DataFrame(rows)


def resample(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Agrège les M1. Chaque bougie est étiquetée par son heure d'ouverture."""
    return m1.resample(rule, label="left", closed="left").agg(OHLCV).dropna(subset=["open"])


def daily_bars(m1: pd.DataFrame) -> pd.DataFrame:
    """Bougies journalières forex : la journée se termine à 17h, heure de New York.

    L'index est la date de trading (sans fuseau horaire). La séance du dimanche
    soir est rattachée au lundi.
    """
    ny = m1.index.tz_convert("America/New_York")
    key = (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize()
    return m1.groupby(key).agg(OHLCV)


def check(m1: pd.DataFrame) -> pd.DataFrame:
    """Contrôle qualité par année : nombre de bougies et trous en semaine."""
    idx = m1.index
    gaps = pd.Series(idx[1:] - idx[:-1], index=idx[1:])
    # On ignore la fermeture du week-end : vendredi soir → dimanche soir.
    weekday_gaps = gaps[(gaps > pd.Timedelta(minutes=30)) & (gaps < pd.Timedelta(hours=40))]
    out = pd.DataFrame({
        "bougies": m1.groupby(idx.year).size(),
        "trous_>30min": weekday_gaps.groupby(weekday_gaps.index.year).size(),
        "plus_long_trou": weekday_gaps.groupby(weekday_gaps.index.year).max(),
        "premier": pd.Series(idx, index=idx).groupby(idx.year).min(),
        "dernier": pd.Series(idx, index=idx).groupby(idx.year).max(),
    }).fillna({"trous_>30min": 0})
    out.index.name = "année"
    return out
