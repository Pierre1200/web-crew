# Le squelette front

Le point de départ de tout site produit par web-crew. Le crew ne construit pas
une application depuis rien : il copie ce dossier et ne produit que les
variations.

```bash
npm install
npm run dev        # http://localhost:3000
npm run verifier   # ESLint, TypeScript, puis la construction. Les trois doivent passer.
```

`npm run build` écrit le site dans `out/`.

## Ce que le crew a le droit de toucher

| Fichier | Qui l'écrit |
|---|---|
| `site.config.ts` | le crew, des VALEURS uniquement |
| `app/charte.css` | le crew, le côté droit des deux points uniquement |
| `lib/types.ts`, `lib/data/*.ts` | le crew : le modèle de contenu et la couture |
| `app/**/page.tsx`, `composants/` engendrés | le crew |
| `app/composants.css` | le crew |
| `app/correctifs.css` | la boucle de correction visuelle, et elle seule |
| tout le reste | personne, c'est le squelette |

## Les trois pièges de l'export statique

1. **Aucun état calculé pendant le rendu d'une page.** Le site est construit une
   fois : « En cours » calculé au build sera encore affiché des mois plus tard.
   Passer par `composants/Etat.tsx`, qui recalcule dans le navigateur.
2. **Les en-têtes de sécurité ne sont pas dans `next.config.ts`.** `headers()`
   n'a aucun effet ici. Ils sont écrits par `utils/securite.py` dans le fichier
   de l'hébergeur.
3. **Pas de Server Actions.** Le formulaire appelle `lib/data/messages.ts`,
   qui écrit depuis le navigateur. C'est aussi ce que fera l'insertion en base,
   autorisée par une règle RLS : un site statique n'a pas besoin de serveur
   pour écrire.

## Un formulaire est une table

Si le brief demande un formulaire, il est pensé dès le premier jour comme une
table de la future base : une fonction nommée, une charge utile aux noms des
futures colonnes, des vérifications qui recopient les contraintes à venir. Le
jour du branchement, seul le corps de `envoyerMessage` change. Voir
`lib/data/LISEZMOI.md`.

Le crew ne produit ni schéma, ni RLS, ni back-office.

## La règle mère

Aucune donnée en dur dans le balisage. Une page appelle une fonction de
`lib/data/`, jamais un fichier directement. Ces fonctions sont `async` dès le
premier jour, même pour lire un fichier local : c'est ce qui permet de brancher
une base plus tard en réécrivant trois corps de fonctions, sans toucher une
seule page.
