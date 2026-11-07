# Stratégie D2 : Breakout Price Action v2 (H1 / M15 / M5, avec obliques)

> Règles commitées **avant tout test**. Elles ne changent plus au vu des résultats.
> Ce sont les règles de la version 1 (`docs/regles_breakout_price_action.md`), avec deux changements demandés par Rick :
> 1. unités de temps **H1 / M15 / M5** au lieu de H4 / H1 / M5 ;
> 2. ajout des **obliques et triangles**, avec un critère de **3 touches**.
>
> Les choix marqués *(choix)* ne viennent pas de la méthode manuelle.

## 1. Ce qui change par rapport à la version 1

| Élément | Version 1 | Version 2 |
|---|---|---|
| Tendance (« sens du fleuve ») | H4 | **H1** (même définition : 2 derniers sommets et creux confirmés) |
| Niveaux, cassure, zone de chasse | H1 | **M15** |
| Déclencheur | Pin bar M5 | Pin bar M5 (inchangé) |
| Lignes utilisées | Horizontales | Horizontales **et obliques à 3 touches** |
| ATR des seuils (force, zone, tolérance) | ATR14 H1 | **ATR14 M15** |

Les durées restent exprimées **en nombre de bougies**, comme dans la méthode manuelle (« 100 à 150 bougies ») :
un niveau vit 150 bougies M15 (environ 1,5 jour de marché), et le pullback a 24 bougies M15 (6 heures).

## 2. Obliques et triangles

- **Oblique de résistance** : une droite qui passe par **au moins 3 sommets M15 confirmés**. On la trace entre deux
  sommets A et C, et au moins un sommet intermédiaire B doit se trouver à moins de **0,1 × ATR14 M15** de la droite
  *(choix : la tolérance)*.
- **Oblique de support** : même chose avec les creux.
- **Ligne valide à sa naissance** : aucune clôture M15 ne l'a franchie entre A et C. Sinon, elle est « percée au
  milieu des corps », donc morte.
- **Toutes les pentes sont acceptées** (descendante, montante, plate). Une ligne plate à 3 touches est une
  résistance horizontale renforcée.
- **Triangle** : deux obliques qui convergent. Sa cassure est la cassure de l'une des deux obliques, donc elle est
  couverte par la règle ci-dessus sans règle à part *(choix)*.
- **Durée de vie** : 150 bougies M15 après la dernière touche.
- **Après la cassure**, la zone de chasse **suit la pente** de l'oblique prolongée : on attend le retour du prix
  sur la ligne là où elle se trouve au moment du pullback *(choix)*.

Les niveaux horizontaux simples (un seul sommet ou creux) de la version 1 restent actifs.

## 3. Règles (achat ; la vente est le symétrique)

1. **Filtre H1** : la tendance H1 est haussière. Achats seulement.
2. **Cassure M15** : une bougie de force M15 (corps ≥ 0,7 × ATR14 M15, clôture dans le quart haut) clôture
   au-dessus d'une résistance valide, horizontale ou oblique. Une clôture au-dessus sans bougie de force tue la ligne.
   Si plusieurs lignes sont cassées en même temps, on garde la plus proche de la clôture.
3. **Zone de chasse** : la ligne (prolongée si oblique) ± 0,2 × ATR14 M15 de la bougie de cassure.
4. **Annulation** : une clôture M15 sous le bas de la zone (fausse cassure), ou 24 bougies M15 sans signal.
5. **Signal** : une pin bar haussière M5 dans la zone, sur une bougie ouverte entre **8h00 et 11h55**,
   avec une tendance H1 encore haussière.
6. **Entrée** à l'ouverture M5 suivante. **Stop** 2 pips sous la mèche. **Objectif** : le plus haut atteint
   depuis la cassure, et trade ignoré s'il est à moins de 1 R.
7. **Sortie forcée à 17h.** 2 trades par jour au maximum, arrêt après 2 pertes consécutives. Une zone ne sert qu'une fois.

`N` = 3 pour les sommets et creux, sur H1 et sur M15.

## 4. Critères de réussite (inchangés)

Sur 2015–2021, coût de 1,1 pip, **toutes les conditions** suivantes doivent être remplies :
R moyen net ≥ +0,05 sur les deux paires ; profit factor ≥ 1,10 sur chaque paire ; au moins 4 années positives sur 7 ;
R moyen encore positif à 1,5 pip ; au moins 150 trades par paire ; toutes les variantes de la section 5 positives.

**Mise en garde** : c'est la 2ᵉ version d'une méthode déjà rejetée. Chaque nouvelle version augmente la probabilité
de trouver un résultat positif par hasard. Un éventuel succès sur 2015–2021 devra absolument être confirmé sur 2022–2026.

## 5. Variantes de sensibilité (fixées à l'avance)

| Réglage | Base | Variantes |
|---|---|---|
| `N` (sommets et creux) | 3 | 2 · 5 |
| Tolérance des 3 touches (× ATR M15) | 0,1 | 0,05 · 0,2 |
| Corps de la bougie de force (× ATR M15) | 0,7 | 0,5 · 1,0 |
| Largeur de la zone (× ATR M15) | 0,2 | 0,1 · 0,3 |
| Délai du pullback (bougies M15) | 24 | 12 · 48 |
| Filtre H1 | actif | désactivé |
| Obliques | actives | désactivées (horizontales seules, en H1 / M15 / M5) |

## 6. Résultat (2015–2021, HistData) : **rejetée**

Test lancé après le commit des règles ci-dessus, sans modification.

| Paire | Trades | Réussite | R moyen net (1,1 pip) | Profit factor | Années positives | Stop médian | Objectif médian |
|---|---|---|---|---|---|---|---|
| EUR/USD | 94 | 34 % | −0,19 | 0,76 | 2 / 7 | 5,4 pips | 1,9 R |
| GBP/USD | 95 | 40 % | +0,045 | 1,07 | 4 / 7 | 7,2 pips | 2,1 R |

Critères non remplis : EUR/USD est négatif, GBP/USD reste sous +0,05 R et devient négatif à 1,5 pip, et il y a moins de
150 trades par paire. **Les 13 variantes sont toutes négatives sur EUR/USD** (de −0,08 à −0,41 R). GBP/USD oscille
entre −0,08 et +0,10 R selon les réglages : c'est le profil d'un résultat dû au hasard sur environ 100 trades, pas d'un avantage.

Ce qu'on apprend :
- **Les obliques à 3 touches sont bien détectées** : environ 28 % des zones sur les deux paires. Mais elles n'apportent
  rien : sans elles, le résultat est un peu **meilleur** (−0,10 R sur EUR/USD, +0,10 R sur GBP/USD), avec le même nombre
  de trades.
- **Passer en H1 / M15 / M5** multiplie les cassures (environ 11 000 zones au lieu de 2 400), mais le nombre de trades
  reste d'environ 95 par paire. Le goulot d'étranglement est la combinaison « pullback entre 8h et 12h, pin bar, tendance alignée ».
- **Le stop reste trop serré** (5 à 7 pips) : le coût pèse environ 0,15 à 0,2 R par trade, comme dans la version 1.
- Le résultat de GBP/USD sur cette version (+0,045 R) ne doit **pas** être utilisé pour choisir une version 3 :
  ce serait ajuster la méthode aux données.

La période 2022–2026 n'a pas été utilisée.
