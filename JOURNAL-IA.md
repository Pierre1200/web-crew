# Journal de bord de la V2

**Ce fichier s'adresse à une IA qui reprend le travail.** Il n'est pas la
documentation du produit : celle-ci est le
[`README.md`](README.md) du dépôt. Il raconte ce qui a été fait,
dans quel ordre, pourquoi, ce qui a été vérifié et ce qui ne l'a pas été.

Le lire en entier avant de proposer quoi que ce soit. Il contient trois choses
qu'on ne devine pas en lisant le code : les règles permanentes de Pierre, la
géographie du projet, et la liste de ce qu'il ne faut surtout pas affirmer.

Dernière mise à jour : 1er septembre 2026.

---

## 1. Les règles permanentes, sans exception

Elles viennent de `DEMARRAGE-V2.md` et de Pierre lui-même. Les enfreindre est
la seule façon certaine de rendre le travail inutilisable.

- **Ne jamais lancer `git commit` ni `git add`.** Proposer un message de commit
  prêt à coller, c'est lui qui commite. Il l'a toujours fait jusqu'ici.
- **Aucun appel à l'API sans accord explicite et sans annoncer le coût estimé
  avant.** Les commandes du crew le font déjà : elles affichent un tableau par
  étape et demandent confirmation.
- **Pas de tirets cadratins** dans les textes écrits. Il les repère et les
  déteste. Une virgule ou un deux-points font le travail.
- **Aucun nom de client réel** dans les fichiers versionnés. `CONTEXT.md` est
  ignoré par git, les vrais noms y sont permis.
- **Expliquer de façon pédagogique.** Pierre est en reconversion, quelques mois
  de Python, un passé en C. Les analogies avec le C fonctionnent très bien :
  attribut de classe et variable statique, réducteur et `+=`, checkpointer et
  sauvegarde d'état.

Deux règles de méthode qui ont émergé du travail et qui valent d'être tenues :

- **Vérifier plutôt que raisonner.** Chaque affirmation de ce dépôt a été
  passée à un outil : la porte de build sur un squelette cassé exprès, la
  garantie des couches CSS dans un vrai navigateur, l'équivalence des chemins
  par des tests. Un raisonnement juste sur un fait faux ne se voit pas.
- **Ne jamais surestimer ce qui est vérifié.** Voir le chapitre 6, qui est
  probablement le plus important du fichier.

---

## 2. La géographie, et l'erreur à ne pas refaire

Trois dossiers portent le même code. Il est très facile d'écrire dans le
mauvais, et rien ne le signale.

| Dossier | Branche | Ce que c'est |
|---|---|---|
| `~/Documents/web-crew` | `main` | **la V1, en production, sert de vrais clients.** Ne jamais casser |
| `~/Documents/web-crew-v2` | `v2` | **la V2. C'est ici qu'on travaille.** |
| `~/Documents/web-crew/.claude/worktrees/...` | branche jetable | worktrees ouverts par l'outil |

**L'erreur qui a été commise, une fois :** le répertoire courant du shell est
revenu tout seul au worktree Claude entre deux commandes, et deux fichiers ont
été écrits dans la V1 au lieu de la V2. Rien n'a prévenu. La parade tenue
depuis : **chemins absolus systématiques**, ou un `cd` explicite en tête de
chaque commande.

`DEMARRAGE-V2.md` **n'est pas suivi par git** et vit uniquement dans
`web-crew-v2`. Une session ouverte depuis `web-crew` ne le trouvera pas et
lira la V1 en croyant lire la V2.

L'étalon de qualité visé est un projet écrit à la main par Pierre, hors dépôt :
`~/Documents/adap12-lacabane/lacabane-app` (Next 16, React 19, Supabase, avec
back-office). Il contient les réponses à la plupart des questions
d'architecture. Le lire avant de proposer une structure.

---

## 3. Ce qui a été fait, dans l'ordre

Tout ce qui suit a été réalisé le 1er septembre 2026, en une session, **sans
un seul appel à l'API de génération**. Le coût du travail décrit ici est nul en
jetons de crew.

### Étape 0. Lecture de l'étalon

Lecture intégrale de `lacabane-app` : configuration, `lib/`, `app/`, les
migrations, la feuille de style, plus la documentation locale de Next dans
`node_modules/next/dist/docs/`.

**Le constat qui a changé le plan :** `lacabane-app` est une application avec
serveur, la V2 vise un export statique. Quatre choses qu'elle utilise partout
n'existent pas en export : `headers()` dans `next.config.ts`, `revalidate`, les
Server Actions, l'optimiseur d'images. Écrit dans `SQUELETTE.md`.

