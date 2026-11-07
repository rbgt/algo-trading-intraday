# algo-trading-python

Recherche de stratégies forex intraday (EUR/USD, GBP/USD) sur plus de 10 ans de données
M1 (HistData, Dukascopy), avec un moteur de backtest simple et vérifiable.

## Démarrage rapide

```bash
# 1. Installer (une seule fois)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. Récupérer et préparer les données (une seule fois, environ 5 minutes)
.venv/bin/python -m fxbt download-histdata --pairs EURUSD GBPUSD
.venv/bin/python -m fxbt import-histdata --pairs EURUSD GBPUSD
.venv/bin/python -m fxbt check          # contrôle qualité : bougies, trous

# 3. Lancer un backtest
.venv/bin/python -m fxbt backtest --strategy london_breakout
```

Toutes les commandes s'utilisent sous la forme `.venv/bin/python -m fxbt <commande> [options]`.
`--help` affiche l'aide, par exemple `.venv/bin/python -m fxbt backtest --help`.

## Guide du backtest

### Stratégies disponibles

| Nom (`--strategy`) | Idée | Règles | Statut |
|---|---|---|---|
| `ema_breakout` | Signal M5 dans le sens de la tendance M15 | `src/fxbt/strategies/ema_breakout.py` | Rejetée |
| `london_breakout` | Cassure de la zone asiatique | `src/fxbt/strategies/london_breakout.py` | Rejetée |
| `contre_tendance` | Retour à la moyenne journalière | `docs/regles_contre_tendance.md` | Rejetée |

### La commande `backtest`

```bash
.venv/bin/python -m fxbt backtest --strategy contre_tendance
```

Par défaut, elle teste **les deux paires**, sur la **période de conception (2015–2021)**, avec
**trois niveaux de coûts** (1,1, 1,5 et 2 pips aller-retour), et un capital de 100 €.

| Option | Rôle | Par défaut |
|---|---|---|
| `--strategy NOM` | Stratégie à tester (obligatoire) | — |
| `--pairs EURUSD GBPUSD` | Paires à tester | les deux |
| `--costs 1.1 1.5 2.0` | Coût aller-retour en pips (spread et glissement) | `1.1 1.5 2.0` |
| `--param CLÉ=VALEUR` | Modifier un réglage de la stratégie (répétable) | réglages de base |
| `--period is` ou `oos` | `is` = 2015–2021 (conception), `oos` = 2022 → aujourd'hui (validation) | `is` |
| `--final` | Obligatoire avec `--period oos` (voir plus bas) | — |
| `--capital 100` | Capital de départ en EUR | `100` |
| `--lot-step 1000` | Pas de taille : `1` = à l'unité, `1000` = micro-lots réels | `1` |
| `--source histdata` ou `dukascopy` | Source des données | `histdata` |

**Modifier un réglage.** Les réglages possibles sont les champs de la classe `Params` de chaque
stratégie, par exemple `rr`, `stop_atr` ou `entry_end_hour`. Un nom inconnu affiche la liste complète.

```bash
.venv/bin/python -m fxbt backtest --strategy contre_tendance --param rr=2.0 --param stretch=1.0
.venv/bin/python -m fxbt backtest --strategy london_breakout --pairs EURUSD --costs 1.1
```

### Lire le résultat

Le premier tableau donne une ligne par paire et par niveau de coût :

| Colonne | Signification |
|---|---|
| `trades` | Nombre de trades. Moins de quelques centaines, ce n'est pas assez pour conclure. |
| `réussite_%` | Pourcentage de trades gagnants. Seul, ça ne veut rien dire : il faut le lire avec le R moyen. |
| `R_moyen` | **Le chiffre clé** : gain moyen par trade en multiples du risque. +0,10 veut dire qu'on gagne en moyenne 10 % de la mise risquée par trade. |
| `R_total` | Somme des R de tous les trades. |
| `profit_factor` | Gains totaux ÷ pertes totales. Au-dessus de 1, c'est gagnant ; il faut viser 1,1 ou plus. |
| `DD_max_R` | Pire baisse, en R, depuis un sommet. |
| `DD_max_%` | Pire baisse du capital, en %, depuis un sommet. |
| `capital_final` | Capital à la fin, en EUR (composé). |
| `risque_moyen_%` | Risque réellement pris par trade. Il est souvent sous 1 % à cause du levier 1:5 et des 100 €. |

Viennent ensuite les **résultats par année** pour chaque paire, au premier niveau de coût. Une stratégie
solide gagne la plupart des années, pas seulement une ou deux.

