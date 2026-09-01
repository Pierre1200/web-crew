# web-crew V2

Un crew de développement front qui produit des **sites vitrines Next.js** à
partir d'un brief client, et qui refuse de livrer ce qui ne compile pas.

### Les autres documents

| Fichier | Ce qu'il contient |
|---|---|
| [`DEMARRAGE-V2.md`](DEMARRAGE-V2.md) | les décisions prises avant d'écrire la première ligne |
| [`SQUELETTE.md`](SQUELETTE.md) | la composition du squelette front, et pourquoi |
| [`graphe/LISEZMOI.md`](graphe/LISEZMOI.md) | le détail des deux graphes |
| [`squelette/LISEZMOI.md`](squelette/LISEZMOI.md) | ce que le crew a le droit de toucher |
| [`README-V1.md`](README-V1.md) | la V1, toujours en production sur `main` |
| [`JOURNAL-IA.md`](JOURNAL-IA.md) | le journal de bord, à lire par une IA qui reprend le travail |

---

## 1. Ce que c'est

Un outil en ligne de commande. On lui donne un dossier de projet contenant un
brief en français et une configuration, il rend un site statique prêt à
déployer.

La V2 se distingue de la V1 sur trois points.

**La sortie est un projet Next.js, pas du HTML écrit par un modèle.** Le crew
part d'un squelette front déjà validé et ne produit que les variations : le
modèle de contenu, les composants, les pages, la charte, les textes.

**La validation est un compilateur, pas un jugement.** ESLint, TypeScript et
`next build` remplacent l'inspection du HTML à coups d'expressions régulières.
Un site qui ne passe pas ces trois portes n'est jamais publié.

**L'orchestration est une machine à états, pas une suite d'appels.** LangGraph
permet trois choses qu'un pipeline linéaire ne sait pas faire : reprendre un
run interrompu au nœud fautif au lieu de tout repayer, s'arrêter net à un
plafond en euros, et demander un accord humain après le cadrage, avant la
dépense principale.

## 2. Ce que ce n'est pas

**web-crew ne génère ni back-office, ni authentification, ni règles de sécurité
en base.** Ce n'est pas une limite technique, c'est un choix.

Un back-office se fait sur mesure, en français, taillé pour la personne qui va
s'en servir : ça ne se génère pas et ça n'a aucun intérêt à être générique. Et
retirer l'authentification du champ de la machine élimine la classe de bug la
plus dangereuse, celle qui passe le build en silence.

**En revanche, le front produit est prêt à recevoir une base de données** de
type Supabase, sans réécriture. C'est une propriété d'ingénierie précise,
détaillée au chapitre 6.

---

## 3. Prise en main

### Prérequis

| Outil | Version | Pourquoi |
|---|---|---|
| Python | 3.12 ou plus (3.14 ici) | le crew |
| Node et npm | 20 ou plus | la porte de build et le site |
| Playwright | facultatif | la critique visuelle uniquement |

### Installation

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Puis renseigner `ANTHROPIC_API_KEY` dans un fichier `.env` à la racine. Ce
fichier n'est jamais versionné.

Pour la critique visuelle, une fois :

```bash
.venv/bin/playwright install chromium
```

### Un premier site

```bash
mkdir -p projects/mon-client
# y déposer brief.md et config.json, et les documents du client dans data/
.venv/bin/python main.py front --project mon-client
```

La commande annonce le coût estimé par étape et demande confirmation avant le
moindre appel. Elle s'arrête ensuite après le cadrage pour montrer ce qu'elle a
compris, et attend un feu vert avant de dépenser.

---

## 4. Anatomie d'un projet

```
projects/mon-client/
  brief.md          CE QUE VEUT LE CLIENT, en français, écrit à la main
  config.json       identité, sections, mentions légales, collections
  data/             les documents fournis par le client (PDF, DOCX, ODT, images)
  site/             LE PROJET NEXT : squelette copié, puis rempli par le crew
  output/           LE SITE LIVRÉ : recopié depuis site/out/ après le build
  output_prev/      la version d'avant le dernier run, pour revenir en arrière
  temp/             plan, direction, textes, points de reprise du graphe
  logs/             un journal par agent, et les captures d'écran
```

Deux dossiers méritent une explication.

