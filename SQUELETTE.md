# Le squelette front

Composition du squelette front de la V2 : ce qu'on garde tel quel, ce qu'on
paramètre, ce qu'on laisse au crew.

Écrit après lecture de `DEMARRAGE-V2.md`, de `lacabane-app` en entier, et de la
documentation locale de Next dans `node_modules/next/dist/docs/`.

---

## Un constat préalable qui change une partie du plan

`lacabane-app` est une application **avec serveur**. La V2 vise un **export
statique**. La documentation locale de Next 16
(`01-app/02-guides/static-exports.md`) liste ce que `output: 'export'` retire,
et quatre de ces choses sont utilisées partout dans l'étalon.

| Ce que fait lacabane | En export statique | Ce qui le remplace |
|---|---|---|
| `headers()` dans `next.config.ts` | inopérant | fichiers d'en-têtes de l'hébergeur, engendrés par `utils/securite.py` |
| `export const revalidate = 600` | inopérant | un composant client, voir plus bas |
| Server Actions (`envoyerMessage`) | inopérant | un `fetch` vers un service tiers, même signature |
| `next/image` avec l'optimiseur | inopérant | `images: { unoptimized: true }`, le travail est fait par `utils/images.py` |
| `proxy.ts` | inopérant | rien, il n'y a plus de session à renouveler |

Le piège sérieux est `revalidate`. Chez lacabane, `lib/dates.ts` calcule
« En cours », « Bientôt », « Terminée » à partir des dates, et
`revalidate = 600` garantit que le calcul est refait toutes les dix minutes. En
statique, **le calcul est figé au moment du build**. Un site construit en
juillet affichera « En cours » en septembre. ESLint passe, TypeScript passe,
`next build` passe, et la critique visuelle ne voit rien puisque la capture est
faite le jour du build.

C'est le même mode de panne que `proxy.ts` contre `middleware.ts` : silencieux,
et invisible pour qui développe.

**La parade, dans le squelette :** `etat()` reste en `lib/`, mais son résultat
est rendu par un petit composant client qui le recalcule à l'affichage. La date
de construction devient une donnée, pas une vérité.

---

## La composition

Trois régimes. En C, ce serait la bibliothèque compilée une fois pour toutes,
le fichier de configuration, et le code écrit pour chaque programme.

### A. Invariant, copié tel quel, jamais touché par le crew

```
package.json            versions ÉPINGLÉES (next 16.3.3, react 19.2.8)
                        + le script "verifier" : lint && typecheck && build
tsconfig.json           strict, paths @/*
eslint.config.mjs
next.config.ts          output:'export', images unoptimized
.gitignore

app/layout.tsx          <html lang="fr">, favicon, metadataBase
app/error.tsx           l'écran d'incident, sans error.message
app/not-found.tsx       la 404 AVEC l'enveloppe (hors groupe de routes)
app/robots.ts
app/sitemap.ts          lit lib/data, jamais une liste écrite à la main
app/flux.xml/route.ts   avec dynamic = 'force-static'

lib/site.ts             ADRESSE_DU_SITE, un seul endroit dans tout le dépôt
lib/dates.ts            enFrançais, periode, etat, quand
lib/contenu.ts          le chargeur des fichiers de contenu, async
lib/types.ts            LIVRÉ VIDE, avec l'en-tête qui explique le contrat
lib/data/               LIVRÉ VIDE
lib/envoyer-message.ts  signature figée, corps paramétré

composants/Trait.tsx, EnteteSection.tsx
composants/Cadre.tsx           le cadre en pointillés
composants/Etat.tsx            "use client", recalcule l'état à l'affichage
composants/Comportements.tsx   révélations au défilement

app/base.css            reset, focus-visible, .sr-only, .conteneur,
                        impression, prefers-reduced-motion
app/correctifs.css      VIDE, importé en dernier
public/polices/         engendré par utils/polices.py
```

Trois remarques sur cette colonne.

**`Cadre.tsx` n'existe pas chez lacabane.** Le cadre en pointillés y est copié
quatre fois à l'identique : `ligne-exposition.tsx`,
`expositions/[slug]/page.tsx`, `blog/page.tsx` et `page.tsx`. Écrit à la main,
c'est une négligence bénigne. Confié à un modèle, c'est quatre occasions de
diverger.

**`Comportements.tsx` est repris avec son commentaire.** Le bug qu'il documente
(le composant reste monté d'une page à l'autre, donc un tableau de dépendances
vide laisse le contenu invisible à vie) est précisément ce qu'un modèle
réécrirait de travers, et le filet de 2,5 secondes est ce qui empêche la panne
d'être définitive.

