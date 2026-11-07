# Monte-Carlo : paramétrage ou stratégie ?

Question : les 5 stratégies rejetées l'ont-elles été à cause de **mauvais réglages**, ou parce que la **stratégie elle-même**
ne prévoit rien ?

Méthode (`python -m fxbt montecarlo`, période 2015–2021, coût de 1,1 pip) :
1. **Monte-Carlo sur les paramètres** : 300 jeux de réglages tirés au hasard par stratégie, dans des plages larges
   fixées avant le premier tirage (`PARAM_SPACE` dans chaque stratégie).
2. **Test contre le hasard** : mêmes trades que la stratégie avec ses réglages de base (mêmes heures, stops et objectifs),
   mais le sens est tiré à pile ou face, 10 000 fois. Chaque trade est simulé indépendamment.

## Résultats

### 1. Monte-Carlo sur les paramètres (300 tirages)

| Stratégie | Tirages positifs sur les 2 paires | Tirages qui passent les critères | R médian EUR/USD | R médian GBP/USD |
|---|---|---|---|---|
| EMA Breakout | 0 % | 0 % | −0,127 | −0,066 |
| London Breakout | 0 % | 0 % | −0,089 | −0,054 |
| Contre-tendance | 12 % | 0 % | −0,018 | +0,003 |
| Breakout Price Action v1 | 4 % | 0 % | −0,115 | −0,183 |
| Breakout Price Action v2 | 5 % | 0 % | −0,131 | −0,072 |

« Passer les critères » : au moins +0,05 R sur les deux paires et au moins 150 trades par paire.

### 2. Test contre le hasard (réglages de base)

Part des 10 000 versions « sens au hasard » qui font **aussi bien ou mieux** que la stratégie. Sous 5 %, la stratégie
prévoirait réellement le sens.

| Stratégie | EUR/USD | GBP/USD |
|---|---|---|
| EMA Breakout | 67 % | 10 % |
| London Breakout | 61 % | 20 % |
| Contre-tendance | 42 % | 39 % |
| Breakout Price Action v1 | 14 % | 56 % |
| Breakout Price Action v2 | 19 % | 14 % |

## Conclusion : c'est la stratégie, pas le paramétrage

- **Aucun des 1 500 jeux de réglages** ne remplit les critères. Pour l'EMA Breakout et le London Breakout, aucun n'est
  même positif sur les deux paires.
- **Aucune stratégie ne bat le hasard** : sur les 10 comparaisons, aucune n'est sous 5 %. Avec 10 essais, en voir une
  vers 10 % est normal par chance. Le signal de ces stratégies ne prévoit pas le sens du marché.
- **La contre-tendance est la plus proche de zéro** (R médian −0,02 et +0,00), mais c'est parce que ses stops larges
  rendent le coût presque négligeable, pas parce qu'elle a un avantage : elle ne fait pas mieux que le hasard (environ 40 %).
- **Les « meilleurs » tirages sont des mirages** : le meilleur tirage du Breakout Price Action v1 fait +0,32 R sur EUR/USD
  et +0,20 R sur GBP/USD, mais sur 56 et 65 trades seulement. Choisir ce réglage serait de la suroptimisation pure :
  sur 300 tirages, quelques-uns sortent toujours très bien par chance.

Les tableaux complets (un tirage par ligne) sont écrits dans `results/montecarlo_<stratégie>.csv`.
