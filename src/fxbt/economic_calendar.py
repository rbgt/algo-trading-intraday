"""Calendrier économique (Forex Factory, 2007 → avril 2025, jeu de données public sous licence MIT).

Source : https://huggingface.co/datasets/Tropstan/Forex_Factory_Calendar, à déposer dans
data/calendar/forex_factory_2007_2025.csv (commande `download-calendar`).

Le fichier est en heure de Téhéran. Environ 35 à 50 % des annonces n'y ont pas d'heure : elles sont
placées à minuit. La date reste juste. Pour ces annonces, l'heure est déduite des autres publications
du même événement, dans l'heure locale de son pays (le NFP sort toujours à 8h30 à New York), en
prenant les 5 publications connues les plus proches dans le temps. Le contrôle `event_spike` vérifie
ensuite, avec les prix, qu'il y a bien un pic de volatilité à l'heure retenue.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from .data import DATA_DIR, TZ

CALENDAR_PATH = DATA_DIR / "calendar" / "forex_factory_2007_2025.csv"
CALENDAR_URL = "https://huggingface.co/datasets/Tropstan/Forex_Factory_Calendar/resolve/main/forex_factory_cache.csv"
HOME_TZ = {"USD": "America/New_York", "EUR": "Europe/Berlin", "GBP": "Europe/London"}
REFERENCE_COUNT = 5  # publications connues les plus proches dans le temps
# Discours, auditions et réunions : pas d'heure de réaction précise, et des heures souvent fausses
# dans le fichier (pic de volatilité absent, voir `check-calendar`). Exclus par défaut.
UNSCHEDULED = ("Speaks", "Testifies", "Hearings", "Summit", "Meetings", "Conference Call")


def download_calendar() -> Path:
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        CALENDAR_PATH.write_bytes(resp.read())
    return CALENDAR_PATH


def _infer_times(group: pd.DataFrame, tz: str) -> pd.Series:
    """Heure locale (minutes depuis minuit) de chaque annonce d'un même événement.

    Annonce sans heure : heure la plus fréquente parmi les REFERENCE_COUNT publications connues du même
    événement les plus proches dans le temps (suit les changements d'horaire officiels). NaN si aucune référence.
    """
    known = group[~group["missing"]]
    out = pd.Series(np.nan, index=group.index)
    out[known.index] = known["local_minutes"]
    if known.empty:
        return out
    k_days = known["date"].to_numpy("datetime64[D]").astype("int64")
    k_minutes = known["local_minutes"].to_numpy()
    for idx, day in group.loc[group["missing"], "date"].items():
        nearest = np.argsort(np.abs(k_days - np.datetime64(day, "D").astype("int64")), kind="stable")[:REFERENCE_COUNT]
        out[idx] = pd.Series(k_minutes[nearest]).mode().iloc[0]
    return out


def load_calendar(currencies=("USD", "EUR", "GBP"), impacts=("High",), scheduled_only: bool = True) -> pd.DataFrame:
    """Annonces avec heure de Zurich : colonnes time, currency, impact, event, actual, forecast, previous, time_source."""
    if not CALENDAR_PATH.exists():
        raise FileNotFoundError("Calendrier absent. Lancer d'abord : python -m fxbt download-calendar")
    raw = pd.read_csv(CALENDAR_PATH, usecols=["DateTime", "Currency", "Impact", "Event", "Actual", "Forecast", "Previous"])
    raw = raw[raw["Currency"].isin(currencies) & raw["Impact"].str.split().str[0].isin(impacts)].copy()
    if scheduled_only:
        raw = raw[~raw["Event"].str.contains("|".join(UNSCHEDULED))]

    raw["missing"] = raw["DateTime"].str.slice(11, 16) == "00:00"
    raw["date"] = pd.to_datetime(raw["DateTime"].str.slice(0, 10))  # date telle qu'écrite : juste même sans heure
    utc = pd.to_datetime(raw["DateTime"], utc=True, format="ISO8601")

    frames = []
    for cur, tz in HOME_TZ.items():
        part = raw[raw["Currency"] == cur].copy()
        if part.empty:
            continue
        local = utc[part.index].dt.tz_convert(tz)
        part["local_minutes"] = (local.dt.hour * 60 + local.dt.minute).astype(float)
        part["minutes"] = np.nan
        for _, group in part.groupby("Event"):
            part.loc[group.index, "minutes"] = _infer_times(group, tz)
        part = part.dropna(subset=["minutes"])
        local_time = part["date"] + pd.to_timedelta(part["minutes"], unit="min")
        part["time"] = local_time.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert(TZ)
        frames.append(part.dropna(subset=["time"]))

    cal = pd.concat(frames)
    cal["time_source"] = np.where(cal["missing"], "déduite", "fichier")
    cal = cal.rename(columns={"Currency": "currency", "Impact": "impact", "Event": "event",
                              "Actual": "actual", "Forecast": "forecast", "Previous": "previous"})
    cols = ["time", "currency", "impact", "event", "actual", "forecast", "previous", "time_source"]
    return cal[cols].sort_values("time").drop_duplicates(["time", "currency", "event"]).reset_index(drop=True)


def spike_report(cal: pd.DataFrame, m1s: dict[str, pd.DataFrame], min_count: int = 12) -> pd.DataFrame:
    """Pic de volatilité par événement et par source d'heure, sur la paire concernée."""
    pair_for = {"USD": "EURUSD", "EUR": "EURUSD", "GBP": "GBPUSD"}
    rows = []
    for (cur, ev), g in cal.groupby(["currency", "event"]):
        if len(g) < min_count or pair_for.get(cur) not in m1s:
            continue
        for src, gs in g.groupby("time_source"):
            rows.append({"devise": cur, "événement": ev, "source_heure": src, "annonces": len(gs),
                         "pic": round(event_spike(m1s[pair_for[cur]], gs["time"]), 1),
                         "heure_zurich": gs["time"].dt.strftime("%H:%M").mode().iloc[0]})
    return pd.DataFrame(rows).sort_values("pic", ascending=False)


def event_spike(m1: pd.DataFrame, times: pd.Series) -> float:
    """Amplitude M1 médiane à la minute de l'annonce, divisée par celle de la même minute les autres jours.

    Une annonce réelle donne un rapport nettement supérieur à 1. Une heure fausse donne environ 1.
    """
    rng = (m1["high"] - m1["low"])
    times = pd.DatetimeIndex(times).floor("min")
    at_event = rng.reindex(times).dropna()
    if at_event.empty:
        return np.nan
    minute = rng.index.hour * 60 + rng.index.minute
    baseline = rng.groupby(minute).median()
    ev_minutes = at_event.index.hour * 60 + at_event.index.minute
    return float(np.median(at_event.to_numpy() / baseline.reindex(ev_minutes).to_numpy()))
