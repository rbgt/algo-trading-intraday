# Stratégie D : Breakout Price Action (H4 / H1 / M5)

> Règles validées et commitées **avant tout test**. Elles ne changent plus au vu des résultats.
> Elles traduisent en règles chiffrées la méthode manuelle « Breakout Price Action ».
> Les choix marqués *(choix)* sont des valeurs que la méthode manuelle ne précisait pas.

## 1. Traduction des notions visuelles

| Notion manuelle | Définition automatique |
|---|---|
| **Sommet / creux** (« sommet majeur », niveau) | Une bougie dont le plus haut dépasse celui des `N` bougies avant **et** des `N` bougies après. Elle n'est connue qu'après la clôture de la `N`-ième bougie suivante, ce qui évite de « voir le futur ». |
| **Tendance H4** (« sens du fleuve ») | Haussière si les 2 derniers sommets H4 confirmés montent **et** les 2 derniers creux montent ; baissière si les deux descendent ; sinon neutre, et pas de trade. |
| **Niveau H1** (résistance ou support) | Un sommet (ou creux) H1 confirmé, de moins de 150 bougies H1 (environ 1,5 semaine). |
| **Ligne « morte »** (percée au milieu des corps) | Le niveau est supprimé dès qu'un **corps** de bougie H1 le traverse sans être la bougie de cassure valide (voir ci-dessous). |
| **Bougie de force** (cassure) | Une bougie H1 qui clôture au-delà du niveau, avec un corps d'au moins 0,7 × ATR14 H1, et qui clôture dans le quart extrême de sa bougie. *(choix)* |
| **Zone de chasse** (rectangle) | Le niveau cassé ± 0,2 × ATR14 H1. *(choix)* |
| **Pin bar M5** (haussière) | Une mèche basse d'au moins 2 fois le corps et d'au moins 60 % de la bougie, une clôture dans le tiers haut, un plus bas qui touche la zone, et une clôture au-dessus du bas de la zone. Pour une vente, c'est le symétrique. |
| **Volume à la cassure** | **Non testable** avec HistData : les fichiers ne contiennent pas de volume. Voir la section 4. |
| **Triangles, canaux, obliques** | **Exclus de la version 1** (voir la section 4). Seuls les niveaux horizontaux sont utilisés. |

`N` = 3 sur H1 et sur H4. *(choix)*

## 2. Règles (achat ; la vente est le symétrique)

Toutes les heures sont en heure de Zurich.

1. **Filtre H4** : la tendance H4 est haussière. Les achats seulement.
2. **Cassure H1** : une bougie de force clôture au-dessus d'une résistance H1 valide. La zone de chasse est créée.
3. **Annulation** : la zone est abandonnée si une bougie H1 clôture sous le bas de la zone (fausse cassure),
   ou si aucun signal n'arrive dans les **24 bougies H1** qui suivent la cassure. *(choix)*
4. **Pullback et signal M5** : une pin bar haussière M5 se forme dans la zone, sur une bougie ouverte
   entre **8h00 et 11h55**.
5. **Entrée** : à l'ouverture de la bougie M5 suivante.
6. **Stop** : sous le plus bas de la pin bar, moins 2 pips.
7. **Objectif** : le plus haut atteint en H1 entre la cassure et le signal (le « dernier sommet » de l'explosion).
   Trade ignoré si l'objectif est à moins de 1 R. *(choix : ce garde-fou n'est pas dans la méthode)*
8. **Sortie forcée à 17h.** 2 trades par jour au maximum, arrêt après 2 pertes consécutives.
   Risque 1 %, levier 1:5. Une zone ne sert qu'une fois.

## 3. Critères de réussite (fixés à l'avance)

Sur 2015–2021, coût de 1,1 pip, la stratégie est retenue **seulement si toutes les conditions sont remplies** :

1. R moyen net **≥ +0,05** sur EUR/USD **et** GBP/USD.
2. Profit factor **≥ 1,10** sur chaque paire.
3. Au moins **4 années positives sur 7** sur chaque paire.
4. R moyen net encore positif à **1,5 pip** de coût.
5. Au moins **150 trades** par paire.
6. Toutes les variantes de la section 5 restent positives.

## 4. Limites connues

- **Volume** : en forex, il n'y a pas de volume centralisé. Les brokers affichent un « volume en ticks »
  (nombre de variations de prix), et HistData n'en fournit pas du tout. La règle « volume important à la cassure »
  ne peut pas être testée dans la version de base. Elle pourra l'être plus tard, sur la période où les données
  Dukascopy (qui ont un volume en ticks) sont disponibles.
- **Triangles et obliques** : leur tracé dépend beaucoup de l'œil (quelles mèches relier, combien de touches).
  Ils sont exclus pour commencer. Une cassure de triangle correspond souvent à la cassure du dernier sommet de la
  compression, qui est en partie couverte par les niveaux horizontaux.
- **Stop serré** : un stop « quelques pips sous la mèche M5 » fait souvent 4 à 10 pips. Avec un coût de
  1,1 pip, ça représente 0,1 à 0,25 R par trade. C'est le problème qui a coulé l'EMA Breakout : il faudra un
  gros avantage brut pour le compenser.

## 5. Variantes de sensibilité (fixées à l'avance)

On change un réglage à la fois :

| Réglage | Base | Variantes |
|---|---|---|
| `N` (sommets et creux) | 3 | 2 · 5 |
| Corps de la bougie de force (× ATR H1) | 0,7 | 0,5 · 1,0 |
| Largeur de la zone (× ATR H1) | 0,2 | 0,1 · 0,3 |
| Délai du pullback (bougies H1) | 24 | 12 · 48 |
| Filtre H4 | actif | désactivé |