### Étape 1. Le squelette front

`squelette/`, 38 fichiers, `npm run verifier` passe. Composition détaillée dans
`SQUELETTE.md`.

Trois choses ne se devinaient pas depuis la lecture seule et ont été apprises
en écrivant :

- `export const dynamic = "force-static"` est obligatoire sur `sitemap.ts` et
  `robots.ts` dès qu'ils sont asynchrones. Le message d'erreur ne dit pas dans
  quel fichier ajouter la ligne.
- `useEffect(() => setState(...))` est refusé par ESLint
  (`react-hooks/set-state-in-effect`). `composants/Etat.tsx` passe donc par
  `useSyncExternalStore`.
- Une liste de définitions vide sous un titre ressemble à une panne. Ce qui
  manque s'écrit en toutes lettres.

### Étape 2. Le recadrage de Pierre sur le formulaire

Première version : le formulaire postait vers un service tiers. **C'était une
erreur.** Pierre a recadré : le crew produit un site vitrine, et si le brief
demande un formulaire, il doit être pensé comme une table de la future base.

Correction : `lib/envoyer-message.ts` est devenu `lib/data/messages.ts`, la
charge utile porte les noms des futures colonnes, les vérifications recopient
les contraintes à venir, et le commentaire montre les deux versions du corps
côte à côte. `squelette/lib/data/LISEZMOI.md` porte le contrat complet.

**Leçon à retenir :** `lib/data/` n'est pas seulement la lecture. L'écriture
obéit aux mêmes règles de couture.

### Étape 3. LangGraph par-dessus la V1

`graphe/`, commande `webcrew graphe`. Le graphe reproduit `generate-safe` sans
toucher à un seul prompt : les nœuds **enveloppent** les agents de la V1, ils
ne les réécrivent pas.

Les quatre points demandés par `DEMARRAGE-V2.md` sont là : checkpointer SQLite
par projet, réducteur `Annotated[float, add]` sur le coût mesuré par différence
sur `BaseAgent.CONSO_RUN`, plafond vérifié avant chaque nœud payant, et
`interrupt()` après la direction artistique.

**Point de vocabulaire à ne pas laisser passer :** « sortie identique » ne peut
pas vouloir dire « octet pour octet ». Deux appels au même modèle avec le même
prompt ne rendent pas le même texte. Ce qui est garanti par construction, c'est
qu'aucun prompt ni modèle n'a changé. Le protocole de comparaison est dans
`graphe/LISEZMOI.md`.

### Étape 4. Le branchement sur le squelette Next

`graphe/front.py`, commande `webcrew front`. La porte de build remplace le
validateur.

Nouveautés notables :

- `utils/verifier.py` : lint, types, build, arrêt au premier échec, problèmes
  typés avec fichier et ligne, codes ANSI retirés.
- `utils/squelette.py` : installation par projet, jamais d'écrasement par
  défaut, publication `site/out` vers `output/`.
- `utils/docs_next.py` : **la trouvaille la plus rentable de la session.** Le
  nœud lit `node_modules/next/dist/docs/` du projet et injecte dans le prompt
  la table des conventions de la version réellement installée. La ligne qui
  compte, extraite telle quelle du paquet : « middleware.js, API reference for
  the middleware.js file (deprecated, renamed to proxy.js) ». C'est la parade
  déterministe au piège décrit dans `DEMARRAGE-V2.md`, pour 650 jetons.
- `agents/front.py` : trois agents, et deux décisions qui tiennent tout le
  fichier. **On ne transporte jamais du code dans du JSON** (les fichiers
  voyagent entre marqueurs de ligne), et **la charte ne renvoie que des
  valeurs** que Python pose lui-même dans les tokens.

### Étape 5. La revue complète

Demandée par Pierre. Elle a trouvé quatre pannes silencieuses, toutes du même
type : le site se construit, tout est vert, et le résultat est faux. Elles sont
détaillées au chapitre 5.

---

## 4. Les décisions structurantes, et leur raison

À ne pas rouvrir sans raison sérieuse. Chacune a une justification qui n'est
pas évidente de l'extérieur.

