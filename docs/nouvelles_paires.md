# USD/CHF et BTC/USD : les 7 stratégies sur deux nouveaux instruments

Période de conception : 2015–2021 pour USD/CHF, **septembre 2017**–2021 pour le BTC (pas de données Binance avant).
Coût de base de chaque instrument : 1,5 pip pour USD/CHF (spread plus large), **0,2 % du prix** aller-retour pour le BTC.
Le levier est plafonné à 1:5 pour le forex et à **1:2 pour le BTC** (plafond réglementaire européen pour les cryptos).
Les stratégies sont lancées avec leurs réglages de base, sans aucune modification.

| Stratégie | USD/CHF : trades | R net | R brut | BTC : trades | R net | R brut |
|---|---|---|---|---|---|---|
| EMA Breakout | 2 482 | −0,34 | −0,01 | 1 502 | −0,62 | +0,07 |
| London Breakout | 1 340 | −0,10 | +0,03 | 512 | −0,13 | +0,07 |
| Contre-tendance | 1 094 | −0,05 | −0,01 | 994 | −0,10 | −0,02 |
| Breakout Price Action v1 | 99 | −0,15 | +0,16 | 66 | −1,29 | −0,16 |
| Breakout Price Action v2 | 88 | −0,37 | −0,06 | 105 | −1,16 | −0,10 |
| Fixing de fin de mois | 84 | **+0,07** | +0,12 | — | — | — |
| Surprise macro | 323 | −0,08 | −0,04 | 154 | −0,05 | +0,03 |

« R brut » : sans aucun coût. Le fixing ne s'applique pas au BTC (pas d'indice actions de référence).

## Lecture

- **Même verdict qu'avant.** Les gains bruts restent proches de zéro (entre −0,16 et +0,16 R), et les coûts font
  basculer presque tout en perte.
- **Le BTC est pénalisé par ses coûts** : 0,2 % du prix, c'est environ 60 $ à 30 000 $. Les stratégies à stop serré
  (EMA Breakout, Breakout Price Action) perdent entre 0,6 et 1,3 R par trade.
- **Le fixing sur USD/CHF (+0,07 R)** n'est **pas** un résultat. Cette stratégie a été rejetée sur ses paires prévues
  (EUR/USD et GBP/USD). En la testant sur une nouvelle paire, on multiplie les chances d'un résultat positif dû au hasard.
  Sa t-stat est de 0,96 sur 84 trades, loin du seuil de 2, et 2021 est très négative (−0,34 R).

Données : USD/CHF depuis HistData (même contrôle du fuseau horaire que les autres paires : réouverture à 17h à New York) ;
BTC/USDT depuis Binance (`data.binance.vision`, public), 4,8 millions de bougies M1, 39 trous de plus de 30 minutes
(pannes connues de Binance en 2018 et 2019).
