# Stratégie F : Poursuite après une surprise macroéconomique

> Règles validées et commitées **avant tout test**. Elles ne changent plus au vu des résultats.

## 1. L'idée et sa cause

Quand un chiffre macroéconomique sort **très différent du consensus** des analystes, le marché doit réviser ses
anticipations (taux d'intérêt, croissance). La première réaction se fait en quelques secondes, et elle est réservée aux
algorithmes. Mais l'ajustement complet peut prendre plus longtemps : les gros acteurs repositionnent leurs portefeuilles
sur plusieurs heures. On cherche à capter cette **poursuite**, en entrant après le premier choc, quand le spread est
revenu à la normale.

Les signaux ne sont **pas techniques** : ils viennent uniquement de l'écart entre le chiffre publié et le consensus.

## 2. Données

- Calendrier Forex Factory (`economic_calendar.py`), annonces **à fort impact**, programmées (sans discours ni réunions),
  pour USD, EUR et GBP, avec un chiffre réel **et** un consensus.
- **Sens** donné par le champ « Usual Effect » de Forex Factory : en général, « réel > consensus est bon pour la devise »
  (et « plus restrictif que prévu » pour les banques centrales) ; pour certains chiffres comme le chômage, c'est l'inverse.
  Les annonces « sans effet constant » sont ignorées.
- **Réserve** : le fichier contient moins d'annonces avec consensus sur les années récentes (environ 490 en 2015, environ
  200 en 2021). Le nombre de trades sera donc plus faible en fin de période.

## 3. Règles

1. **Surprise normalisée** : `z = (réel − consensus) / écart-type des 20 surprises précédentes du même événement`
   (au moins 8 surprises passées ; l'historique remonte à 2007). Le signe de `z` est inversé si un chiffre plus bas est bon
   pour la devise. Ainsi, `z > 0` veut toujours dire « bon pour la devise ».
2. **Annonces simultanées** (par exemple NFP, chômage et salaires à 14h30) : on **additionne** les `z` des annonces d'une
   même devise publiées à la même minute.
3. **Signal** si `|z| ≥ 1`, c'est-à-dire une surprise au moins égale à la surprise typique de cet événement.
4. **Paires** : une annonce USD se trade sur EUR/USD **et** GBP/USD ; une annonce EUR seulement sur EUR/USD ; une annonce
   GBP seulement sur GBP/USD. Bon pour l'USD : on vend la paire. Bon pour l'EUR ou le GBP : on l'achète.
5. **Horaires** (choix de Rick) : annonces publiées entre **8h00 et 16h15** (heure de Zurich). Entrée **15 minutes après**
   l'annonce, sortie forcée à **17h00**, jamais de position la nuit.
6. **Stop de protection** : 0,5 × ATR14 journalier de la veille. Pas d'objectif : la sortie se fait à 17h.
7. **Gestion** : 2 trades par jour et par paire au maximum, arrêt après 2 pertes consécutives. Risque de 1 %, levier 1:5,
   coût de 1,1 pip.

## 4. Critères de réussite (fixés à l'avance)

Sur 2015–2021, coût de 1,1 pip, la stratégie est retenue **seulement si toutes les conditions sont remplies** :

1. R moyen net **≥ +0,05** sur EUR/USD **et** GBP/USD.
2. Profit factor **≥ 1,10** sur chaque paire.
3. Au moins **4 années positives sur 7** sur chaque paire.
4. R moyen net encore **positif à 1,5 pip**.
5. Au moins **150 trades** par paire.
6. **Test contre le hasard** (sens tiré à pile ou face, 10 000 fois) : moins de **5 %** des tirages font aussi bien sur chaque paire.
7. Toutes les variantes de la section 5 restent **positives** sur les deux paires.

## 5. Variantes de sensibilité (fixées à l'avance)

| Réglage | Base | Variantes |
|---|---|---|
| Seuil de surprise `|z|` | 1,0 | 0,5 · 1,5 |
| Délai d'entrée après l'annonce | 15 min | 5 min · 30 min |
| Sortie | 17h00 | 2 h après l'entrée |
| Stop (× ATR journalier) | 0,5 | 0,3 · 1,0 |
| Confirmation | aucune | le mouvement des 15 premières minutes va dans le sens de la surprise |

## 6. Résultat (2015–2021, HistData) : **rejetée**

Test lancé après le commit des règles ci-dessus, sans modification.

| Paire | Trades | Réussite | R moyen net (1,1 pip) | R brut (sans coût) | Profit factor | Années positives |
|---|---|---|---|---|---|---|
| EUR/USD | 368 | 44 % | −0,050 | −0,024 | 0,82 | 1 / 7 |
| GBP/USD | 435 | 46 % | −0,036 | −0,017 | 0,87 | 2 / 7 |

Aucun critère n'est rempli.
- **Variantes** : les 8 variantes de la section 5 sont toutes négatives sur les deux paires (de −0,02 à −0,07 R).
- **Monte-Carlo** (200 jeux de réglages tirés dans les plages `PARAM_SPACE`) : aucun n'est positif sur les deux paires.
  R médian de −0,04 sur EUR/USD et de −0,03 sur GBP/USD.
- **Test contre le hasard** : 86 % (EUR/USD) et 90 % (GBP/USD) des tirages à pile ou face font **mieux** que la
  stratégie. Le sens de la surprise ne prévoit pas la suite du mouvement 15 minutes après l'annonce.

Ce qu'on apprend :
- **Le marché intègre la surprise en moins de 15 minutes**, même 5 minutes (variante). Après, il ne reste pas de
  poursuite exploitable : le gain brut est même légèrement négatif.
- La stratégie fait un peu **moins bien** que le hasard (elle est dans les 10 à 14 % les plus faibles), ce qui pourrait
  suggérer un léger retour en arrière après l'annonce. Ce n'est **pas** significatif, et inverser le sens après coup serait
  de la suroptimisation. Ce serait une nouvelle hypothèse, à écrire et à tester à part.
- **Les signaux ne sont pas techniques**, et le résultat est pourtant le même que pour les stratégies techniques : sur ces
  marchés, l'information publique est intégrée trop vite pour un particulier.

La période 2022–2026 n'a pas été utilisée.
