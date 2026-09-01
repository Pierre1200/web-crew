# Le graphe

Étape 2 de la migration V2 : **LangGraph par-dessus la V1, à sortie
équivalente**. Le graphe reproduit ce que `webcrew generate-safe` sait déjà
faire, sans toucher à un seul prompt ni à un seul modèle.

```bash
webcrew graphe -p mon-projet                 # feu vert humain après le cadrage
webcrew graphe -p mon-projet --visuel 2      # avec deux passes de critique visuelle
webcrew graphe -p mon-projet --plafond 3     # s'arrête net à 3 €
webcrew graphe -p mon-projet --reprendre     # reprend le dernier run où il s'est arrêté
webcrew graphe -p mon-projet --oui           # sans le feu vert, pour comparer à la V1
```

Le coût estimé est annoncé avant chaque run, et rien ne part sans confirmation.

## Le parcours

```
préparer → ingestion → orchestration → direction
         → ⏸ FEU VERT (humain)
         → copywriter → designer → seo → collections → mentions
         → contrôle ──erreurs réparables──> réparation ──┐
              │                                          │
              └──────────────────<───────────────────────┘
         → critique visuelle ⟲ (tant qu'il reste des passes ET des correctifs)
         → fin
```

Deux gardes traversent tout : le **plafond en euros**, vérifié avant chaque
nœud payant, et un **compteur par boucle**. Une boucle sans compteur finit
toujours par tourner sur un défaut que personne ne sait réparer.

## Ce que le graphe apporte, et que le pipeline linéaire ne savait pas faire

**La reprise.** L'état est écrit dans `projects/<projet>/temp/graphe.sqlite`
après chaque nœud. Le premier run réel a raté deux appels sur douze : il
fallait tout repayer. Maintenant, `--reprendre` repart du nœud fautif.

**Le plafond.** `Annotated[float, add]` sur le coût : chaque nœud renvoie ce
qu'il vient de dépenser, la somme se fait toute seule, et la garde a un total
fiable à comparer. Personne n'a à penser à cumuler, donc personne ne peut
l'oublier.

**Le feu vert.** `interrupt()` arrête le graphe après la direction artistique,
pour quelques centimes dépensés. En V1, douze appels partaient avant qu'on
découvre que le cadrage ne collait pas au brief.

**Le coût par étape.** La V1 donne un total de run. Le graphe donne une ligne
par nœud, avec les jetons et les euros, et signale les modèles absents de
`utils/tarifs.py` au lieu de les compter zéro en silence.

## Ce que « sortie équivalente » veut dire, exactement

**Pas « octet pour octet ».** Deux appels au même modèle avec le même prompt ne
rendent pas le même texte : comparer les fichiers ne prouverait rien, et un
écart ne signalerait aucun bug.

Ce qui est garanti **par construction** : aucun prompt, aucun modèle, aucun
réglage d'`effort` n'a changé, puisque les nœuds appellent les agents de la V1
sans les réécrire. `graphe/noeuds.py` ne contient que de l'enveloppe.

Ce qui se vérifie **en comparant deux runs** sur le même brief :

| À comparer | Attendu |
|---|---|
| les fichiers produits dans `output/` | les mêmes noms, aux mêmes endroits |
| le verdict de `webcrew validate` | au moins aussi bon |
| le coût total | le même ordre de grandeur |
| les agents appelés | les mêmes, dans le même ordre |

```bash
webcrew generate-safe -p mon-projet   # la référence
webcrew diff -p mon-projet            # ce que le run a changé
webcrew graphe -p mon-projet --oui    # le graphe, sans le feu vert
webcrew diff -p mon-projet
```

## Les choix à connaître avant de lire le code

**La topologie est figée, et c'est fidèle.** La V1 trie les agents par
`priorite`, mais le prompt de l'orchestrateur FIXE ces priorités : copywriter 1,
designer 2, seo 3. Le plan ne décide donc que de l'inclusion, jamais de
l'ordre. Le nœud d'orchestration vérifie cette hypothèse à chaque run et
prévient si elle cesse d'être vraie.

**Chaque nœud fabrique sa propre instance d'agent.** Les agents de la V1 sont
sans mémoire d'un appel à l'autre : tout ce dont ils ont besoin est relu sur
disque. C'est ce qui rend la reprise possible, un objet Python vivant ne
survivant pas à un checkpoint.

**Un fil de reprise par run.** LangGraph range l'état sous un identifiant de
fil. Réutiliser le même pour un nouveau run cumulerait les dépenses des deux
dans le même compteur, et la garde de budget deviendrait fausse. D'où un fil
horodaté par run, mémorisé dans `temp/graphe_fil.txt`.

**Les mentions légales sont écrites même au plafond.** Elles ne coûtent rien,
et un site sans mentions légales est en infraction, pas « incomplet ».

## Ce qui n'est pas encore là

Le feu vert s'arrête après la direction artistique. `DEMARRAGE-V2.md` le veut
aussi après **le modèle de contenu**, qui n'existe pas encore : c'est l'étape 4.

Le graphe produit toujours le HTML de la V1. Le brancher sur le squelette Next
et la porte `npm run verifier` est le travail qui suit, une fois l'équivalence
constatée.
