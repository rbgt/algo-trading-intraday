"""Ligne de commande.

    python -m fxbt download --pairs EURUSD GBPUSD
    python -m fxbt download-histdata --pairs EURUSD GBPUSD
    python -m fxbt import-histdata --pairs EURUSD GBPUSD
    python -m fxbt check --pairs EURUSD GBPUSD
    python -m fxbt backtest --strategy london_breakout
    python -m fxbt backtest --strategy ema_breakout --param rr=1.5 --costs 1.1
    python -m fxbt sweep --strategy london_breakout --grid rr=1,1.5,2 --grid entry_end_hour=10,11
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, economic_calendar
from .simulation import metrics, montecarlo
from .simulation.engine import Account, Converter, run
from .strategies import STRATEGIES

# Conception sur 2015–2021. 2022 → aujourd'hui est réservé à une seule validation finale.
PERIODS = {
    "is": ("2015-01-01", "2022-01-01"),
    "oos": ("2022-01-01", None),
}
WARMUP_DAYS = 60
RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


def _cast(cls, key: str, raw: str):
    fields = {f.name: f for f in dataclasses.fields(cls)}
    if key not in fields:
        sys.exit(f"Paramètre inconnu : {key}. Disponibles : {', '.join(fields)}")
    default = fields[key].default
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "oui", "yes")
    return type(default)(raw)


def _parse_params(cls, overrides: list[str]):
    values = {}
    for item in overrides:
        key, _, raw = item.partition("=")
        values[key] = _cast(cls, key, raw)
    return cls(**values)


def _news_times(pair: str, window_min: int):
    """Heures des annonces à fort impact des deux devises de la paire (pour le filtre d'annonces)."""
    if not window_min:
        return None
    cal = economic_calendar.load_calendar(currencies=(pair[:3], pair[3:]))
    return np.sort(cal["time"].dt.tz_convert("UTC").to_numpy("datetime64[ns]").astype("int64"))


def _load(pairs: list[str], period: str, source: str):
    """M1 de chaque paire (et d'EUR/USD pour la conversion), avec une marge de préchauffage."""
    start, end = PERIODS[period]
    load_start = (pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)).date().isoformat()
    m1s = {p: data.load_m1(p, load_start, end, source) for p in sorted(set(pairs) | {"EURUSD"})}
    converter = Converter({p: df["close"] for p, df in m1s.items()})
    return m1s, converter, pd.Timestamp(start, tz=data.TZ)


def cmd_download(args):
    for pair in args.pairs:
        data.download(pair, args.start_year, args.end_year)


def cmd_download_histdata(args):
    for pair in args.pairs:
        data.download_histdata(pair, args.start_year)


def cmd_download_indices(args):
    for path in data.download_indices():
        print(f"{path.stem} : ok")


def cmd_download_calendar(args):
    print(f"Calendrier : {economic_calendar.download_calendar()}")


def cmd_check_calendar(args):
    cal = economic_calendar.load_calendar()
    start, end = PERIODS["is"]
    cal = cal[(cal["time"] >= pd.Timestamp(start, tz=data.TZ)) & (cal["time"] < pd.Timestamp(end, tz=data.TZ))]
    print(f"{len(cal)} annonces à fort impact, 2015–2021 | heures : {cal['time_source'].value_counts().to_dict()}")
    m1s = {p: data.load_m1(p, start, end, args.source) for p in ("EURUSD", "GBPUSD")}
    print("Pic = amplitude M1 à l'heure de l'annonce ÷ amplitude habituelle à cette minute (≈ 1 si l'heure est fausse)")
    print(economic_calendar.spike_report(cal, m1s).to_string(index=False))


def cmd_import_histdata(args):
    for pair in args.pairs:
        paths = data.import_histdata(pair)
        print(f"{pair} : {len(paths)} mois importés ({paths[0].stem[-7:]} → {paths[-1].stem[-7:]})")


def cmd_compare(args):
    for pair in args.pairs:
        a, b = data.load_m1(pair, source="dukascopy"), data.load_m1(pair, source="histdata")
        print(f"\n=== {pair} : Dukascopy vs HistData ===")
        print(data.compare_sources(a, b, pair).to_string(index=False))


def cmd_check(args):
    for pair in args.pairs:
        m1 = data.load_m1(pair, source=args.source)
        print(f"\n=== {pair} : {len(m1):,} bougies M1, de {m1.index[0]} à {m1.index[-1]} ===")
        print(f"Prix min/max : {m1['low'].min():.5f} / {m1['high'].max():.5f}")
        print(data.check(m1).to_string())