**Ce qui compte pour décider**, dans l'ordre : le R moyen sur **les deux paires**, la régularité par
année, puis le fait que le résultat tienne quand le coût monte.

### Le détail des trades

Chaque lancement écrit un CSV par paire et par coût dans `results/`, par exemple
`results/contre_tendance_is_EURUSD_1.1.csv`. On peut l'ouvrir dans Excel ou Numbers.

| Colonne | Contenu |
|---|---|
| `entry_time`, `exit_time` | Heures d'entrée et de sortie (Zurich) |
| `direction` | `1` = achat, `-1` = vente |
| `entry`, `exit`, `stop`, `target` | Prix d'entrée, de sortie, du stop et de l'objectif |
| `stop_pips` | Distance du stop en pips |
| `reason` | Motif de sortie : `stop`, `target`, ou `time` (sortie forcée à 17h) |
| `r` | Résultat du trade en R, coûts déduits |
| `units`, `risk_eur` | Taille de la position et risque réel en EUR |
| `pnl_eur`, `equity` | Gain ou perte du trade et capital après le trade |

### Tester la sensibilité : `sweep`

`sweep` teste plusieurs valeurs d'un réglage d'un coup, uniquement sur 2015–2021 et à un seul coût.
Il sert à vérifier qu'un résultat ne dépend pas d'un réglage précis.

```bash
.venv/bin/python -m fxbt sweep --strategy contre_tendance --grid rr=1.0,1.5,2.0
.venv/bin/python -m fxbt sweep --strategy london_breakout --grid rr=1,2 --grid entry_end_hour=10,11
```

Avec plusieurs `--grid`, toutes les combinaisons sont testées. Le tableau final est aussi enregistré dans
`results/sweep_<stratégie>.csv`.

### La validation finale (2022 → aujourd'hui)

```bash
.venv/bin/python -m fxbt backtest --strategy <retenue> --period oos --final
```

Cette période ne sert **qu'une seule fois**, pour la stratégie retenue, avec ses réglages figés. Si on
la regarde plusieurs fois et qu'on ajuste entre deux, elle ne prouve plus rien. Sans `--final`, la
commande refuse de tourner.

### La méthode, en résumé

1. Écrire les règles et les critères de réussite **avant** de tester, puis les commiter
   (voir `docs/regles_contre_tendance.md`).
2. Tester sur 2015–2021 avec `backtest`, sur les deux paires.
3. Vérifier la stabilité avec `sweep`, uniquement sur les variantes prévues à l'avance.
4. Si tous les critères sont remplis : une seule validation avec `--period oos --final`.
5. Si un critère échoue : abandonner l'idée, sans l'ajuster.

### Autres commandes

| Commande | Rôle |
|---|---|
| `download-histdata` | Télécharge les fichiers HistData dans `data/histdata/` |
| `import-histdata` | Convertit ces fichiers en parquet mensuels, en gérant le fuseau horaire |
| `check` | Contrôle qualité par année : nombre de bougies, trous de plus de 30 minutes |
| `compare` | Compare HistData et Dukascopy minute par minute |
| `download` | Télécharge depuis Dukascopy (lent, avec un risque de blocage) |

Les données vont dans `data/` et les résultats dans `results/` ; aucun des deux n'est versionné. Une analyse
utilise toujours une seule source, sans mélange.

## Sources de données

Source principale : **HistData.com** (gratuit, M1). `download-histdata` récupère les années complètes,
puis les mois terminés de l'année en cours, dans `data/histdata/`.

**Fuseau horaire** : contrairement à ce qu'annonce le site, les fichiers sont en heure de New York jusqu'en
2018, puis en UTC−5 avec l'heure d'été européenne à partir de 2019. L'import gère les deux cas. Ça a été
vérifié contre Dukascopy, minute par minute, et sur l'heure de réouverture du marché le dimanche.

Source secondaire : **Dukascopy** (`download`). Le serveur limite fortement le débit et bannit
l'adresse IP pendant des heures (erreur 429) si on insiste. Elle sert surtout à vérifier HistData
avec `compare`.

## Organisation

| Fichier | Rôle |
|---|---|
| `src/fxbt/data.py` | Import HistData, téléchargement Dukascopy, conversion en heure de Zurich, agrégation M5/M15/jour, contrôles |
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

- **Prix** : bougies Bid (HistData ou Dukascopy). Le spread et le glissement sont modélisés par un coût
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
