# Stratégie G : Smart Money Concepts (sweep de liquidité, CHoCH, FVG)

> Règles validées et commitées **avant tout test**. Elles ne changent plus au vu des résultats.
> Elles traduisent en règles chiffrées le schéma SMC le plus courant en session de Londres :
> chasse aux stops de la zone asiatique, changement de structure, puis entrée au retour dans le déséquilibre.
> Les choix marqués *(choix)* sont des valeurs que la méthode SMC ne fixe pas.

## 1. Traduction des notions SMC

| Notion SMC | Définition automatique |
|---|---|
| **Liquidité** | Le plus haut et le plus bas de la **zone asiatique**, entre 00h00 et 07h00 (heure de Zurich), comme pour la stratégie B. |
| **Killzone** | La fenêtre de Londres : sweep et CHoCH entre **08h00 et 10h55**, entrée possible jusqu'à **11h55**. |
| **Sweep** (chasse aux stops, achat) | Une bougie M5 dont le plus bas passe **sous le bas asiatique**, suivie dans les **6 bougies M5** (30 min, en comptant la bougie de dépassement) d'une **clôture M5 revenue au-dessus** du bas asiatique. *(choix : 6 bougies)* |
| **Extrême du sweep** | Le plus bas atteint depuis le premier dépassement. Il est mis à jour tant que le CHoCH n'a pas eu lieu. |
| **Sommet de swing M5** | Une bougie M5 dont le plus haut dépasse celui des `N` bougies avant **et** des `N` bougies après. Il n'est connu qu'après la clôture de la `N`-ième bougie suivante. `N` = 2. *(choix)* |
| **CHoCH** (changement de caractère) | Une **clôture M5 au-dessus du dernier sommet de swing confirmé** avant l'extrême du sweep, dans les **24 bougies M5** (2 h) qui suivent le premier dépassement. Sinon, le setup est abandonné. *(choix : 24 bougies)* |
| **Jambe impulsive** | Les bougies M5 de l'extrême du sweep jusqu'à la bougie du CHoCH incluse. |
| **Fair Value Gap** (FVG, achat) | Trois bougies M5 consécutives de la jambe impulsive avec **plus haut de la 1ʳᵉ < plus bas de la 3ᵉ**. La zone va du plus haut de la 1ʳᵉ (bas du FVG) au plus bas de la 3ᵉ (haut du FVG). On garde le **dernier** FVG de la jambe. Sans FVG, pas de trade. *(choix : le dernier)* |
| **Order block** (achat) | La **dernière bougie M5 baissière** (clôture < ouverture) **avant l'impulsion** : on la cherche en remontant depuis la bougie de l'extrême du sweep (incluse), sur 5 bougies au plus. La zone va de son plus bas à son plus haut, mèches comprises. Elle n'est valide que si la jambe impulsive contient un FVG et produit un CHoCH (définition ICT). Utilisé par la version G-OB, voir la section 6. |

La vente est le symétrique : sweep du **haut** asiatique, CHoCH sous le dernier creux de swing, FVG baissier
(plus bas de la 1ʳᵉ > plus haut de la 3ᵉ).

## 2. Règles (achat ; la vente est le symétrique)

Toutes les heures sont en heure de Zurich.

1. **Zone asiatique** : plus haut et plus bas M1 entre 00h00 et 06h59.
2. **Sweep** du bas asiatique, avec réintégration dans les 6 bougies M5, entre 08h00 et 10h55. Seul le
   **premier dépassement** du jour compte pour chaque côté : s'il n'est pas réintégré ou ne donne pas de CHoCH,
   ce côté est abandonné pour la journée. Journée ignorée s'il manque plus de 120 minutes dans la zone asiatique
   (garde-fou contre les trous de données).
3. **CHoCH M5** dans les 24 bougies M5 après le premier dépassement, au plus tard sur la bougie de 10h55.
4. **FVG** haussier dans la jambe impulsive. S'il n'y en a pas, le setup est abandonné.
5. **Signal** : la première bougie **M1** après la clôture du CHoCH dont le plus bas touche le **haut du FVG**.
   Le setup est abandonné si ce retour n'arrive pas dans les **12 bougies M5** (1 h) après le CHoCH,
   ou après 11h55. *(choix)*
6. **Entrée** : à l'ouverture de la bougie M1 suivante (règle du projet : jamais au prix du signal).
7. **Stop** : extrême du sweep **moins 1 pip**. Le trade est **ignoré si le stop fait moins de 8 pips**,
   pour que le coût ne pèse pas plus d'environ 0,14 R. *(choix)*