**`site/` est le projet Next complet**, avec son `node_modules` et son
`package.json`. Il s'ouvre dans un éditeur, se lance avec `npm run dev`, et se
corrige à la main si besoin. Ce n'est pas un dossier de travail interne, c'est
le projet livrable.

**`output/` reste le dossier livré**, comme en V1. C'est ce qui permet à
`diff`, `restore` et à l'audit de sécurité de fonctionner sans modification :
ils regardent `output/`, quel que soit le moteur qui l'a produit.

`projects/` est exclu du dépôt : les données clients n'y entrent jamais.

---

## 5. Le pipeline

```
préparer → squelette → ingestion → orchestration → direction
         → ⏸ FEU VERT HUMAIN
         → copywriter → charte → polices → front
         → PORTE (lint, types, build) ──échec──> réparation ──┐
              │                                              │
              └──────────────────<───────────────────────────┘
         → publier (site/out → output)
         → critique visuelle → correctifs.css ──> PORTE (⟲)
         → fin
```

| Nœud | Ce qu'il fait | Coût | Ce qu'il écrit |
|---|---|---|---|
| `préparer` | avertit si un travail manuel va être écrasé, sauvegarde `output/` | zéro | `output_prev/` |
| `squelette` | copie le squelette, installe les dépendances | zéro | `site/` |
| `ingestion` | digère `data/` : thèmes disponibles, manques | 0,10 à 0,40 € | `temp/context.json` |
| `orchestration` | lit le brief, décide des agents et du guide de style | ≈ 0,10 € | `temp/plan.json` |
| `direction` | arrête la composition : archétype, palette, rythme, signature | ≈ 0,10 € | `temp/direction.json` |
| ⏸ **feu vert** | montre le cadrage, attend un accord humain | zéro | rien |
| `copywriter` | rédige les textes à partir du contenu réel du client | 0,30 à 0,80 € | `temp/textes.json` |
| `charte` | traduit la direction en valeurs de tokens CSS | ≈ 0,10 € | `site/app/charte.css` |
| `polices` | télécharge et héberge les polices nommées par la charte | zéro | `site/public/polices/` |
| `front` | modèle de contenu, couture, composants, pages | 1,50 à 3,00 € | `site/lib/`, `site/app/`, `site/contenu/` |
| **porte** | ESLint, TypeScript, `next build` | zéro | rien |
| `réparation` | corrige à partir du diagnostic de l'outil | 0,20 à 0,60 € | les fichiers fautifs |
| `publier` | recopie le site bâti dans `output/` | zéro | `output/` |
| `critique visuelle` | photographie le rendu, le juge, écrit les correctifs | ≈ 0,15 € la passe | `site/app/correctifs.css` |

Les montants sont des ordres de grandeur. Le plafond, lui, est dur.

### La direction artistique est mise en cache

Elle est réutilisée tant qu'elle est plus récente que `brief.md` **et**
`config.json`. Retoucher le brief invalide donc la direction, ce qui évite de
dessiner l'ancien site avec les nouvelles instructions.

---

## 6. Les cinq garanties

### La porte de build

Trois outils qui ne se trompent pas sur ce qu'ils affirment, qui ne coûtent
rien, et qui désignent le fichier et la ligne. Ils s'exécutent dans cet ordre
et s'arrêtent au premier échec : corriger une erreur de type change souvent le
résultat du build, et montrer vingt erreurs dont dix sont les conséquences des
dix autres est le meilleur moyen de faire corriger les mauvaises.

**`publier` n'a qu'une seule arête entrante, et elle vient de la porte.** Un
livrable qui ne compile pas n'est pas un livrable en retard, c'est un livrable
qui n'existe pas.

### Le plafond en euros

Chaque nœud déclare ce qu'il vient de dépenser, la somme se fait par un
réducteur, et la garde est vérifiée **avant** chaque nœud payant. On ne peut
pas empêcher un nœud de dépasser à lui seul, on peut refuser d'en lancer un de
plus.

Un modèle absent de `utils/tarifs.py` est signalé, jamais compté zéro en
silence : une garde qui ignore une dépense n'est plus une garde.

### Le feu vert humain

Le graphe s'arrête après la direction artistique, pour quelques centimes
dépensés, et montre les agents prévus, l'ambiance, les couleurs et les polices.
Tout ce qui suit coûte des euros. Refuser ne coûte rien de plus.

### La reprise

