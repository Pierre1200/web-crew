# La couture

Ce dossier est le seul endroit du site qui sait d'où viennent les données.
Une page appelle `listerRealisations()`, jamais un fichier. Le jour où une base
Supabase remplace les fichiers, on réécrit le corps de trois fonctions et le
reste du site ne s'en aperçoit pas.

Livré vide, sauf `plan.ts`. Le crew le remplit à partir du brief.

## Lire

```ts
// AUJOURD'HUI : lit les fichiers de contenu locaux
export async function listerRealisations(): Promise<Realisation[]> {
  const tout = await lireCollection<Realisation>("realisations");
  return tout.filter((r) => r.en_ligne);
}

// DEMAIN : même nom, même signature, même type de retour
export async function listerRealisations(): Promise<Realisation[]> {
  const { data } = await supabase
    .from("realisations").select("*").eq("en_ligne", true);
  return data ?? [];
}
```

## Écrire

Un formulaire demandé dans le brief est une table, pas un envoi de courriel.
Voir `messages.ts` : une fonction nommée, une charge utile typée aux noms des
futures colonnes, un corps remplaçable.

L'insertion se fera depuis le navigateur, avec la clé publiable, autorisée par
une règle RLS. Un site statique n'a donc pas besoin de serveur pour écrire en
base.

## Les six règles

| Règle | Pourquoi |
|---|---|
| `async` dès le premier jour, même pour lire un fichier local | La plus importante et la moins évidente. Une fonction synchrone rend synchrones tous ses appelants ; la rendre asynchrone plus tard oblige à toucher chaque composant. Coût aujourd'hui : zéro. |
| Les types de `lib/types.ts` sont le contrat | Une `Realisation` a la même forme qu'elle vienne d'un fichier ou de Postgres. |
| Forme de table dès l'origine : `slug` unique, `en_ligne`, `cree_le`, `modifie_le`, dates en ISO | Si le contenu local respecte les conventions Postgres, la migration s'écrit toute seule. L'`id` est laissé à la base. |
| Champ absent = `null`, jamais `undefined` ni chaîne vide | PostgreSQL met `NULL`. Une divergence ici est un refactor plus tard. |
| Aucun état dérivé stocké | « en cours », « terminé » se calculent à l'affichage depuis les dates. La donnée ne porte que des faits. |
| Aucun `fetch` dans un composant | Les données descendent de la page en props, sinon la couture fuit partout. |

Deux coutures de plus, du même esprit : **les images** passent par un champ de
données, jamais par un chemin écrit dans un composant, sinon un stockage
distant impose de tout reprendre. **Le formulaire** appelle `envoyerMessage`.

## Ce que le crew ne produit jamais

Ni schéma SQL, ni règles RLS, ni authentification, ni back-office. Ils
s'écrivent à la main, en français, taillés pour la personne qui s'en servira.
`outils/graine.mjs` fait le pont dans l'autre sens : il transforme le contenu
local en `insert`, pour que la base démarre remplie.
