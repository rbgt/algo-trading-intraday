"""Stratégies : règles et signaux, sans dépendance au moteur de simulation.

Pour en ajouter une : créer un module qui respecte l'interface décrite dans base.py,
puis l'enregistrer ci-dessous.
"""

from . import breakout_pa_v2, breakout_price_action, contre_tendance, ema_breakout, fixing_fin_de_mois, london_breakout, smc, smc_ob, surprise_annonces

STRATEGIES = {
    "ema_breakout": ema_breakout,
    "london_breakout": london_breakout,
    "contre_tendance": contre_tendance,
    "breakout_price_action": breakout_price_action,
    "breakout_pa_v2": breakout_pa_v2,
    "fixing_fin_de_mois": fixing_fin_de_mois,
    "surprise_annonces": surprise_annonces,
    "smc": smc,
    "smc_ob": smc_ob,
}