**`lib/slug.ts` ne fait PAS partie du squelette**, et c'est délibéré.
`utils/cleaners.slugifier` en Python et `lib/slug.ts` en TypeScript
implémenteraient la même règle dans deux langues. Deux implémentations d'une
même règle divergent toujours. Le slug est calculé une fois, par Python, et
écrit dans le fichier de contenu. Le TypeScript le lit.

### B. Paramétré : des valeurs, pas du code

```
site.config.ts    nom, adresse du site, courriel, menu, titre et description,
                  image de partage, mentions légales, collections déclarées
app/charte.css    LES VALEURS DES TOKENS uniquement : couleurs, polices,
                  échelle typographique, rythme. La structure est figée, le
                  crew ne remplit que le côté droit des « : ».
```

Cette colonne est la traduction directe de ce qui existe déjà en V1 :
`utils/mentions.donnees_mentions(config)` et
`utils/pages.collections_declarees(config)` lisent déjà une configuration de
cette forme.

Les mentions légales suivent la trouvaille de lacabane, qui vaut d'être reprise
telle quelle : **les mentions manquantes sont affichées en évidence sur la
page**, pas laissées en commentaire dans le code.
`utils/mentions.champs_manquants()` sait déjà les repérer.

### C. Généré par le crew

Le modèle de contenu (`lib/types.ts` et les fichiers de contenu), la couture
(`lib/data/*.ts`), un composant par collection sur le patron de
`LigneExposition`, les pages, `app/composants.css`, les textes, le traitement
des images.

C'est tout. La V1 engendrait en plus la sécurité, les polices, le plan du site,
le flux et les gabarits. La surface d'erreur tombe de beaucoup.

---

## Ce que devient `utils/`

`DEMARRAGE-V2.md` dit de ne pas réécrire `utils/`. D'accord sur le fond, avec
une nuance sur un fichier.

**Survivent sans y toucher :** `extractors.py`, `cleaners.py`, `images.py`,
`polices.py`, `tarifs.py`, `capture.py`, `snapshot.py`, `embeds.py` (la partie
normalisation), `mentions.py` (la partie données).

**Reprend du service : `securite.py`.** On pouvait croire que `construire_csp`
et `rendre_headers` mouraient avec `next.config.ts`. C'est l'inverse : en export
statique `headers()` ne s'applique pas, donc les en-têtes doivent redevenir des
fichiers d'hébergeur, et ces fonctions redeviennent le seul moyen de les
produire. `auditer`, `chercher_secrets` et `durcir_liens_externes` tournent sur
`out/` après le build, puisque l'export produit du vrai HTML.

**Se coupe en deux : `pages.py`.**

| Moitié | Sort |
|---|---|
| `lire_contenu`, `decouper_corps`, `temps_de_lecture`, `date_en_francais`, `lire_collection`, `collections_declarees` | devient la matière du nœud « modèle de contenu » |
| `remplir`, `rendre_corps`, `rendre_couverture`, `rendre_collection`, `marqueur_html_dans_attribut` | sort du chemin |

La seconde moitié est **exactement le mécanisme qui a produit les seize
`<figure>` cassés** : des chaînes de caractères dans lesquelles on injecte du
HTML. JSX la remplace, et TypeScript rend l'erreur impossible plutôt que
détectable. `marqueur_html_dans_attribut` était un pansement sur une plaie que
la V2 supprime.

Ce n'est pas une réécriture, c'est une amputation nette : environ 150 lignes
sur 367 sortent du chemin, le reste ne bouge pas.

---

## Le CSS en quatre couches