def cmd_backtest(args):
    if args.period != "is" and not args.final:
        sys.exit(
            "La période hors échantillon (2022 → aujourd'hui) ne sert qu'une fois, pour la validation finale.\n"
            "Ajouter --final pour confirmer."
        )
    start, end = PERIODS[args.period]
    module = STRATEGIES[args.strategy]
    params = _parse_params(module.Params, args.param)
    account = Account(capital=args.capital, lot_step=args.lot_step)
    print(f"Stratégie : {args.strategy}  |  période : {start} → {end or 'aujourd’hui'}  |  source : {args.source}")
    print(f"Paramètres : {params}")
    print(f"Compte : {account}")
    print(f"Filtre d'annonces : {f'± {args.news_filter} min autour des annonces à fort impact' if args.news_filter else 'désactivé'}\n")

    m1s, converter, tz_start = _load(args.pairs, args.period, args.source)
    RESULTS_DIR.mkdir(exist_ok=True)

    rows, base_trades = [], {}
    for pair in args.pairs:
        signals = module.generate_signals(m1s[pair], params, pair)
        signals = signals[signals["entry_time"] >= tz_start]
        for cost in args.costs:
            trades = run(signals, m1s[pair], pair, params, account, cost, converter,
                         _news_times(pair, args.news_filter), args.news_filter)
            rows.append({"paire": pair, "coût_pips": cost, **metrics.summarize(trades, account.capital)})
            out = RESULTS_DIR / f"{args.strategy}_{args.period}_{pair}_{cost}.csv"
            trades.to_csv(out, index=False)
            if cost == args.costs[0]:
                base_trades[pair] = trades

    print(pd.DataFrame(rows).to_string(index=False))
    for pair, trades in base_trades.items():
        print(f"\n--- {pair}, par année (coût {args.costs[0]} pip) ---")
        print(metrics.by_year(trades).to_string())
    print(f"\nTrades détaillés : {RESULTS_DIR}/")


def cmd_sweep(args):
    """Test de sensibilité sur la période de conception uniquement."""
    module = STRATEGIES[args.strategy]
    base = _parse_params(module.Params, args.param)
    grid = {}
    for item in args.grid:
        key, _, raw = item.partition("=")
        grid[key] = [_cast(module.Params, key, v) for v in raw.split(",")]
    account = Account(capital=args.capital, lot_step=args.lot_step)
    m1s, converter, tz_start = _load(args.pairs, "is", args.source)

    rows = []
    for combo in itertools.product(*grid.values()):
        params = dataclasses.replace(base, **dict(zip(grid, combo)))
        row = dict(zip(grid, combo))
        for pair in args.pairs:
            signals = module.generate_signals(m1s[pair], params, pair)
            trades = run(signals[signals["entry_time"] >= tz_start], m1s[pair], pair, params, account, args.cost, converter,
                         _news_times(pair, args.news_filter), args.news_filter)
            m = metrics.summarize(trades, account.capital)
            row |= {f"{pair}_trades": m["trades"], f"{pair}_R_moyen": m.get("R_moyen"), f"{pair}_PF": m.get("profit_factor")}
        rows.append(row)
        print(row, flush=True)

    table = pd.DataFrame(rows)
    print(f"\n=== {args.strategy}, 2015–2021, coût {args.cost} pip ===")
    print(table.to_string(index=False))
    RESULTS_DIR.mkdir(exist_ok=True)
    table.to_csv(RESULTS_DIR / f"sweep_{args.strategy}.csv", index=False)


