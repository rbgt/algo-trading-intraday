"""Stratégie D2 : Breakout Price Action v2 (règles : docs/regles_breakout_price_action_v2.md).

Même logique que la version 1, en H1 (tendance) / M15 (lignes, cassure, zone) / M5 (pin bar),
avec les obliques et triangles à 3 touches.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import breakout_price_action as v1
from .breakout_price_action import generate_signals  # noqa: F401  (interface de stratégie)


@dataclass(frozen=True)
class Params(v1.Params):
    trend_tf: str = "1h"
    level_tf: str = "15min"
    use_trendlines: bool = True