L'état est écrit dans un SQLite du projet après chaque nœud. Un appel raté ne
fait plus tout repayer :

```bash
.venv/bin/python main.py front -p mon-client --reprendre
```

Un fil de reprise par run : réutiliser le même pour un nouveau run cumulerait
les dépenses des deux dans le même compteur et fausserait la garde de budget.

### Le périmètre d'écriture

Le crew écrit dans `site.config.ts`, `lib/types.ts`, `lib/data/`, `contenu/`,
`composants/`, `app/**/page.tsx` et `app/composants.css`. **Toute autre
destination est refusée avant écriture**, `next.config.ts`, `app/base.css`,
`app/charte.css` et `app/layout.tsx` en tête. Le squelette est ce qui rend le
résultat prévisible ; un modèle qui le réécrit le défait.

---

## 7. Le squelette front

Le crew ne construit pas une application depuis rien. Il part de `squelette/`,
un projet Next validé, et ne produit que les variations. Bénéfice mesurable :
la surface où la machine peut se tromper s'effondre, et comme on produit
beaucoup moins de code, la facture baisse.

Composition complète dans [`SQUELETTE.md`](SQUELETTE.md). Trois points à
connaître pour l'utiliser.

### La règle mère : aucune donnée en dur dans le balisage

Une page appelle une fonction de `lib/data/`, jamais un fichier directement.
Ces fonctions sont `async` dès le premier jour, même pour lire un fichier
local.

```ts
// AUJOURD'HUI
export async function listerRealisations(): Promise<Realisation[]> {
  const tout = await lireCollection<Realisation>("realisations");
  return tout.filter((r) => r.en_ligne);
}

// DEMAIN, avec une base : même nom, même signature, même type de retour
export async function listerRealisations(): Promise<Realisation[]> {
  const { data } = await supabase
    .from("realisations").select("*").eq("en_ligne", true);
  return data ?? [];
}
```

Brancher une base devient : réécrire le corps de trois fonctions. Le contrat
complet est dans `squelette/lib/data/LISEZMOI.md`.

### Un formulaire est une table

Si le brief demande un formulaire, il est pensé dès le premier jour comme une
table de la future base : une fonction nommée, une charge utile aux noms des
futures colonnes, des vérifications qui recopient les contraintes à venir.
L'insertion se fera depuis le navigateur avec la clé publiable, autorisée par
une règle RLS : un site statique n'a pas besoin de serveur pour écrire en base.

Le crew ne produit ni schéma SQL, ni règles RLS. `squelette/outils/graine.mjs` fait
le pont dans l'autre sens : il transforme le contenu local en `insert`, pour que
la base démarre remplie.

### Le CSS en quatre couches

```
base.css        invariant          @layer base
charte.css      les valeurs        @layer charte
composants.css  engendré           @layer composants
correctifs.css  la boucle visuelle HORS COUCHE
```

Une règle hors couche bat toutes les couches, quelle que soit leur
spécificité. C'est ce qui permet à un correctif `.hero {…}` de l'emporter sur
un `.section .hero {…}` sans un seul `!important`, et donc de rendre la boucle
de correction visuelle fiable. `composants.css` est enveloppé automatiquement à
l'écriture plutôt que confié à la mémoire du modèle.

---

## 8. Les commandes

### V2

| Commande | Ce qu'elle fait |
|---|---|
| `front -p <projet>` | le pipeline complet : squelette, génération, porte, publication |
| `front -p <projet> --visuel 2` | avec deux passes de critique visuelle |
| `front -p <projet> --plafond 5` | s'arrête net à 5 € |
| `front -p <projet> --reprendre` | reprend le dernier run là où il s'est arrêté |
| `front -p <projet> --oui` | sans le feu vert humain |
| `graphe -p <projet>` | le pipeline de la V1, orchestré par LangGraph |

### V1, toujours disponibles

`generate`, `generate-safe`, `design-only`, `validate`, `diff`, `restore`,
`seo-only`, `critique`, `pages`, `direction`, `visuel`, `securiser`, `ingest`,
`list-agents`. Voir [`README-V1.md`](README-V1.md).

Trois d'entre elles servent aussi à la V2, puisqu'elles travaillent sur
`output/` :

```bash
main.py diff -p mon-client       # ce que le dernier run a changé
main.py restore -p mon-client    # annuler le dernier run
main.py securiser -p mon-client  # audit avant livraison
```