def cmd_montecarlo(args):
    """Monte-Carlo sur les paramètres et test contre le hasard, période de conception uniquement."""
    start, end = PERIODS["is"]
    load_start = (pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)).date().isoformat()
    tz_start = pd.Timestamp(start, tz=data.TZ)
    m1s, converter = montecarlo.load(args.pairs, load_start, end, args.source)
    RESULTS_DIR.mkdir(exist_ok=True)
    strategies = sorted(STRATEGIES) if args.strategy == "toutes" else [args.strategy]
    for name in strategies:
        print(f"\n========== {name} ==========")
        table = montecarlo.param_montecarlo(name, args.samples, args.seed, args.pairs, load_start, end, start,
                                            args.source, args.cost, args.workers)
        table.to_csv(RESULTS_DIR / f"montecarlo_{name}.csv", index=False)
        print(f"Monte-Carlo sur les paramètres ({args.samples} tirages, coût {args.cost} pip) :")
        for k, v in montecarlo.summarize_montecarlo(table, args.pairs).items():
            print(f"  {k} : {v}")
        null = montecarlo.direction_null(name, STRATEGIES[name].Params(), m1s, converter, tz_start,
                                         args.pairs, args.cost, args.flips, args.seed)
        print(f"Test contre le hasard (réglages de base, {args.flips} tirages du sens) :")
        print(null.to_string(index=False))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fxbt")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="Télécharger les M1 Dukascopy (Bid)")
    d.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    d.add_argument("--start-year", type=int, default=2014)
    d.add_argument("--end-year", type=int, default=pd.Timestamp.now().year)
    d.set_defaults(func=cmd_download)

    dh = sub.add_parser("download-histdata", help="Télécharger les M1 HistData.com dans data/histdata/")
    dh.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    dh.add_argument("--start-year", type=int, default=2014)
    dh.set_defaults(func=cmd_download_histdata)

    di = sub.add_parser("download-indices", help="Télécharger les indices actions (S&P 500, DAX, FTSE 100)")
    di.set_defaults(func=cmd_download_indices)

    dc = sub.add_parser("download-calendar", help="Télécharger le calendrier économique (Forex Factory 2007–2025)")
    dc.set_defaults(func=cmd_download_calendar)

    cc = sub.add_parser("check-calendar", help="Vérifier les heures du calendrier avec les pics de volatilité")
    cc.add_argument("--source", choices=sorted(data.SOURCES), default="histdata")
    cc.set_defaults(func=cmd_check_calendar)

    h = sub.add_parser("import-histdata", help="Importer les fichiers HistData de data/histdata/")
    h.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    h.set_defaults(func=cmd_import_histdata)

    k = sub.add_parser("compare", help="Comparer Dukascopy et HistData sur leur période commune")
    k.add_argument("--pairs", nargs="+", default=["EURUSD"])
    k.set_defaults(func=cmd_compare)

    c = sub.add_parser("check", help="Contrôler la qualité des données")
    c.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    c.add_argument("--source", choices=sorted(data.SOURCES), default="histdata")
    c.set_defaults(func=cmd_check)

    b = sub.add_parser("backtest", help="Lancer un backtest")
    b.add_argument("--strategy", choices=sorted(STRATEGIES), required=True)
    b.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    b.add_argument("--costs", nargs="+", type=float, default=[1.1, 1.5, 2.0], help="coût aller-retour en pips")
    b.add_argument("--period", choices=sorted(PERIODS), default="is")
    b.add_argument("--final", action="store_true", help="autoriser la période hors échantillon")
    b.add_argument("--param", action="append", default=[], metavar="CLÉ=VALEUR", help="modifier un paramètre")
    b.add_argument("--capital", type=float, default=100.0)
    b.add_argument("--lot-step", type=int, default=1, help="pas de taille en unités (1000 = micro-lot)")
    b.add_argument("--source", choices=sorted(data.SOURCES), default="histdata")
    b.add_argument("--news-filter", type=int, default=0, metavar="MIN",
                   help="pas d'entrée à moins de MIN minutes d'une annonce à fort impact (0 = désactivé)")
    b.set_defaults(func=cmd_backtest)

    w = sub.add_parser("sweep", help="Test de sensibilité (période de conception seulement)")
    w.add_argument("--strategy", choices=sorted(STRATEGIES), required=True)
    w.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    w.add_argument("--grid", action="append", required=True, metavar="CLÉ=V1,V2,…", help="valeurs à tester")
    w.add_argument("--param", action="append", default=[], metavar="CLÉ=VALEUR", help="paramètre fixe")
    w.add_argument("--cost", type=float, default=1.1, help="coût aller-retour en pips")
    w.add_argument("--capital", type=float, default=100.0)
    w.add_argument("--lot-step", type=int, default=1)
    w.add_argument("--source", choices=sorted(data.SOURCES), default="histdata")
    w.add_argument("--news-filter", type=int, default=0, metavar="MIN")
    w.set_defaults(func=cmd_sweep)

    mc = sub.add_parser("montecarlo", help="Monte-Carlo sur les paramètres et test contre le hasard (2015–2021)")
    mc.add_argument("--strategy", choices=sorted(STRATEGIES) + ["toutes"], default="toutes")
    mc.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    mc.add_argument("--samples", type=int, default=300, help="nombre de jeux de réglages tirés")
    mc.add_argument("--flips", type=int, default=10_000, help="tirages du sens pour le test contre le hasard")
    mc.add_argument("--seed", type=int, default=0)
    mc.add_argument("--cost", type=float, default=1.1)
    mc.add_argument("--workers", type=int, default=montecarlo.default_workers())
    mc.add_argument("--source", choices=sorted(data.SOURCES), default="histdata")
    mc.set_defaults(func=cmd_montecarlo)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