8. **Objectif** : **2 R**.
9. **Sortie forcée à 17h.** Au maximum un setup par côté et par jour (sweep du bas, sweep du haut), donc 2 trades
   par jour au plus, et arrêt après 2 pertes consécutives. Risque 1 %, levier 1:5. Pas de position ouverte
   en même temps qu'une autre.

## 3. Critères de réussite (fixés à l'avance)

Sur 2015–2021, coût de 1,1 pip, la stratégie est retenue **seulement si toutes les conditions sont remplies** :

1. R moyen net **≥ +0,05** sur EUR/USD **et** GBP/USD.
2. Profit factor **≥ 1,10** sur chaque paire.
3. Au moins **4 années positives sur 7** sur chaque paire.
4. R moyen net encore **positif à 1,5 pip**.
5. Au moins **150 trades** par paire.
6. **Test contre le hasard** (sens tiré à pile ou face, 10 000 fois) : moins de **5 %** des tirages font aussi bien sur chaque paire.
7. Toutes les variantes de la section 5 restent **positives** sur les deux paires.

En complément : Monte-Carlo de 300 jeux de réglages tirés dans les plages de la section 5, comme pour les
stratégies A à F. USD/CHF est donné à titre d'information, sans entrer dans le verdict.

## 4. Limites connues

- **Order blocks** : selon les sources, c'est la dernière bougie opposée avant l'impulsion, la dernière bougie
  avant le BOS, ou une zone englobant plusieurs bougies. La version G-OB (section 6) retient la définition ICT,
  fixée avant tout test.
- **Biais de plus haute unité de temps** : beaucoup de traders SMC ne prennent que les sweeps dans le sens du
  biais H4 ou journalier. Il est testé comme une variante (section 5), pas dans la version de base.
- **Premium / discount, inducement, SMT divergence** : non testés dans cette version.
- **Entrée** : en manuel, on placerait un ordre limite au haut du FVG. Ici, l'entrée se fait à l'ouverture
  de la bougie M1 qui suit le contact : parfois un peu mieux, parfois un peu moins bien qu'un ordre limite.
- **Volatilité à 8h** : le spread s'élargit souvent à l'ouverture de Londres. Le coût fixe de 1,1 pip peut
  le sous-estimer ; d'où le critère 4 à 1,5 pip.

## 5. Variantes de sensibilité (fixées à l'avance)

On change un réglage à la fois :

| Réglage | Base | Variantes |
|---|---|---|
| `N` (sommets et creux de swing M5) | 2 | 1 · 3 |
| Délai de réintégration du sweep (bougies M5) | 6 | 3 · 12 |
| Délai du CHoCH (bougies M5) | 24 | 12 · 48 |
| Délai du retour dans le FVG (bougies M5) | 12 | 6 · 24 |
| Stop minimal (pips) | 8 | 5 · 12 |
| Objectif | 2 R | 1,5 R · 3 R · côté opposé de la zone asiatique (au moins 1 R) |
| Biais journalier | aucun | achats seulement si la clôture de la veille est au-dessus de l'EMA 50 journalière (et l'inverse pour les ventes) |

## 6. Version G-OB : entrée sur l'order block (ajoutée avant tout test)

Ajoutée à la demande de Rick, toujours **avant tout test**. Même setup que G (sweep, CHoCH, FVG obligatoire comme
preuve d'impulsion) ; seule la zone d'entrée change.

**Pourquoi cette définition** : c'est celle d'ICT, à l'origine du vocabulaire SMC, et la seule qui se traduit
sans ambiguïté. « La dernière bougie de sens opposé avant le mouvement qui casse la structure » désigne une seule
bougie, alors que les zones « englobant plusieurs bougies » ou « tracées à l'œil » demandent un choix à chaque fois.
La condition de déplacement (FVG) et de cassure (CHoCH) est celle qui distingue, chez ICT, un order block valide
d'une simple bougie.

Règles (achat ; la vente est le symétrique, avec la dernière bougie haussière avant l'impulsion baissière) :

1. **Order block** : la dernière bougie M5 baissière entre la bougie de l'extrême du sweep (incluse) et les
   5 bougies qui la précèdent. S'il n'y en a pas, pas de trade.
2. **Signal** : la première bougie M1 après la clôture du CHoCH dont le plus bas touche le **haut de l'order block**
   (son bord proche), dans les 12 bougies M5 et avant 11h55.
3. **Entrée, stop, objectif, limites** : identiques à G (stop sous l'extrême du sweep moins 1 pip, au moins 8 pips,
   objectif 2 R, sortie à 17h).

Critères de réussite : les 7 de la section 3. Variantes : celles de la section 5, plus une entrée au **milieu de
l'order block** (« mean threshold » d'ICT).

## 7. Version swing (repo algo-trading-swing)

Le même schéma sur plusieurs jours est décrit dans `docs/regles_smc_swing.md` du repo swing.
