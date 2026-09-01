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

- **Le service du formulaire de contact.** `envoyerMessage()` garde sa
  signature, mais son corps doit poster quelque part. Par défaut : une adresse
  d'envoi lue dans `site.config.ts`, pour ne dépendre d'aucun fournisseur, et
  un lien de courriel visible en secours comme chez lacabane.
- **La suite immédiate**, mécanique et sans appel API : écrire le squelette,
  lancer `npm run verifier` dessus, vérifier qu'un site vide construit et se
  sert.
