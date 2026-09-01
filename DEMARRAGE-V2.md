# Démarrage V2

Ce fichier est le point d'entrée de la V2 de web-crew. Il rassemble les
décisions prises avant d'écrire la première ligne. À lire en entier avant de
proposer quoi que ce soit.

---

## Qui travaille ici

Pierre, 41 ans, en reconversion, quelques mois de Python derrière lui, un passé
en C. Il cherche une alternance. Il développe web-crew pour de vrais clients
payants : deux sites en cours, un près du déploiement.

**Règles permanentes, sans exception :**

- **Ne jamais lancer `git commit` ni `git add`.** Proposer un message de commit
  prêt à coller, c'est lui qui commite.
- **Aucun appel à l'API sans accord explicite et sans annoncer le coût estimé
  avant.**
- **Pas de tirets cadratins** dans les textes écrits. Il les repère et les
  déteste.
- **Aucun nom de client réel** dans les fichiers versionnés (code, tests,
  README). `CONTEXT.md` est ignoré par git, les vrais noms y sont permis.
- Expliquer de façon pédagogique. Il débute en Python, les analogies avec le C
  fonctionnent bien.

---

## Où on est

**Dossier :** `/Users/macbookdepierre/Documents/web-crew-v2`, branche `v2`,
worktree du dépôt principal. La V1 reste vivante sur `main` dans
`/Users/macbookdepierre/Documents/web-crew` et sert des clients en production.
Ne jamais casser `main`.

Cette branche ne fusionnera probablement jamais dans `main` : elle la
remplacera. Ce n'est pas un problème, c'est le plan.

**Ce que le worktree ne contient pas** (ignoré par git) : `.venv`, `projects/`,
`logs/`. `.env` et `CONTEXT.md` ont été copiés à la main. Pour l'environnement
Python, en sachant que les dépendances V2 vont diverger (LangGraph, SDK
compatible OpenAI) :

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

---

## Ce qu'était la V1, et ce qui en survit

La V1 est un CLI Python multi-agents qui génère des sites statiques en HTML et
CSS. Dix agents héritant de `BaseAgent`, orchestrés par `main.py`, quatorze
commandes. Elle a produit un vrai site pour un vrai client, à 3,88 euros le run.

**Ce qui est bon et doit être repris tel quel :** tout le Python déterministe
de `utils/`. Ce sont plusieurs milliers de lignes testées qui ne consomment
aucun token : `images.py`, `embeds.py`, `pages.py`, `securite.py`, `polices.py`,
`tarifs.py`, `mentions.py`, `cleaners.py`, `extractors.py`, `capture.py`,
`snapshot.py`. **C'est la vraie valeur de web-crew. Ne pas les réécrire.** Elles
deviennent des nœuds du graphe.

**Ce qui ne va pas :** le contenu est tressé dans le HTML généré. Le premier run
réel a produit seize blocs `<figure>` cassés parce que les gabarits sont des
chaînes de caractères, et il a fallu tout reprendre à la main. Score de critique
visuelle : 5 sur 10, `conforme_au_brief: false`.

---

## Le périmètre de la V2

**web-crew reste un crew de développement front, professionnel. Il ne génère ni
back-office, ni authentification, ni règles de sécurité en base.**

Raison : le back-office se fait sur mesure, en français, taillé pour la personne
qui va s'en servir. Ça ne se génère pas et ça n'a aucun intérêt à être
générique. Et retirer l'authentification du champ de la machine élimine la
classe de bug la plus dangereuse, celle qui passe le build en silence.

**Mais le front produit doit être prêt à recevoir une base de données** plus
tard, Supabase ou autre, sans réécriture. C'est une propriété d'ingénierie
précise, détaillée plus bas.

---

## La stack

**Next.js en export statique, React, TypeScript.** Décidé, ne pas rouvrir le
débat.

La raison n'est pas technique mais stratégique : le jour où un client veut son
back-office, on est déjà dans Next. On retire `output: 'export'`, on réécrit les
fonctions de lecture, on ajoute `admin/`. Le front statique et l'application
avec back-office ne sont pas deux produits, c'est **le même produit à deux
étapes**. Le passage de l'un à l'autre est une facturation, pas une réécriture.

**Le style :** CSS vanilla avec des tokens de design, plus des CSS Modules.
**Pas de Tailwind, pas de CSS-in-JS.** Ce n'est pas un goût : la boucle de
correction visuelle automatique ajoute des règles hors couche en fin de feuille,
ce qui n'a de sens que s'il existe une feuille. Avec Tailwind il faudrait éditer
des chaînes de classes dans le JSX, opération bien moins fiable pour une
machine.

---

## La référence : un exemple réel existe déjà

`/Users/macbookdepierre/Documents/adap12-lacabane/lacabane-app`

