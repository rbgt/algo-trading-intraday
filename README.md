# algo-trading-intraday

Recherche de stratégies **intraday** (EUR/USD, GBP/USD, USD/CHF, BTC/USD) sur plus de 10 ans de données
M1 (HistData, Binance, Dukascopy), avec un moteur de backtest simple et vérifiable.

Les stratégies sur plusieurs jours sont dans le repo [algo-trading-swing](https://github.com/rbgt/algo-trading-swing),
qui utilise ce repo comme bibliothèque (paquet `fxbt` : données, moteur, mesures, Monte-Carlo).

## Conclusion (novembre 2026) : recherche arrêtée

**Aucune stratégie testée n'a d'avantage exploitable sur le forex**, ni en intraday ni en swing. La recherche sur le
forex est arrêtée.

| Approche | Repo | Résultat sur 2015–2021 (R moyen net par trade) |
|---|---|---|
| A. EMA Breakout (M5 / M15) | intraday | −0,18 (EUR/USD), −0,08 (GBP/USD) |
| B. London Breakout (cassure de la zone asiatique) | intraday | −0,11, −0,04 |
| C. Contre-tendance (retour à la moyenne journalière) | intraday | −0,03, −0,00 |
| D et D2. Breakout Price Action (H4 / H1 / M5) | intraday | de −0,27 à +0,05, variantes négatives |
| E. Fixing de fin de mois | intraday | −1,7 pip par trade, t = −0,70 |
| F. Surprise macro (annonces économiques) | intraday | −0,05, −0,04, R brut négatif |
| G. Smart Money Concepts (sweep, CHoCH, FVG ou order block) | intraday | de −0,41 à +0,05, ne bat pas le hasard |
| S1. Cassure de Donchian | swing | +0,16 réuni, mais seul le BTC est positif ; BTC seul en 2022–2026 : échec |
| S2. Momentum sur 12 mois | swing | −0,12 |
| S3 et S4. SMC en H4 (FVG ou order block) | swing | +0,015 et −0,21 |

Toutes ces approches ont suivi la même méthode : règles écrites et commitées avant le test, conception sur 2015–2021
seulement, coûts réalistes (spread, glissement, swap), sensibilité des réglages, Monte-Carlo sur les paramètres et
test contre le hasard (sens tiré à pile ou face). La période 2022 → 2026 n'a servi qu'une fois, pour le Donchian sur le BTC.

**Ce qu'on en retient**

- **Le problème est l'absence d'avantage brut, pas les coûts.** Sans aucun coût, la meilleure stratégie intraday
  gagne environ +0,06 R par trade. Un broker moins cher, des stops plus larges ou un filtre d'annonces ne changent
  aucun verdict.
- **C'est la logique des stratégies, pas le réglage.** Sur plus de 1 500 jeux de réglages tirés au hasard, aucun
  ne passe les critères.
- **Un résultat positif sur une seule paire est la signature du hasard.** Plusieurs stratégies gagnent sur GBP/USD
  et perdent sur EUR/USD, ou l'inverse.
- **Le capital ne change rien au verdict.** Avec 1 000 € au lieu de 100 €, les résultats en R sont identiques. Plus de
  capital rend les trades exécutables (micro-lot), pas rentables.
- **Le forex majeur est le marché le plus efficient.** Les avantages qui y existent demandent des moyens
  institutionnels (données, exécution, coûts) et une recherche à plein temps.

**Si la recherche reprend un jour**, les pistes les mieux documentées sont sur les **indices actions** (momentum
intraday sur le S&P 500 ou le Nasdaq, retour à la moyenne à court terme, effet de tournant de mois) ou dans
l'**investissement passif et multi-actifs**, avec la même méthode et les mêmes outils (`fxbt`).

## Démarrage rapide

```bash
# 1. Installer (une seule fois)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 2. Récupérer et préparer les données (une seule fois, environ 5 minutes)
.venv/bin/python -m fxbt download-histdata --pairs EURUSD GBPUSD USDCHF
.venv/bin/python -m fxbt import-histdata --pairs EURUSD GBPUSD USDCHF
.venv/bin/python -m fxbt download-binance   # BTC/USD (BTC/USDT de Binance, depuis août 2017)
.venv/bin/python -m fxbt download-indices   # S&P 500, DAX, FTSE 100 (stratégie fixing_fin_de_mois)
.venv/bin/python -m fxbt download-calendar  # calendrier économique 2007 → avril 2025
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
| `breakout_price_action` | Cassure H1, pullback, pin bar M5 (filtre H4) | `docs/regles_breakout_price_action.md` | Rejetée |
| `breakout_pa_v2` | Version H1 / M15 / M5, avec obliques et triangles à 3 touches | `docs/regles_breakout_price_action_v2.md` | Rejetée |
| `fixing_fin_de_mois` | Rééquilibrage de fin de mois au fixing de Londres (16h–17h) | `docs/regles_fixing_fin_de_mois.md` | Rejetée |
| `surprise_annonces` | Poursuite après une surprise macro (chiffre réel contre consensus), entrée 15 min après | `docs/regles_surprise_annonces.md` | Rejetée |
| `smc` | SMC : sweep de la zone asiatique, CHoCH M5, entrée au retour dans le FVG | `docs/regles_smc.md` | Rejetée |
| `smc_ob` | Comme `smc`, avec entrée sur l'order block (définition ICT) | `docs/regles_smc.md` | Rejetée |

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
| `--news-filter 30` | Pas d'entrée à moins de 30 min d'une annonce à fort impact (calendrier jusqu'en avril 2025) | désactivé |

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

### Instruments

| Instrument | Source | Depuis | Coûts testés (aller-retour) | Swap (nuit) | Levier max | Taille min |
|---|---|---|---|---|---|---|
| EUR/USD, GBP/USD | HistData | 2014 | 1,1 · 1,5 · 2 pips | 3 %/an, triple le mercredi | 1:5 | 1 unité |
| USD/CHF | HistData | 2014 | 1,5 · 2 · 2,5 pips | 3 %/an, triple le mercredi | 1:5 | 1 unité |
| BTC/USD | Binance (BTC/USDT) | août 2017 | 0,2 · 0,3 · 0,5 % du prix | 20 %/an, chaque nuit | 1:2 | 0,0001 BTC |

Le swap n'est payé que si la position passe 17h à New York (23h à Zurich) : il est sans effet sur les stratégies intraday
de ce repo. Variable d'environnement `FXBT_DATA_DIR` : dossier des données, si `fxbt` est utilisé depuis un autre repo.

Les caractéristiques sont dans `data.INSTRUMENTS`. `--costs` s'exprime dans l'unité de l'instrument. Par défaut, les
commandes testent EUR/USD et GBP/USD ; ajouter `--pairs USDCHF BTCUSD` pour les autres. Résultats des 7 stratégies sur
USD/CHF et BTC/USD : `docs/nouvelles_paires.md`.

### Paramétrage ou stratégie : `montecarlo`

```bash
.venv/bin/python -m fxbt montecarlo                                  # les 5 stratégies, environ 5 minutes
.venv/bin/python -m fxbt montecarlo --strategy contre_tendance --samples 500
```

Deux tests, uniquement sur 2015–2021 :
1. **Monte-Carlo sur les paramètres** : des jeux de réglages tirés au hasard dans les plages `PARAM_SPACE` de la
   stratégie. Si une bonne part gagne sur les deux paires, c'est le réglage qui pèche ; si presque tous perdent,
   c'est la stratégie. Il faut lire la distribution, pas le meilleur tirage, qui est flatteur par chance.
2. **Test contre le hasard** : les mêmes trades avec un sens tiré à pile ou face. La colonne
   `part_du_hasard_qui_fait_mieux_%` doit être sous 5 % pour que le signal prévoie vraiment le sens du marché.

Résultats et conclusion pour les 5 stratégies : `docs/montecarlo.md`.

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
| `download-binance` | Télécharge les M1 du BTC/USDT depuis Binance (public, depuis août 2017) |
| `download-calendar` | Télécharge le calendrier économique (Forex Factory, 2007 → avril 2025) dans `data/calendar/` |
| `check-calendar` | Vérifie les heures du calendrier avec les pics de volatilité M1 |
| `download-indices` | Télécharge les clôtures du S&P 500, du DAX et du FTSE 100 (Yahoo Finance) dans `data/indices/` |
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

### Calendrier économique

Source : jeu de données public [Forex Factory Calendar](https://huggingface.co/datasets/Tropstan/Forex_Factory_Calendar)
(licence MIT, 2007 → 7 avril 2025), avec le réel, le consensus, le précédent et le niveau d'impact. Il ne couvre pas la fin de
la période de validation (après avril 2025).

**Heures manquantes** : 35 à 50 % des annonces n'ont pas d'heure dans le fichier (elles sont placées à minuit, heure de Téhéran).
La date est juste. L'heure est déduite des 5 publications connues les plus proches du même événement, dans l'heure locale
de son pays. `check-calendar` vérifie le résultat avec les prix : à l'heure d'une annonce, l'amplitude M1 est de 8 à 20 fois
l'amplitude habituelle (NFP, Fed, BCE, Banque d'Angleterre) ; décalée d'une heure, le rapport retombe vers 1.
Les discours, auditions et réunions sont exclus par défaut : ils n'ont pas d'heure de réaction précise.

## Organisation

Le code est séparé en trois blocs. Les dépendances vont dans un seul sens : la simulation exécute les
stratégies, mais les stratégies ne connaissent pas la simulation.

```
src/fxbt/
├── data.py                  # DONNÉES : téléchargement, import, fuseau horaire, agrégation, contrôles
├── economic_calendar.py     # DONNÉES : calendrier économique, heures déduites et vérifiées
├── strategies/              # STRATÉGIES : règles et signaux uniquement
│   ├── base.py              #   interface commune (BaseParams, colonnes des signaux)
│   ├── indicators.py        #   EMA, RSI, ATR, sommets et creux
│   ├── ema_breakout.py
│   ├── london_breakout.py
│   ├── contre_tendance.py
│   ├── breakout_price_action.py
│   └── breakout_pa_v2.py
├── simulation/              # SIMULATION : exécution et évaluation
│   ├── engine.py            #   moteur : taille, levier, coûts, sorties résolues en M1
│   ├── metrics.py           #   réussite, R moyen, profit factor, drawdown, par année
│   └── montecarlo.py        #   Monte-Carlo sur les paramètres et test contre le hasard
└── __main__.py              # ligne de commande
docs/                        # règles de chaque stratégie, écrites avant le test, et verdicts
tests/                       # test_data.py, test_strategies.py, test_simulation.py
```

### Ajouter une stratégie

Créer `src/fxbt/strategies/ma_strategie.py` en respectant l'interface décrite dans `strategies/base.py` :
- une dataclass `Params(BaseParams)`, qui contient tous les réglages et les limites par jour ;
- une fonction `generate_signals(m1, params, pair)`, qui renvoie un DataFrame de signaux candidats
  (colonnes `SIGNAL_COLUMNS`, plus la colonne facultative `target_level` pour un objectif à un niveau de prix) ;
- un dictionnaire `PARAM_SPACE`, qui donne les plages de tirage pour le Monte-Carlo.

Puis l'ajouter au dictionnaire `STRATEGIES` dans `strategies/__init__.py`. Une stratégie n'importe rien
de `simulation/`.

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