| Décision | Pourquoi |
|---|---|
| Next en export statique, CSS vanilla, pas de Tailwind | la boucle de correction visuelle ajoute des règles en fin de feuille ; avec Tailwind il faudrait éditer des chaînes de classes dans le JSX, opération bien moins fiable pour une machine |
| Le crew part d'un squelette, il n'invente pas la structure | la surface où la machine peut se tromper s'effondre, et la facture avec |
| Les nœuds appellent les SDK bruts, jamais les abstractions LangChain | c'est ce qui permet de garder `effort`, le raisonnement adaptatif et le comptage de coût exact |
| La topologie du graphe est figée | le prompt de l'orchestrateur fixe les priorités 1, 2, 3 : le plan ne décide que de l'inclusion. Le nœud le revérifie à chaque run |
| Un fil de reprise LangGraph par run | réutiliser le même cumulerait les dépenses de deux runs dans le même compteur et fausserait la garde de budget |
| `output/` reste le dossier livré | `diff`, `restore` et l'audit de sécurité continuent de fonctionner sans modification |
| Les fichiers voyagent hors JSON | un TSX entier échappé dans une chaîne JSON, c'est ce qui a lâché deux fois sur douze au premier run réel de la V1 |
| Le slug est calculé une fois, par Python | deux implémentations d'une même règle dans deux langues divergent toujours |
| `async` dès le premier jour dans `lib/data/` | une fonction synchrone rend synchrones tous ses appelants ; la rendre asynchrone plus tard oblige à toucher chaque composant |

---

## 5. Les bugs trouvés, et la leçon de chacun

Ils partagent tous la même signature : **aucun outil ne les signale**. C'est ce
qui les rend chers, et c'est pour ça qu'ils sont listés ici.

**Les polices n'étaient jamais téléchargées.** L'enveloppe du squelette charge
`/polices/polices.css` sans condition, la charte nomme des familles, et rien ne
produisait le fichier. 404 visible dans la seule console du navigateur, retour
silencieux à la police de secours. *Leçon : un `<link>` vers un fichier absent
ne fait échouer aucune construction.*

**La boucle de correction visuelle ne tenait pas sa promesse.** Le prompt de la
critique affirme au modèle que ses correctifs sont « hors couche, ce qui leur
donne déjà la priorité sur tout le reste ». Vrai en V1, faux dans le squelette,
qui n'avait aucune couche. *Leçon : quand un prompt affirme une propriété
technique, vérifier qu'elle est vraie dans le code qui reçoit le résultat.*

**Le front pouvait écraser `charte.css`.** Il passe juste après l'agent qui
l'écrit. *Leçon : une liste blanche d'écriture doit être relue chaque fois
qu'un nœud est ajouté avant un autre.*

**La critique visuelle ne voyait qu'une page sur un export Next.** Elle cherche
`blog/article.html`, l'export écrit `blog/article/index.html`. *Leçon : le code
de la V1 qui « marche encore » en V2 mérite d'être relu avec la disposition de
fichiers de la V2 sous les yeux.*

**Une clé d'état non déclarée est jetée en silence par LangGraph.** Le nœud
croit avoir écrit, le suivant lit une clé absente, l'aiguillage part du mauvais
côté, aucune erreur n'est levée. Trouvé par une doublure de test, pas par la
lecture. *Un test relit maintenant les nœuds et compare à `EtatCrew` : le
lancer avant de chercher ailleurs.*

**Les tests écrivaient dans le vrai `projects/`.** Un nœud non doublé y créait
des dossiers. *Une fixture `autouse` dans `conftest.py` l'interdit désormais à
tous les tests, pas seulement à ceux qui demandent la fixture `proj`.*

---

## 6. Ce qui est vérifié, et ce qui ne l'est pas

**À lire avant d'affirmer quoi que ce soit à Pierre.** Il travaille pour de
vrais clients payants : une affirmation optimiste lui coûte une soirée.

### Vérifié, avec l'outil qui l'a vérifié

| Affirmation | Comment |
|---|---|
| le squelette compile et se sert | `npm run verifier` + serveur local + captures dans un navigateur |
| la porte détecte les trois familles d'erreurs | squelette cassé exprès de trois façons, sorties réelles conservées dans les tests |
| un correctif hors couche bat une règle plus spécifique en couche | duel de spécificité construit, `getComputedStyle` dans un vrai navigateur |
| le plafond coupe avant le nœud le plus cher | doublures de coût dans le graphe réel |
| le feu vert arrête et un refus ne dépense rien de plus | `interrupt()` puis `Command(resume="non")` |
| on ne publie jamais sans porte verte | `publier` n'a qu'une arête entrante, un test le vérifie |
| toute clé de nœud est déclarée | relecture AST des deux fichiers de nœuds |
| la doc locale de Next contient bien le renommage | lecture du paquet installé |

330 tests passent, aucun n'appelle l'API ni npm.

### Jamais vérifié

- **Les deux graphes n'ont jamais tourné contre l'API.** Ni `graphe`, ni
  `front`. Le câblage l'est, les prompts non.
