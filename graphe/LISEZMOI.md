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

---

# Le graphe front : le crew branché sur le squelette Next

`graphe/front.py`, commande `webcrew front`. Même colonne vertébrale, mais la
sortie n'est plus du HTML écrit par un modèle : c'est un projet Next bâti par
un compilateur.

```bash
webcrew front -p mon-projet              # feu vert humain après le cadrage
webcrew front -p mon-projet --visuel 2   # avec deux passes de critique visuelle
webcrew front -p mon-projet --reprendre  # reprend le dernier run
```

```
préparer → squelette → ingestion → orchestration → direction
         → ⏸ FEU VERT
         → copywriter → charte → front
         → PORTE (lint, types, build) ──échec──> réparation ──┐
              │                                              │
              └──────────────────<───────────────────────────┘
         → publier (site/out → output)
         → critique visuelle → correctifs.css ──> PORTE (⟲)
         → fin
```

## La règle qui justifie l'étape entière

**On ne publie jamais un site qui ne passe pas la porte.** Un livrable qui ne
compile pas n'est pas un livrable en retard, c'est un livrable qui n'existe
pas. `publier` n'a qu'une seule arête entrante, et elle vient de `porte` : un
test le vérifie, parce que le jour où une seconde apparaîtrait, tout le reste
ne servirait plus à rien.

## Ce que la porte change

| | V1 | V2 |
|---|---|---|
| qui juge | un modèle, sur une page | ESLint, TypeScript, `next build` |
| coût | des jetons | zéro |
| précision | « il manque peut-être une section » | fichier, ligne, code d'erreur |
| réparation | aiguillage sur un type déduit | le diagnostic de l'outil, et le fichier fautif |

Les trois étapes s'arrêtent à la première qui échoue : corriger une erreur de
type change souvent le résultat du build, et montrer vingt erreurs dont dix
sont les conséquences des dix autres est le meilleur moyen de faire corriger
les mauvaises.

## Les trois agents front

**`CharteAgent` ne produit pas de CSS, il produit des valeurs.** Un JSON
`{token: valeur}`, que Python pose dans `app/charte.css`. Le modèle ne peut pas
casser une feuille qu'il n'écrit pas, et une valeur contenant `;`, `}` ou
`url(` est refusée avant d'être posée.

**`FrontAgent` écrit le modèle de contenu, la couture, les composants et les
pages en un seul appel.** Ces fichiers se répondent les uns aux autres : les
produire en trois appels, c'est produire trois versions d'un même contrat.

**`ReparateurAgent` reçoit le diagnostic de l'outil et le fichier fautif.** Il
lui est explicitement interdit de faire passer la porte en supprimant l'appel,
en désactivant une règle ou en mettant `any`.

## Deux décisions qui tiennent tout

**On ne transporte jamais du code dans du JSON.** Les fichiers voyagent entre
des marqueurs de ligne :

```
=== FICHIER: lib/types.ts ===
export type Realisation = { slug: string };
=== FIN ===
```

Un fichier TSX entier échappé dans une chaîne JSON, c'est exactement ce qui a
lâché deux fois sur douze au premier run réel. Ici il n'y a rien à échapper, et
un fichier sans marqueur de fin est ignoré : une réponse coupée ne produit
jamais un fichier à moitié écrit.

**Le squelette est protégé par une liste blanche.** Le crew écrit dans
`site.config.ts`, `lib/types.ts`, `lib/data/`, `contenu/`, `composants/`,
`app/**/page.tsx` et `app/composants.css`. Toute autre destination est refusée
avant écriture, `next.config.ts` et `app/base.css` en tête. Le squelette est ce
qui rend le résultat prévisible ; un modèle qui le réécrit le défait.

## La documentation locale de Next, injectée dans le prompt

`utils/docs_next.py` lit `node_modules/next/dist/docs/` du projet et en tire
deux choses qu'un modèle ne peut pas deviner : la table des noms de fichiers
réservés par la version installée, et la liste de ce que `output: 'export'`
interdit.

C'est la parade au piège de `DEMARRAGE-V2.md` : Next 16 a renommé
`middleware.ts` en `proxy.ts`. Un modèle entraîné sur la version d'avant écrit
`middleware.ts`, le build passe, TypeScript est content, et le fichier ne
s'exécute jamais. Aucune porte automatique n'attrape ça. La documentation
installée, elle, dit noir sur blanc « deprecated, renamed to proxy.js ».

Coût : environ 650 jetons par appel, et zéro pour l'extraction.

## Le sort de `output/`

Le site bâti (`site/out/`) est recopié dans `output/`, qui reste le dossier
LIVRÉ. `webcrew diff`, `webcrew restore` et l'audit de sécurité continuent donc
de fonctionner sans être modifiés : ils regardent `output/`, et `output/`
contient toujours le site livrable, quel que soit le moteur qui l'a produit.
La critique visuelle aussi : elle photographie `output/index.html`, qui existe.

## Ce qui reste à faire

Le graphe front n'a **jamais tourné contre l'API**. Ce qui est vérifié est le
câblage, les garde-fous et la porte, avec des doublures et sur le squelette
réel. Les prompts des trois agents front n'ont jamais été confrontés à un
modèle : c'est le premier run réel qui les jugera, et il faudra une passe de
retouche après.

Le feu vert s'arrête après la direction artistique. `DEMARRAGE-V2.md` le veut
aussi après le modèle de contenu, qui est produit par `FrontAgent` en même
temps que les pages. Les séparer en deux nœuds, avec un second arrêt entre les
deux, est le prolongement naturel une fois le premier run passé.
