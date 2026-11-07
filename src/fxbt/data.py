"""Téléchargement et chargement des bougies M1 Dukascopy.

Les fichiers Dukascopy sont journaliers (UTC), compressés en LZMA. Chaque
enregistrement fait 24 octets, en big-endian :
secondes depuis minuit, ouverture, clôture, plus bas, plus haut (entiers en
points) et volume (float).
"""

from __future__ import annotations

import http.client
import lzma
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "Europe/Zurich"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
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