- **Les prompts des trois agents front n'ont jamais été confrontés à un
  modèle.** `CharteAgent`, `FrontAgent`, `ReparateurAgent`. Le premier run réel
  les jugera, et il faudra une passe de retouche derrière. Ne pas les présenter
  comme fonctionnels.
- **Aucun site V2 n'a jamais été produit.** `projects/` est vide.
- **`heberger_polices_next` n'a jamais téléchargé quoi que ce soit.** Seule sa
  partie hors ligne est testée. Le squelette par défaut n'utilise que des
  familles système, donc le chemin réseau ne s'est jamais exécuté.
- **La partie V1 de `utils/polices.py` n'a aucun test.**

---

## 7. Les conventions du dépôt

- **Tout en français** : noms de fonctions, de variables, commentaires,
  messages. Le code existant s'y tient, s'y tenir aussi.
- **Les commentaires expliquent POURQUOI, jamais QUOI.** Le dépôt est plein de
  commentaires qui racontent un bug vécu et ce qu'il a coûté. C'est sa plus
  grande valeur : ne pas les résumer, ne pas les supprimer.
- **Les problèmes sont des dicts typés**, jamais des phrases :
  `{"type": ..., "niveau": ..., "message": ...}`. L'aiguillage se fait sur le
  type. Avant, du filtrage sur le texte français cassait la correction dès
  qu'un message était reformulé.
- **Les modules `utils/` ne consomment aucun jeton.** C'est la vraie valeur de
  web-crew. Ne pas les réécrire.
- **Un test décrit un comportement, pas une implémentation.** Les noms de test
  du dépôt sont des phrases : `test_le_plafond_coupe_avant_le_designer`.
- **`main.py` est le seul point d'entrée**, et la facture s'affiche dans un
  `finally` pour survivre à une exception.

---

## 8. La suite, dans l'ordre

1. **Le premier run réel de `webcrew front`**, sur un projet avec brief et
   configuration. C'est la seule chose qui puisse juger les prompts. Prévoir
   une passe de retouche derrière, et un plafond bas pour la première fois.
2. **Retoucher les prompts front** d'après ce que ce run montre.
3. **MiniMax sur les nœuds mécaniques** : structuration des textes extraits,
   slugs, textes alternatifs, méta-descriptions. Pierre n'a pas encore la clé
   API. L'API est compatible OpenAI : SDK `openai` avec une autre `base_url`.
   Vérifier avant de s'engager : le nom exact des modèles, l'URL de l'endpoint
   international, et surtout **l'existence d'un mode JSON strict**. Ce dernier
   point est décisif, toute la chaîne dépend de JSON parsable.
4. **Séparer le modèle de contenu des pages** dans le graphe front, avec un
   second feu vert entre les deux, comme `DEMARRAGE-V2.md` le demande.
   Aujourd'hui `FrontAgent` produit les deux en un appel.
5. **Décider du sort de l'orchestrateur.** Son prompt planifie `designer` et
   `seo`, qui n'ont pas de nœud dans le graphe front. Ce n'est pas du
   gaspillage (l'instruction du designer est ce que `cahier_des_charges()`
   transmet au front), mais un prompt propre au front serait plus honnête.
   Attention : le modifier casse l'équivalence V1 de l'étape 2.
6. Tenir ce journal à jour : y écrire ce que le premier run réel
   révèle, et faire passer les lignes correspondantes du chapitre 6 de
   « jamais vérifié » à « vérifié, et voici comment ».

---

## 9. Les pièges qui coûtent une demi-journée

Ceux qu'on ne trouve pas en lisant le code.

- Le répertoire courant du shell revient au worktree Claude sans prévenir.
  Chemins absolus.
- Turbopack refuse un `node_modules` en lien symbolique et échoue sur un panic
  illisible. Une installation par projet, sans exception.
- `next build` en export statique refuse toute route asynchrone sans
  `force-static`, et ne dit pas laquelle.
- Un état calculé pendant le rendu d'une page est figé au jour du build. Rien
  ne le signale, et la capture visuelle est faite le même jour.
- Supprimer `.next/` pendant que `npm run dev` tourne fait servir des 404 sur
  toutes les pages.
- Avec Supabase, une règle RLS manquante ne renvoie pas d'erreur : elle renvoie
  zéro ligne. Une page vide sans message est presque toujours une règle
  manquante, pas un bug de code.
- `BaseAgent.CONSO_RUN` est un attribut de CLASSE, partagé par tout le
  processus. Un test qui ne le remet pas à zéro hérite du compteur du
  précédent.
