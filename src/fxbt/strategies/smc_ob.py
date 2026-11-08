"""Stratégie G-OB : comme G (smc), avec entrée sur l'order block ICT (règles : docs/regles_smc.md, section 6).

Order block (achat) : la dernière bougie M5 baissière entre l'extrême du sweep (inclus) et les 5 bougies qui le
précèdent. Signal au premier contact M1 avec son plus haut ; le FVG reste obligatoire comme preuve d'impulsion.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import smc


@dataclass(frozen=True)
class Params(smc.Params):
    entry_zone: str = "ob"


generate_signals = smc.generate_signals
PARAM_SPACE = smc.PARAM_SPACE