C'est une application Next.js 16 + React 19 + Supabase avec back-office, écrite
à la main par Pierre pour un vrai client, en quatre jours. Elle contient les
réponses à la plupart des questions d'architecture. **La lire avant de proposer
une structure.** En particulier :

- `lib/data/` : la lecture pour le site public, la couture qui rend le
  branchement possible
- `lib/types.ts` : le contrat entre la base et le code, avec des commentaires
  qui expliquent chaque décision
- `supabase/migrations/*.sql` : la forme régulière d'une table et de ses règles
- `README.md` à la racine et dans l'app : les décisions et les pièges

C'est **l'étalon**. La V2 est réussie quand elle sait produire un front de cette
qualité à partir d'un brief.

---

## Les règles de branchabilité

C'est le cœur technique de la V2. Le front généré doit respecter ceci.

**Règle mère : aucune donnée en dur dans le balisage.** Toute lecture passe par
`lib/data/`. Une page appelle `listerExpositions()`, jamais un fichier
directement.

```ts
// AUJOURD'HUI : lit un fichier de contenu local
export async function listerExpositions(): Promise<Exposition[]> {
  return contenu.filter(e => e.en_ligne);
}

// DEMAIN : même nom, même signature, même type de retour
export async function listerExpositions(): Promise<Exposition[]> {
  const { data } = await supabase
    .from("expositions").select("*").eq("en_ligne", true);
  return data ?? [];
}
```

Brancher une base devient : réécrire le corps de trois fonctions. Le reste du
site ne s'en aperçoit pas.

Les six règles qui font tenir la couture :

| Règle | Pourquoi |
|---|---|
| `async` dès le premier jour, même pour lire un fichier local | La plus importante et la moins évidente. Une fonction synchrone rend tous ses appelants synchrones ; la rendre asynchrone plus tard veut dire toucher chaque composant. Coût aujourd'hui : zéro. |
| Les types TypeScript sont le contrat | Une `Exposition` a la même forme qu'elle vienne d'un fichier ou de Postgres. |
| Forme de table dès l'origine : `id`, `slug` unique, `en_ligne`, `cree_le`, `modifie_le`, dates en ISO | Si le contenu local respecte les conventions Postgres, la migration s'écrit toute seule. |
| Champ absent = `null`, jamais `undefined` ni chaîne vide | PostgreSQL met `NULL`. Une divergence ici est un refactor plus tard. |
| Aucun état dérivé stocké | « en cours », « terminée » se calculent à l'affichage depuis les dates. La base ne stocke que des faits. |
| Aucun `fetch` dans un composant | Les données descendent de la page en props, sinon la couture fuit partout. |

Deux coutures de plus, du même esprit : **les images** passent par un champ de
données, jamais par un chemin écrit dans un composant, sinon un stockage
distant impose de tout reprendre. **Le formulaire** appelle une fonction nommée
`envoyerMessage(donnees)`, même si aujourd'hui elle ne fait que poster vers un
service tiers.

Enfin : **le fichier de contenu produit par le crew doit pouvoir servir de seed
à la base.** Un petit script le lit et crache les `INSERT`. C'est la continuité
entre les deux étapes du produit.

---

## Le squelette

La V2 ne génère pas une application depuis rien. Elle part d'un **squelette
front validé** et ne produit que les variations.

Le squelette contient : la configuration Next, le layout racine, `error.tsx`,
`not-found.tsx`, `sitemap.ts`, `robots.ts`, les en-têtes de sécurité, le fichier
de tokens CSS, et surtout **la couture `lib/data/` et `lib/types.ts` livrée
vide**. Le crew la remplit, il ne l'invente pas.

Le crew génère : le modèle de contenu, les composants et pages, les styles, les
textes, le traitement des images.

Bénéfice mesurable : la surface où la machine peut se tromper s'effondre, et
comme on produit beaucoup moins de code, la facture baisse. **Le squelette fera
plus pour le coût que n'importe quel changement de fournisseur de modèle.**

---

## L'orchestration : LangGraph

LangGraph, pas LangChain. Le besoin n'est pas une chaîne mais une machine à
états avec des boucles.

**Point non négociable : les nœuds appellent les SDK bruts.** LangGraph sert
d'orchestrateur, on ne passe pas par ses abstractions de modèle. C'est ce qui
permet de garder `effort`, le thinking adaptatif, et le comptage de coût exact.

Ce qu'on en attend :

- **Checkpointer** : le premier run réel a raté deux appels sur douze. Avec un
  état persisté, on reprend au nœud fautif au lieu de tout repayer.
- **Cycles avec garde** : générer, bâtir, critiquer, corriger, rebâtir, avec un
  compteur d'itérations et un plafond en euros.
- **`interrupt()`** : arrêter le graphe après la direction artistique et le
  modèle de contenu, faire valider par Pierre, puis dépenser. Aujourd'hui il
  paie douze appels avant de découvrir que ça ne colle pas au brief.