### Vérifier un site à la main

```bash
cd projects/mon-client/site
npm run verifier   # lint, types, build : les trois doivent passer
npm run dev        # http://localhost:3000
```

---

## 9. Les coûts

Mesuré sur le premier run réel de la V1 : **3,88 €** pour un site complet. La
V2 vise le même ordre de grandeur, avec deux effets contraires : le squelette
fait produire beaucoup moins de code, mais le front Next est plus exigeant que
du HTML.

Le crew affiche le détail par nœud en fin de run :

```
   Dépense par nœud :
      orchestration        claude-sonnet-5     12 400 in /   1 800 out   0,0591 €
      front                claude-opus-5       28 900 in /  19 400 out   0,5791 €

   Total du run : 0,6382 €
```

Trois leviers, du plus efficace au moins efficace :

1. **le squelette**, qui fera plus pour le coût que n'importe quel changement
   de fournisseur de modèle ;
2. **les caches** : direction artistique, ingestion et gabarits de collection
   sont réutilisés tant que leurs sources n'ont pas changé ;
3. **le routage par nœud** : les tâches mécaniques n'ont pas besoin du modèle
   le plus capable.

Les prix sont dans `utils/tarifs.py`, à tenir à jour à cet endroit et nulle
part ailleurs.

---

## 10. Dépannage : les pièges connus

**Le site s'affiche sans sa typographie.** La charte nomme une famille que
Google ne connaît pas sous ce nom exact, et la feuille locale est vide.
Vérifier `site/public/polices/polices.css` et l'orthographe des familles dans
`site/app/charte.css`.

**Un correctif visuel ne s'applique pas.** Vérifier que `app/composants.css`
est bien dans `@layer composants`. S'il est hors couche, il se retrouve à
égalité avec les correctifs et la spécificité reprend le dessus.

**`next build` échoue sur une route.** En export statique, `sitemap.ts`,
`robots.ts` et tout `route.ts` asynchrone exigent
`export const dynamic = "force-static"`. Le message d'erreur ne dit pas dans
quel fichier ajouter la ligne.

**`npm ci` très long, ou disque plein.** Chaque projet a son propre
`node_modules`. Ne pas ruser avec un lien symbolique vers un dossier partagé :
Turbopack refuse de construire et échoue sur « Symlink node_modules is invalid,
it points out of the filesystem root ».

**Le site affiche « En cours » des mois après.** Un état a été calculé pendant
le rendu d'une page au lieu de passer par `composants/Etat.tsx`. En export
statique, tout ce qui est calculé au build est figé au jour du build.

**Une page entière est invisible mais occupe sa place.** Le témoin `data-js`
est posé et personne ne révèle les blocs. Cela n'arrive qu'en arrivant par un
lien : un rechargement répare tout, ce qui est le meilleur moyen de ne jamais
le remarquer en développement. Voir `composants/Comportements.tsx`.

**Le graphe boucle sans jamais publier.** Une clé écrite par un nœud n'est pas
déclarée dans `EtatCrew` : LangGraph la jette en silence. Un test le vérifie
mécaniquement, le lancer avant de chercher ailleurs.

**Ne jamais supprimer `.next/` pendant que `npm run dev` tourne.** Le serveur
continue de lire des fichiers qui n'existent plus et sert des 404 sur toutes
les pages. Arrêter le serveur d'abord.

---

## 11. État d'avancement

| Étape | État |
|---|---|
| 1. Extraire le squelette front | fait, `npm run verifier` passe |
| 2. LangGraph par-dessus, à sortie équivalente | fait, jamais lancé contre l'API |
| 3. MiniMax sur les nœuds mécaniques | en attente d'une clé API |
| 4. Générateur de modèle de contenu et validation humaine | partiel |

**Ce qui n'a jamais tourné contre l'API :** les deux graphes. Le câblage, les
garde-fous, la porte de build et les garanties sont vérifiés par 330 tests et
sur le squelette réel. Les prompts des trois agents front n'ont jamais été
confrontés à un modèle : le premier run réel les jugera, et il faudra une passe
de retouche derrière.

**Critère d'arrêt, décidé d'avance :** la V2 doit produire, sur un brief connu,
un front au moins équivalent à ce que la V1 a produit. Sinon on garde la V1 et
on sait pourquoi.
