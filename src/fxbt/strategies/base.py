"""Interface commune des stratégies.

Une stratégie est un module qui définit :
- une dataclass `Params` qui hérite de `BaseParams` (tous ses réglages, limites par jour comprises) ;
- une fonction `generate_signals(m1, params, pair)` qui renvoie un DataFrame de signaux candidats
  (`pair` sert aux stratégies qui ont besoin de données propres à la paire) ;
- un dictionnaire `PARAM_SPACE` (plages de tirage pour le Monte-Carlo).

Les stratégies ne connaissent pas le moteur : c'est la simulation qui les exécute.
"""

from __future__ import annotations

from dataclasses import dataclass

# Colonnes attendues dans le DataFrame de signaux :
#   entry_time   ouverture de la bougie d'entrée (Timestamp, heure de Zurich)
#   direction    +1 achat, -1 vente
#   stop_dist    distance du stop en prix (NaN si stop_level est donné)
#   stop_level   niveau de stop absolu (NaN si stop_dist est donné)
#   rr           objectif en multiples de R
#   deadline     sortie forcée à l'ouverture de la première minute ≥ deadline
#   day          journée de trading (Timestamp normalisé), pour les limites par jour
# Colonne facultative :
#   target_level objectif à un niveau de prix absolu ; remplace alors rr
SIGNAL_COLUMNS = ["entry_time", "direction", "stop_dist", "stop_level", "rr", "deadline", "day"]


@dataclass(frozen=True)
class BaseParams:
    """Règles de gestion communes, que chaque stratégie hérite et règle."""

    max_trades_per_day: int = 1
    max_consec_losses: int = 0  # 0 = pas de limite
    flat_hour: int = 17
    min_stop_pips: float = 0.0  # trade ignoré si le stop est plus court
    min_target_r: float = 0.0  # avec target_level : trade ignoré si l'objectif est à moins de ce nombre de R