- **Réducteurs** : `Annotated[float, add]` sur le coût, chaque nœud renvoie ce
  qu'il vient de dépenser, le total sert de garde-fou. `utils/tarifs.py` sert
  telle quelle.

La forme visée :

```
brief → ingestion → direction artistique → modèle de contenu
      → ⏸ VALIDATION HUMAINE
      → génération pages et composants (parallèle par collection)
      → npm run lint && tsc --noEmit && next build ──échec──> réparation ──┐
           │                                                              │
           └──────────────────────────<───────────────────────────────────┘
      → capture Playwright → critique visuelle
           └── boucle correctifs CSS, plafond en euros et en passes
      → sécurité → livraison
```

La porte de build est déterministe et gratuite. En V1 on n'avait que le
jugement d'un modèle sur une page ; là on a un compilateur. C'est une différence
de nature, pas de degré.

---

## Les modèles

**Le nœud qui écrit du Next et du React est le plus dur de la chaîne. Ce n'est
pas là qu'on économise.**

Preuve concrète, à vérifier dans `lacabane-app` : le fichier s'appelle
`proxy.ts`. Dans les versions précédentes de Next il s'appelait
`middleware.ts`. Un modèle entraîné sur l'ancienne version écrit
`middleware.ts` ; le build passe, TypeScript est content, ESLint aussi, et le
fichier ne s'exécute jamais. Panne silencieuse qu'aucune porte automatique
n'attrape. Next écrit d'ailleurs lui-même dans `CLAUDE.md` que ce n'est pas le
Next que le modèle croit connaître, et demande de lire la doc locale dans
`node_modules/next/dist/docs/` avant d'écrire.

**Conséquence pour la V2 :** le nœud de génération doit consulter la
documentation locale plutôt que sa mémoire, et la version de Next doit être
épinglée.

**MiniMax** est à tester, mais sur les nœuds mécaniques uniquement au départ :
structuration des textes extraits, slugs, textes alternatifs des images,
méta-descriptions, classement des photos. Aucun risque de sécurité, volume
important, gain mesurable.

L'API MiniMax est compatible OpenAI : on utilise le SDK `openai` avec un autre
`base_url`. **À vérifier dans leur documentation avant de s'engager :** le nom
exact des modèles, l'URL de l'endpoint international, et surtout l'existence
d'un mode JSON strict. Ce dernier point est décisif, toute la chaîne dépend de
JSON parsable et c'est ce qui a lâché deux fois sur douze au premier run.

Routage par nœud, dans une table :

```python
MODELES = {
    "structurer": ("minimax", "..."),      # mécanique, bon marché
    "alt_images": ("minimax", "..."),
    "direction":  ("anthropic", "claude-opus-5"),   # goût
    "generer":    ("anthropic", "claude-opus-5"),   # le produit
    "critique":   ("anthropic", "claude-opus-5"),   # les yeux
}
```

---

## L'ordre de migration, et pourquoi il compte

Trois changements simultanés : orchestrateur, stack de sortie, fournisseur de
modèle. Si le résultat est moins bon, impossible de savoir lequel est en cause.
C'est le piège qui coûte des semaines.

1. **Extraire le squelette front.** Travail manuel, pas de génération. On
   sépare ce qui est générique de ce qui est propre à un client, en s'inspirant
   de `lacabane-app`.
2. **LangGraph par-dessus, à sortie identique.** Le graphe doit d'abord
   reproduire ce que la V1 sait faire, mêmes prompts, mêmes modèles. Si la
   sortie diffère, c'est un bug de migration, pas un choix.
3. **MiniMax sur les nœuds mécaniques**, en parallèle de l'étape 2. Risque nul,
   mesure immédiate.
4. **Le générateur de modèle de contenu**, avec la validation humaine. C'est le
   morceau qui transforme web-crew en produit.

**Critère d'arrêt, à écrire maintenant et pas après :** la V2 doit produire, sur
un brief connu, un front au moins équivalent à ce que la V1 a produit. Sinon on
garde la V1 et on sait pourquoi.

---

## Ce qu'il ne faut pas faire

- Ne pas réécrire `utils/`. Ces modules sont testés et gratuits.
- Ne pas générer d'authentification, de règles RLS ni de back-office.
- Ne pas construire de multi-locataire. Un dépôt, un déploiement par client.
- Ne pas passer par les abstractions de modèle de LangChain.
- Ne pas lancer d'appel API sans accord et sans annoncer le coût.
- Ne pas commiter.

---

## Première tâche proposée

Lire `lacabane-app` en entier, puis proposer la composition du squelette front :
ce qu'on garde tel quel, ce qu'on paramètre, ce qu'on laisse au crew. Zéro
token, zéro appel API, et c'est le fondement de tout le reste.