`app/site.css` fait 1149 lignes chez lacabane, et mélange ce qui est vrai pour
tout site (le reset, `:focus-visible`, `.conteneur`, l'impression) avec ce qui
est propre à La Cabane (la crème, les halos, le grain de papier).

Pour que la boucle de correction visuelle ait un endroit défini où écrire,
quatre feuilles, importées dans cet ordre :

1. `base.css` invariant
2. `charte.css` les valeurs des tokens, paramétré
3. `composants.css` généré
4. `correctifs.css` **vide dans le squelette**, où la boucle ajoute ses règles

La boucle n'édite jamais les trois premières. Elle ajoute à la fin de la
quatrième. Une passe de correction devient relisible, et annulable en
supprimant un fichier.

**Réserve sur les CSS Modules** annoncés dans `DEMARRAGE-V2.md` : ils
fonctionnent contre la boucle, qui a besoin d'un endroit unique et prévisible
où écrire. Proposition : des feuilles globales et des noms de classes en BEM,
comme lacabane, et garder les CSS Modules en réserve si un composant généré
devient conflictuel. Ce n'est pas une remise en cause de la stack, seulement du
découpage des fichiers.

---

## Ce qui ne rentre pas dans le squelette

`app/admin/`, `supabase/`, `lib/supabase/`, `lib/actions/` (sauf le contact),
`proxy.ts`, et `app/api/sante/route.ts`.

Ce dernier existe pour empêcher Supabase de mettre le projet en pause au bout
de sept jours sans activité. Il n'a aucun sens sans base, mais son raisonnement
mérite d'être conservé : ne pas surveiller la page d'accueil, qui est servie
depuis le cache et ne toucherait donc pas la base. Il rejoindra le squelette à
l'étape « avec back-office ».

---

## Reste à trancher

- **La destination provisoire du formulaire.** `envoyerMessage()` garde sa
  signature ; il lui faut une adresse d'envoi tant qu'il n'y a pas de base.
  `null` par défaut, ce qui désactive le formulaire et ne laisse que le lien
  de courriel.
- **La suite immédiate**, mécanique et sans appel API : écrire le squelette,
  lancer `npm run verifier` dessus, vérifier qu'un site vide construit et se
  sert.

---

## Ce que l'écriture a appris

Le squelette est écrit dans `squelette/`. `npm run verifier` passe : ESLint,
TypeScript, puis la construction. Sept adresses sont produites, et le site vide
se sert.

Trois choses ne se devinaient pas depuis la lecture seule.

**`export const dynamic = "force-static"` est obligatoire sur `sitemap.ts` et
`robots.ts`.** Dès qu'une de ces routes est `async`, Next la classe comme
dynamique et refuse de construire. Le message d'erreur ne dit pas dans quel
fichier ajouter la ligne. C'est deux minutes quand on sait, une demi-heure
sinon : le squelette les porte déjà.

**On ne peut plus écrire `useEffect(() => setState(...))`.** La règle
`react-hooks/set-state-in-effect` refuse désormais un état posé directement
dans un effet, rendus en cascade. `composants/Etat.tsx` passe donc par
`useSyncExternalStore`, qui est la façon prévue de dire « cette valeur vient de
l'extérieur de React ». Le résultat est plus court et plus juste.

**Une page ne peut pas contenir de dl vide.** Sur les mentions légales, un
titre suivi d'une liste vide ressemble à une panne. Ce qui manque s'écrit en
toutes lettres.

Deux ajouts par rapport à la composition prévue :

- `outils/graine.mjs` : lit une collection de `contenu/` et crache les `insert`
  correspondants. C'est la continuité entre les deux étapes du produit, promise
  dans `DEMARRAGE-V2.md`, et elle tient en soixante lignes.
- `app/mentions-legales/page.tsx` : la page existe dans le squelette, puisque
  le pied de page y renvoie et qu'un lien mort en bas de site est une faute.

---

## Un formulaire est une table

`lib/data/` n'est pas seulement la lecture. Si le brief demande un formulaire,
il est pensé dès le premier jour comme une TABLE de la future base, et non
comme un envoi de courriel déguisé. C'est le même travail de couture, du côté
écriture, et il obéit aux mêmes règles.

Ce que ça veut dire concrètement, dans `lib/data/messages.ts` :

- une fonction nommée, `envoyerMessage(message)`, appelée par le formulaire qui
  ne sait rien de ce qu'il y a derrière ;
- une charge utile typée aux noms des futures colonnes, en minuscules avec des
  tirets bas ;
- ce qu'on n'envoie PAS : ni `id` (la base le fabrique), ni `cree_le` (elle
  l'horodate), ni `lu` (c'est l'affaire d'un back-office qui n'existe pas) ;
- des vérifications qui recopient les contraintes que portera la table, dont la
  liste fermée des motifs, qui deviendra une contrainte `check` ;
- une destination provisoire dans `site.config.ts`, `null` par défaut. Sans
  destination, le formulaire dit qu'il n'a pas pu envoyer et affiche le
  courriel direct. Il ne fait jamais semblant.

Le jour du branchement, seul le corps change :

```ts
const { error } = await supabase.from("messages").insert(message);
return error ? { etat: "echec" } : { etat: "envoye" };
```

**L'insertion se fait depuis le navigateur**, avec la clé publiable, autorisée
par une règle RLS « chacun peut déposer un message ». Un site statique n'a donc
pas besoin de serveur pour écrire en base : c'est ce qui rend le branchement
possible sans changer d'hébergement.

Le crew ne produit ni schéma SQL, ni règles RLS, ni back-office. La forme est
prête, le reste s'écrit à la main le jour venu.

Le contrat complet, lisible par le nœud de génération, est dans
`squelette/lib/data/LISEZMOI.md`.
