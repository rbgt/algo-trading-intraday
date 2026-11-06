# algo-trading-python

Recherche de stratégies forex intraday (EUR/USD, GBP/USD) sur plus de 10 ans de données
Dukascopy M1, avec un moteur de backtest simple et vérifiable. Le contexte complet et la
méthode sont décrits dans [CLAUDE.md](CLAUDE.md).

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Utilisation

```bash
# 1. Données : M1 Bid, de 2014 à aujourd'hui (2014 sert au préchauffage des indicateurs)
.venv/bin/python -m fxbt download --pairs EURUSD GBPUSD
.venv/bin/python -m fxbt check

# 2. Backtest sur la période de conception (2015–2021), coûts de 1,1, 1,5 et 2 pips
.venv/bin/python -m fxbt backtest --strategy london_breakout
.venv/bin/python -m fxbt backtest --strategy ema_breakout

# Test de sensibilité : modifier un paramètre
.venv/bin/python -m fxbt backtest --strategy london_breakout --param rr=2.0 --param entry_end_hour=10

# Validation finale, une seule fois (2022 → aujourd'hui)
.venv/bin/python -m fxbt backtest --strategy <retenue> --period oos --final
```

Les trades détaillés sont écrits dans `results/`. Les données vont dans `data/` (non versionné).

## Organisation

| Fichier | Rôle |
|---|---|
| `src/fxbt/data.py` | Téléchargement Dukascopy, conversion en heure de Zurich, agrégation M5/M15/jour, contrôle qualité |
| `src/fxbt/indicators.py` | EMA, RSI, ATR (lissage de Wilder, comme TradingView) |
| `src/fxbt/engine.py` | Simulation des trades en M1 : taille, levier, coûts, limites par jour |
| `src/fxbt/metrics.py` | Réussite, R moyen, profit factor, drawdown, résultats par année |
| `src/fxbt/strategies/` | Une stratégie par module, enregistrée dans `STRATEGIES` |

### Ajouter une stratégie

Créer `src/fxbt/strategies/ma_strategie.py` avec :
- une dataclass `Params(BaseParams)`, qui contient tous les réglages et les limites par jour ;
- une fonction `generate_signals(m1, params)`, qui renvoie un DataFrame de signaux candidats
  (colonnes décrites dans `engine.SIGNAL_COLUMNS`).

Puis l'ajouter au dictionnaire `STRATEGIES` dans `strategies/__init__.py`.

## Hypothèses de simulation

- **Prix** : bougies Bid Dukascopy. Le spread et le glissement sont modélisés par un coût
  fixe aller-retour en pips (1,1 pip par défaut, testé aussi à 1,5 et 2).
- **Signal** sur la clôture d'une bougie, **entrée** à l'ouverture de la suivante.
- **Sorties résolues en M1** : si le stop et l'objectif sont touchés dans la même minute, le stop
  est compté d'abord. Un gap au-delà du stop est exécuté à l'ouverture. Sortie forcée à
  l'ouverture de la minute de 17h.
- **Taille** : `min(risque_EUR / (distance_stop × taux_cotation→EUR), capital × 5 × 0,98 / taux_base→EUR)`,
  avec le capital composé. Avec 100 €, c'est souvent le plafond de levier qui limite la taille :
  le risque réel est alors inférieur à 1 % (colonne `risque_moyen_%`). Les résultats en **R** ne
  dépendent pas de la taille.
- **Journée forex** (pour l'ATR et l'EMA journaliers) : clôture à 17h, heure de New York, comme les bougies « D » de TradingView.

### Écarts connus avec les versions Pine Script
- London Breakout : la distance du stop est calculée depuis le prix d'entrée réel (ouverture
  suivante), et non depuis la clôture du signal. Une journée est ignorée si la zone asiatique a
  moins de 20 bougies M15 (trous de données).
- Pas de filtre d'annonces macro (pas de calendrier économique historique pour l'instant).
