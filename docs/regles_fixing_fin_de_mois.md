# Stratégie E : Rééquilibrage de fin de mois au fixing de Londres

> Règles commitées **avant tout test**. Elles ne changent plus au vu des résultats.

## 1. L'idée et sa cause économique

Le **fixing WM/Reuters** de 16h à Londres (17h à Zurich, toute l'année, car le Royaume-Uni et la Suisse changent
d'heure aux mêmes dates) sert de prix de référence aux fonds du monde entier. Beaucoup d'ordres y sont exécutés.

**Mécanisme** (Melvin et Prins, *Equity hedging and exchange rates at the London 4 p.m. fix*, 2015) : les investisseurs
européens qui détiennent des actions américaines couvrent leur risque de change en vendant du dollar à terme. Si les
actions américaines ont **plus monté** que les actions européennes pendant le mois, la valeur en dollars de leurs
portefeuilles a grossi : leur couverture est trop faible. À la fin du mois, ils **vendent du dollar** pour la
rééquilibrer, et ces ordres passent au fixing. L'inverse se produit si les actions américaines ont moins monté.

Ces flux sont **prévisibles** à partir de données publiques connues avant le fixing.

**Réserves connues avant le test** :
- l'effet a été publié en 2015 ; il a pu être exploité et réduit depuis ;
- en février 2015, la fenêtre de calcul du fixing est passée de 1 à 5 minutes, ce qui peut avoir changé la dynamique ;
- **horaires** : le trade a lieu de 16h à 17h, **en dehors de la fenêtre 8h–12h** des règles de Rick. C'est un test de
  recherche. Un passage en démo demanderait une décision explicite de Rick sur cette exception.

## 2. Règles

- **Jour du signal** : le dernier jour ouvré du mois (dernier jour de semaine avec des cotations à 16h, heure de Zurich).
- **Indices** (clôtures Yahoo Finance, en monnaie locale) : S&P 500 pour les États-Unis ; **DAX** pour EUR/USD et
  **FTSE 100** pour GBP/USD.
- **Performance du mois** de chaque indice : de la dernière clôture du mois précédent à la dernière clôture **avant**
  le jour du signal. Ces deux valeurs sont connues avant 16h.
- **Écart** `D = performance S&P 500 − performance de l'indice européen`.
- Si `D > 0` : on vend du dollar, donc on **achète** EUR/USD ou GBP/USD. Si `D < 0` : on **vend** la paire.
- **Entrée à 16h00** (heure de Zurich). **Sortie à 17h00**, au fixing.
- **Stop de protection** : 0,5 × ATR14 journalier de la veille. Pas d'objectif : la sortie se fait à l'heure.
- Un trade par mois et par paire. Risque de 1 %, levier 1:5, coût de 1,1 pip, comme pour les autres stratégies.

## 3. Critères de réussite (fixés à l'avance)

Il n'y a qu'environ 84 trades par paire sur 2015–2021 : les critères portent donc sur le **résultat en pips** et sur sa
**significativité statistique**, pas sur 150 trades minimum.

Sur 2015–2021, coût de 1,1 pip, la stratégie est retenue **seulement si toutes les conditions sont remplies** :

1. Gain moyen net **positif sur EUR/USD et sur GBP/USD**.
2. Sur les deux paires réunies, **t-stat ≥ 2,0** du gain net en pips. Autrement dit, il y a moins d'environ 5 % de
   chances d'obtenir un tel résultat par hasard.
3. Au moins **5 années positives sur 7**, les deux paires réunies.
4. Gain moyen net encore **positif à 1,5 pip** de coût, les deux paires réunies.
5. Toutes les variantes de la section 4 sont **positives**, les deux paires réunies.

## 4. Variantes de sensibilité (fixées à l'avance)

| Réglage | Base | Variantes |
|---|---|---|
| Heure d'entrée | 16h00 | 15h00 · 16h30 |
| Écart minimal `|D|` pour trader | 0 % | 2 % |
| Stop (× ATR journalier) | 0,5 | 1,0 |

## 5. Résultat (2015–2021, HistData) : **rejetée**

Test lancé après le commit des règles ci-dessus, sans modification.

| Cas | Trades | Pips moyens nets | EUR/USD | GBP/USD | t-stat | Années positives |
|---|---|---|---|---|---|---|
| Base, 1,1 pip | 168 | −1,7 | −1,8 | −1,7 | −0,70 | 4 / 7 |
| Base, 1,5 pip | 168 | −2,1 | −2,2 | −2,1 | −0,87 | 3 / 7 |
| Base, sans coût (brut) | 168 | −0,6 | −0,7 | −0,6 | −0,26 | 4 / 7 |
| Entrée 15h00 | 168 | −2,0 | −3,9 | −0,1 | −0,74 | 2 / 7 |
| Entrée 16h30 | 168 | −0,8 | −0,5 | −1,1 | −0,39 | 5 / 7 |
| Écart minimal 2 % | 89 | −0,4 | −5,6 | +5,3 | −0,10 | 5 / 7 |
| Stop 1,0 × ATR | 168 | −2,0 | −2,5 | −1,6 | −0,81 | 4 / 7 |

Aucun critère n'est rempli : le gain est négatif sur les deux paires, et la t-stat est loin de +2 (elle est même négative).

Par année (base, en pips cumulés sur les deux paires) : 2015 −73, 2016 +84, 2017 +174, 2018 +8, 2019 −48, 2020 +127,
**2021 −563** (22 trades perdants sur 24 : les données ont été vérifiées trade par trade et sont correctes).

Ce qu'on apprend :
- **Les flux de fin de mois existent bien** : entre 16h et 17h le dernier jour du mois, EUR/USD et GBP/USD bougent souvent
  de 15 à 40 pips. Mais la règle publique (l'écart de performance des indices actions) **ne prévoit pas leur sens**
  sur 2015–2021. L'effet a probablement été exploité après sa publication en 2015, ou noyé par d'autres flux.
- **Ne pas inverser le sens** à cause de 2021 : sur les autres années, le résultat est mitigé, pas inversé. Choisir le
  sens après coup serait de la suroptimisation.

La période 2022–2026 n'a pas été utilisée.
