"""Téléchargement et chargement des bougies M1 Dukascopy.

Les fichiers Dukascopy sont journaliers (UTC), compressés en LZMA. Chaque
enregistrement fait 24 octets, en big-endian :
secondes depuis minuit, ouverture, clôture, plus bas, plus haut (entiers en
points) et volume (float).
"""

from __future__ import annotations

import lzma
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "Europe/Zurich"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
URL = "https://datafeed.dukascopy.com/datafeed/{pair}/{y}/{m:02d}/{d:02d}/{side}_candles_min_1.bi5"
OHLCV = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

_DTYPE = np.dtype([
    ("t", ">u4"), ("open", ">u4"), ("close", ">u4"),
    ("low", ">u4"), ("high", ">u4"), ("volume", ">f4"),
])


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def _point(pair: str) -> float:
    return 1e3 if pair.endswith("JPY") else 1e5


def _fetch_day(pair: str, day: date, side: str) -> pd.DataFrame | None:
    # Les mois commencent à 0 dans les URL Dukascopy.
    url = URL.format(pair=pair, y=day.year, m=day.month - 1, d=day.day, side=side)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    err: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = e
        time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"Échec du téléchargement de {url} : {err}")
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


def year_path(pair: str, year: int, side: str = "BID") -> Path:
    return DATA_DIR / "raw" / f"{pair}_{side}_M1_{year}.parquet"


def download_year(pair: str, year: int, side: str = "BID", workers: int = 8) -> Path | None:
    """Télécharge une année de M1 en parquet (UTC). L'année en cours est toujours rafraîchie."""
    path = year_path(pair, year, side)
    today = datetime.now(timezone.utc).date()
    if year > today.year or (path.exists() and year < today.year):
        return path if path.exists() else None

    last = min(date(year, 12, 31), today - timedelta(days=1))
    days = [d.date() for d in pd.date_range(f"{year}-01-01", last.isoformat())]
    with ThreadPoolExecutor(workers) as ex:
        frames = [f for f in ex.map(lambda d: _fetch_day(pair, d, side), days) if f is not None and len(f)]
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


def load_m1(pair: str, start: str | None = None, end: str | None = None, side: str = "BID") -> pd.DataFrame:
    """Bougies M1 en heure de Zurich, sur [start, end)."""
    files = sorted((DATA_DIR / "raw").glob(f"{pair}_{side}_M1_*.parquet"))
    if not files:
        raise FileNotFoundError(f"Aucune donnée pour {pair}. Lancer d'abord : python -m fxbt download")
    df = pd.concat(pd.read_parquet(f) for f in files).sort_index()
    df.index = df.index.tz_convert(TZ)
    if start:
        df = df[df.index >= pd.Timestamp(start, tz=TZ)]
    if end:
        df = df[df.index < pd.Timestamp(end, tz=TZ)]
    return df


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


def check(m1: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Contrôle qualité par année : bougies, trous en semaine, nombre de décimales."""
    idx = m1.index
    gaps = pd.Series(idx[1:] - idx[:-1], index=idx[1:])
    # On ignore la fermeture du week-end : vendredi soir → dimanche soir.
    weekday_gaps = gaps[(gaps > pd.Timedelta(minutes=30)) & (gaps < pd.Timedelta(hours=40))]
    decimals = int(round(-np.log10(pip_size(pair)))) + 1
    out = pd.DataFrame({
        "bougies": m1.groupby(idx.year).size(),
        "trous_>30min": weekday_gaps.groupby(weekday_gaps.index.year).size(),
        "plus_long_trou": weekday_gaps.groupby(weekday_gaps.index.year).max(),
        "premier": pd.Series(idx, index=idx).groupby(idx.year).min(),
        "dernier": pd.Series(idx, index=idx).groupby(idx.year).max(),
    }).fillna({"trous_>30min": 0})
    out.index.name = "année"
    out.attrs["decimales_attendues"] = decimals
    return out
