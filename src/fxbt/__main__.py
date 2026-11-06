"""Ligne de commande.

    python -m fxbt download --pairs EURUSD GBPUSD
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

import pandas as pd

from . import data, metrics
from .engine import Account, Converter, run
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


def _load(pairs: list[str], period: str):
    """M1 de chaque paire (et d'EUR/USD pour la conversion), avec une marge de préchauffage."""
    start, end = PERIODS[period]
    load_start = (pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)).date().isoformat()
    m1s = {p: data.load_m1(p, load_start, end) for p in sorted(set(pairs) | {"EURUSD"})}
    converter = Converter({p: df["close"] for p, df in m1s.items()})
    return m1s, converter, pd.Timestamp(start, tz=data.TZ)


def cmd_download(args):
    for pair in args.pairs:
        data.download(pair, args.start_year, args.end_year)


def cmd_check(args):
    for pair in args.pairs:
        m1 = data.load_m1(pair)
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
    print(f"Stratégie : {args.strategy}  |  période : {start} → {end or 'aujourd’hui'}")
    print(f"Paramètres : {params}")
    print(f"Compte : {account}\n")

    m1s, converter, tz_start = _load(args.pairs, args.period)
    RESULTS_DIR.mkdir(exist_ok=True)

    rows, base_trades = [], {}
    for pair in args.pairs:
        signals = module.generate_signals(m1s[pair], params)
        signals = signals[signals["entry_time"] >= tz_start]
        for cost in args.costs:
            trades = run(signals, m1s[pair], pair, params, account, cost, converter)
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
    m1s, converter, tz_start = _load(args.pairs, "is")

    rows = []
    for combo in itertools.product(*grid.values()):
        params = dataclasses.replace(base, **dict(zip(grid, combo)))
        row = dict(zip(grid, combo))
        for pair in args.pairs:
            signals = module.generate_signals(m1s[pair], params)
            trades = run(signals[signals["entry_time"] >= tz_start], m1s[pair], pair, params, account, args.cost, converter)
            m = metrics.summarize(trades, account.capital)
            row |= {f"{pair}_trades": m["trades"], f"{pair}_R_moyen": m.get("R_moyen"), f"{pair}_PF": m.get("profit_factor")}
        rows.append(row)
        print(row, flush=True)

    table = pd.DataFrame(rows)
    print(f"\n=== {args.strategy}, 2015–2021, coût {args.cost} pip ===")
    print(table.to_string(index=False))
    RESULTS_DIR.mkdir(exist_ok=True)
    table.to_csv(RESULTS_DIR / f"sweep_{args.strategy}.csv", index=False)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fxbt")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="Télécharger les M1 Dukascopy (Bid)")
    d.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    d.add_argument("--start-year", type=int, default=2014)
    d.add_argument("--end-year", type=int, default=pd.Timestamp.now().year)
    d.set_defaults(func=cmd_download)

    c = sub.add_parser("check", help="Contrôler la qualité des données")
    c.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
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
    b.set_defaults(func=cmd_backtest)

    w = sub.add_parser("sweep", help="Test de sensibilité (période de conception seulement)")
    w.add_argument("--strategy", choices=sorted(STRATEGIES), required=True)
    w.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD"])
    w.add_argument("--grid", action="append", required=True, metavar="CLÉ=V1,V2,…", help="valeurs à tester")
    w.add_argument("--param", action="append", default=[], metavar="CLÉ=VALEUR", help="paramètre fixe")
    w.add_argument("--cost", type=float, default=1.1, help="coût aller-retour en pips")
    w.add_argument("--capital", type=float, default=100.0)
    w.add_argument("--lot-step", type=int, default=1)
    w.set_defaults(func=cmd_sweep)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
