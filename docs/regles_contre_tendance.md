# Stratégie C : Retour à la moyenne contre-tendance

> Règles écrites **avant tout test**. Elles ne changent pas au vu des résultats.
> Les variantes de la section 4 sont fixées dès maintenant ; aucune autre ne sera ajoutée après coup.

## 1. L'idée

Quand le prix s'est **beaucoup éloigné** de sa moyenne journalière, on parie qu'il va **revenir
partiellement** vers elle. On attend que le mouvement intraday commence à se retourner pour entrer.

**Origine de l'idée.** Dans les backtests de l'EMA Breakout (2015–2021), les signaux pris contre la
tendance journalière avaient un gain brut de +0,10 à +0,12 R sur les deux paires, contre environ 0 pour
ceux pris dans le sens de la tendance. Comme l'idée vient de ces mêmes données, le résultat sur
2015–2021 sera **trop optimiste**. Seule la validation 2022–2026 tranchera.

## 2. Règles

Toutes les heures sont en heure de Zurich. La journée journalière se termine à 17h, heure de New York.

### Contexte du jour (bougie journalière de la veille, clôturée)
- `C` = clôture de la veille, `EMA50` = EMA 50 journalière, `ATR` = ATR 14 journalier.
- Écart à la moyenne : `E = (C − EMA50) / ATR`.
- Si `E ≥ +0,5`, le marché est **étiré à la hausse** : seules les **ventes** sont autorisées ce jour-là.
- Si `E ≤ −0,5`, le marché est **étiré à la baisse** : seuls les **achats** sont autorisés.
- Sinon, pas de trade.

### Déclencheur (M15)
- Bougie M15 ouverte entre **8h00 et 11h45**.
- **Vente** : la clôture M15 passe **sous** l'EMA 20 M15 (clôture précédente au-dessus ou égale).
- **Achat** : la clôture M15 passe **au-dessus** de l'EMA 20 M15 (clôture précédente en dessous ou égale).
- Entrée à l'**ouverture de la bougie M15 suivante**.

### Sortie
- **Stop** : 0,5 × `ATR` journalier, depuis le prix d'entrée (environ 30 à 45 pips sur EUR/USD,
  45 à 60 pips sur GBP/USD).
- Trade ignoré si le stop fait moins de **20 pips** (garde-fou contre les coûts).
- **Objectif** : 1,5 R.
- **Sortie forcée à 17h**.

### Gestion
- **1 trade par jour au maximum.**
- Risque 1 %, levier 1:5 maximum, même moteur et mêmes coûts que pour les stratégies A et B.

## 3. Critères de réussite (fixés à l'avance)

Sur 2015–2021, coût de 1,1 pip, la stratégie est retenue **seulement si toutes les conditions sont remplies** :

1. R moyen net **≥ +0,05** sur **EUR/USD et sur GBP/USD**.
2. Profit factor **≥ 1,10** sur chaque paire.
3. Au moins **4 années positives sur 7** sur chaque paire.
4. R moyen net **encore positif à 1,5 pip** de coût.
5. **Au moins 150 trades** par paire.
6. Toutes les variantes de la section 4 restent **positives** : pas de falaise.

Si elle passe : une seule validation sur 2022–2026, avec les mêmes critères 1, 2 et 4.
Si elle échoue : on l'abandonne, sans « petit ajustement ».

## 4. Variantes de sensibilité (fixées à l'avance)

On change un réglage à la fois, les autres restent à leur valeur de base :

| Réglage | Base | Variantes |
|---|---|---|
| Seuil d'étirement `E` | 0,5 | 0 · 1,0 |
| Stop (× ATR journalier) | 0,5 | 0,4 · 0,6 |
| Objectif (R) | 1,5 | 1,0 · 2,0 |
| Fin de la fenêtre d'entrée | 12h | 11h |

## 5. Résultat (2015–2021, HistData) : **rejetée**

Test lancé après le commit des règles ci-dessus, sans modification.

| Paire | Trades | R moyen net (1,1 pip) | Profit factor | Années positives | R moyen net (1,5 pip) |
|---|---|---|---|---|---|
| EUR/USD | 1 118 | −0,026 | 0,93 | 2 / 7 | −0,037 |
| GBP/USD | 1 120 | −0,004 | 0,99 | 3 / 7 | −0,011 |

Critères 1, 2, 3, 4 et 6 non remplis. Toutes les variantes de la section 4 donnent entre −0,05 et +0,004 R,
donc rien de proche du seuil de +0,05 R.

Ce qu'on apprend :
- Le stop large a bien fonctionné comme prévu : le coût ne pèse plus qu'environ 0,02 à 0,03 R par trade.
  Mais le gain **brut** est nul (+0,003 R sur EUR/USD, +0,016 R sur GBP/USD) : il n'y a rien à protéger.
- Un étirement plus fort (`E` ≥ 1,0) donne un résultat **pire**, alors que l'idée prédisait l'inverse.
  C'est un argument direct contre l'hypothèse du retour à la moyenne.
- 60 % des trades sortent à 17h : sur une demi-journée, le prix ne revient pas assez vers sa moyenne
  pour atteindre 1,5 R.
- L'écart « contre la tendance » vu dans l'EMA Breakout (+0,10 R brut) ne se retrouve pas ici. C'était
  probablement du bruit, ou un effet lié aux stops minuscules de cette stratégie.

La période 2022–2026 n'a pas été utilisée.
