"""Registre des stratégies.

Pour en ajouter une : créer un module avec une dataclass `Params` (héritant de
`engine.BaseParams`) et une fonction `generate_signals(m1, params)`, puis
l'enregistrer ci-dessous.
"""

from . import breakout_pa_v2, breakout_price_action, contre_tendance, ema_breakout, london_breakout

STRATEGIES = {
    "ema_breakout": ema_breakout,
    "london_breakout": london_breakout,
    "contre_tendance": contre_tendance,
    "breakout_price_action": breakout_price_action,
    "breakout_pa_v2": breakout_pa_v2,
}
