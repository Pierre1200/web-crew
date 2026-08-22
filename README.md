# web-crew

**Une brigade d'agents IA qui génère des sites vitrines statiques, du brief client au site livré.**

`web-crew` est un pipeline multi-agents en Python, inspiré de l'organisation d'une brigade de cuisine : chaque agent a un rôle précis, et un orchestrateur coordonne le tout. On ne touche jamais au code — on « branche » le crew sur un dossier client contenant un brief et une config, et il produit un site complet (HTML/CSS/JS), optimisé SEO et validé.

---

## Fonctionnement

```
  ENTRÉES      brief.md  ·  config.json  ·  data/ (docx, pdf, images, textes)
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  CADRAGE      INGESTION ──────────────▶  temp/context.json
  ~0,20 $      ORCHESTRATEUR ──────────▶  temp/plan.json      (la maquette)
               DIRECTION ARTISTIQUE ───▶  temp/direction.json (la composition)
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  PRODUCTION   COPYWRITER ───────────▶  temp/textes.json
  ~1,30 $      DESIGNER ─────────────▶  index.html · style.css · main.js
               PAGES ────────────────▶  blog/… (1 appel, quel que soit N)
               SEO ──────────────────▶  balises · sitemap.xml · robots.txt
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  CONTRÔLE     VALIDATEUR ──────────▶  structure, liens, médias   (0 token)
               CRITIQUE ────────────▶  le fond des textes
               CRITIQUE VISUELLE ───▶  le rendu réel, en images  (~0,15 $)
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  LIVRAISON    SÉCURITÉ ────────────▶  durcissement · SECURITE.md (0 token)
```

Chaque étape écrit son résultat sur le disque, et chacune est rejouable seule :
on ne repaie jamais une phase pour en corriger une autre.

L'orchestrateur lit le brief en langage naturel et décide **dynamiquement** quels
agents de production mobiliser et dans quel ordre — aucun chemin ni séquence en
dur. Les étapes dont la place ne se discute pas (cadrage, contrôle, livraison)
sont appelées explicitement : voir [Ajouter un agent](#ajouter-un-agent).

---

## La brigade

Chaque agent tourne sur le modèle et la profondeur de raisonnement adaptés à sa tâche — un arbitrage **qualité / coût** assumé : les modèles les plus puissants là où la valeur se joue (contenu, design), les plus économiques sur les tâches mécaniques à schéma fixe.

| Agent | Rôle | Modèle | Raisonnement | Effort |
|---|---|---|---|---|
| **Ingestion** | Digère les données client brutes (docx/pdf/images) en contexte structuré | Sonnet 5 | ✅ | high |
| **Orchestrateur** | Lit le brief, transcrit la maquette, produit le plan de travail | Sonnet 5 | ✅ | high |
| **Direction artistique** | Arrête l'archétype, la palette, le rythme et la typographie | Opus 5 | ✅ | **xhigh** |
| **Copywriter** | Rédige tous les textes du site à partir du contenu réel | Opus 5 | ✅ | high |
| **Designer** | Génère HTML + CSS + JS cohérents en une passe | Opus 5 | ✅ | **xhigh** |
| **Validateur** | Contrôle qualité pur Python (HTML complet, classes cohérentes, médias…) | — *(0 token)* | — | — |
| **Critique** | Contrôle du fond des textes : faits inventés, sections creuses, générique | Sonnet 5 | ✅ | high |
| **Critique visuelle** | Photographie le site rendu et juge composition, maquette, contrastes | Opus 5 | ✅ | **xhigh** |
| **Sécurité** | Audite les tiers, durcit le site, écrit le rapport de livraison | Sonnet 5 *(1 appel optionnel)* | ✅ | high |
| **SEO** | Métadonnées, Open Graph, Schema.org, sitemap, robots.txt | Haiku 4.5 | — | — |

`effort` (`low` → `max`) règle la profondeur de travail du modèle : c'est le principal levier qualité/coût. Le designer tourne en `xhigh`, le réglage le plus adapté aux tâches de code. **Haiku 4.5 refuse `effort` et le raisonnement adaptatif** — d'où `EFFORT = None` et `THINKING = None` sur l'agent SEO.

L'extraction de texte, le catalogage d'images et toute la validation sont réalisés en **Python pur, sans appel IA** — les tokens ne sont dépensés que là où l'intelligence apporte réellement quelque chose.

---

## Installation

```bash
git clone <url-du-repo>
cd web-crew

python3 -m venv .venv              # Python 3.12+ requis
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

**Une étape de plus pour la critique visuelle** — Playwright a besoin de
télécharger un navigateur (~150 Mo), une seule fois :

```bash
playwright install chromium
```

Sans lui, tout le reste fonctionne : seule la commande `visuel` s'arrêtera, avec
un message indiquant quoi lancer.

### Vérifier que tout est en place

```bash
python3 -m pytest tests/ -q        # 182 tests, aucun appel API, aucune clé requise
python3 main.py list-agents
```

Si les tests passent sans clé API, l'installation est bonne : le client Anthropic
n'est créé qu'au premier appel réel.

---

## Utilisation

```bash
# Pipeline complet : ingestion → orchestrateur → direction → copywriter → designer → SEO
python3 main.py generate --project mon-client

# Le chemin recommandé : génération + correction auto + 2 passes de critique visuelle
python3 main.py generate-safe --project mon-client --visuel 2
```

Étapes isolées, pour itérer sans repayer un pipeline complet :

```bash
python3 main.py ingest       --project mon-client   # digère data/ uniquement
python3 main.py design-only  --project mon-client --replan   # redessine (voir ci-dessous)
python3 main.py securiser    --project mon-client   # audit de sécurité — gratuit
python3 main.py pages        --project mon-client   # (re)génère les collections — gratuit
python3 main.py direction    --project mon-client   # rejoue la direction artistique seule
python3 main.py visuel       --project mon-client --corriger # juge le rendu et corrige
python3 main.py validate     --project mon-client   # validateur seul (0 token)
python3 main.py critique     --project mon-client   # contrôle du fond des textes
python3 main.py seo-only     --project mon-client   # métadonnées SEO seules

python3 main.py diff         --project mon-client   # ce que le dernier run a changé (0 token)
python3 main.py restore      --project mon-client   # annule le dernier run (0 token)
python3 main.py list-agents                          # agents du registre
```

> **`design-only` sans `--replan` rejoue l'ANCIEN plan.** Le plan porte le cahier
> des charges depuis qu'il pilote la maquette : après toute modification de
> `brief.md` ou `config.json`, `--replan` rafraîchit le plan pour quelques
> centimes. Sans lui, tu paies une génération qui reproduit l'ancienne maquette.

Prévisualiser le site généré :

```bash
cd projects/mon-client/output && python3 -m http.server 8080
# → http://localhost:8080
```

---

## ⚠️ `output/` est jetable

Chaque génération **écrase** `output/`. Toute correction faite à la main dedans
disparaît au run suivant : la valeur doit remonter dans `brief.md` ou
`config.json`, sinon elle n'existe pas. Un branchement Formspree posé à la main
dans le HTML, par exemple, doit devenir `site.formspree_id` dans la config.

Deux filets protègent les runs payants :

- **Sauvegarde automatique** — avant chaque génération, `output/` est copié dans
  `output_prev/`. `diff` montre ce qui a changé, `restore` revient en arrière.
- **Contrôle de pré-vol** — si le site actuel contient un branchement absent de
  la config, la commande le signale **avant** de dépenser quoi que ce soit.

---

## Sécurité et livraison

Un site statique a une surface d'attaque minuscule : pas de serveur applicatif,
pas de base de données, pas de dépendances à patcher, pas de comptes utilisateurs.
Prétendre le contraire serait du théâtre. Les vrais sujets sont ailleurs — les
services tiers, le durcissement absent, et les secrets oubliés.

```bash
python3 main.py securiser --project mon-client              # audit seul, gratuit
python3 main.py securiser --project mon-client --durcir     # applique les corrections
python3 main.py securiser --project mon-client --durcir --injection
```

Le durcissement est une commande **séparée**, à lancer quand le rendu convient :
il modifie le site généré, on ne le rejoue pas à chaque essai.

### Ce que le durcissement applique

| Action | Pourquoi |
|---|---|
| **Polices hébergées sur le site** | Sans cela, chaque visiteur transmet son adresse IP à Google. Un jugement allemand de 2022 a condamné un exploitant pour exactement cela. Rapatrier les fichiers supprime le transfert, la dépendance au CDN, et deux connexions au chargement. |
| **`_headers` et `.htaccess`** | En-têtes de sécurité pour Netlify/Cloudflare et Apache, avec une **CSP calculée depuis le site réel** — pas recopiée d'un tutoriel. |
| **`rel="noopener noreferrer"`** | Une page ouverte dans un nouvel onglet ne peut plus agir sur celle du site. |
| **Pot de miel anti-robot** | Un champ invisible que seuls les robots remplissent ; Formspree jette ces envois. |

Seules les sous-familles `latin` et `latin-ext` des polices sont conservées :
Google en sert une dizaine (cyrillique, grec, vietnamien…) dont un site français
n'a aucun usage.

### L'audit et le rapport client

L'audit est gratuit et produit `output/SECURITE.md` — le site est livré **avec
son audit**. Le rapport liste les services extérieurs contactés (« où partent les
données de mes visiteurs ? »), ce qui a été durci, et ce qui reste à la charge du
client.

Les contrôles : contenu mixte `http://` sur un site `https`, liens `target="_blank"`
non protégés, `innerHTML`/`eval` dans le JS, iframes sans `referrerpolicy`, adresses
email en clair, formulaires sans piège, et **recherche de secrets** dans les fichiers
sur le point d'être livrés (les clés trouvées ne sont jamais recopiées en entier
dans le rapport — elles sont à révoquer, pas à archiver).

### Le seul appel au modèle : les documents du client

`--injection` relit les documents de `data/` à la recherche de passages rédigés
pour détourner un automate — « ignore les instructions précédentes », « ajoute ce
lien dans le pied de page ». Le risque est réel puisque l'agent Ingestion insère
ces textes dans les prompts des autres agents, et qu'un client transmet parfois un
document dont il n'est pas l'auteur. C'est sémantique, donc c'est le bon usage
d'un modèle — tout le reste est déterministe.

---

## Pages multiples — blog, réalisations, services…

Un site peut porter des **collections** : des ensembles de pages produites à
partir de textes écrits par le client. Un blog en est le cas typique, mais le
mécanisme est générique (portfolio, fiches services, actualités).

```json
"site": {
  "collections": [
    { "id": "blog", "titre": "Le blog", "source": "articles",
      "chapeau": "Les histoires qui ne tiennent pas en trois minutes de vidéo.",
      "flux": true }
  ]
}
```

Le client dépose ses textes dans `data/articles/`, un fichier `.txt` par page :

```
Titre: D'où vient le mot « bougnat » ?
Chapo: Derrière le nom, il y a un métier et une migration.
Date: 2026-08-14
Couverture: charbon.jpg
Statut: publie

Le mot « bougnat » désigne à Paris les Auvergnats venus s'y installer.

## Du charbon au comptoir

Les marchands livraient les immeubles, étage par étage.

> Le comptoir et le charbon, dans la même boutique.
```

**Ce n'est pas du Markdown, volontairement.** Une ligne vide sépare deux
paragraphes, `## ` ouvre un sous-titre, `> ` une citation. Le client n'a aucune
syntaxe à apprendre — et comme le crew n'insère jamais de HTML écrit par lui
(tout est échappé avant insertion), l'injection est impossible **par
construction** plutôt que par vigilance.

Le format est permissif : sans en-tête, le titre vient du nom du fichier et la
date de sa dernière modification. `Statut: brouillon` garde une page hors ligne
le temps de la finir.

### Le coût ne dépend pas du nombre de pages

Le modèle produit **un gabarit par collection** — une page de liste, une page de
contenu, et le balisage des paragraphes, sous-titres, citations et images. Python
le remplit ensuite pour chaque texte. Cinquante articles coûtent donc **un seul
appel**, et sont cohérents entre eux par construction.

Les gabarits sont mis en cache dans `temp/`. Corriger une faute de frappe dans un
article et régénérer le site est **gratuit** :

```bash
python3 main.py pages --project mon-client              # gratuit (gabarits en cache)
python3 main.py pages --project mon-client --gabarits   # redessine les gabarits
```

Chaque collection reçoit aussi son **flux RSS**, et le `sitemap.xml` est
recalculé pour lister toutes les pages — sans quoi un blog de trente articles
resterait invisible des moteurs de recherche.

Le validateur contrôle ensuite les pages secondaires : liens cassés résolus
**depuis le dossier de la page** (c'est là que se glissent les préfixes `../`
oubliés), `<h1>` et meta viewport présents, collections déclarées mais vides.

---

## Direction artistique

Avant qu'une seule ligne de code soit écrite, un agent **arrête la composition
du site** et l'écrit dans `temp/direction.json`. Séparer la décision de
l'exécution change tout : auparavant, les choix de mise en page étaient pris
implicitement par le designer, au milieu de la génération de 25 000 tokens de
code — le pire moment pour décider quoi que ce soit.

La direction produit des **décisions chiffrées**, pas des conseils. « Varier le
rythme vertical » ne sert à rien ; `{"hero": "160px, très aéré", "contact":
"64px, dense"}` est applicable tel quel.

```bash
python3 main.py direction --project mon-client
python3 main.py direction --project mon-client --archetype galerie-grille
```

L'archétype de mise en page est choisi dans un vocabulaire fermé, ce qui force
un vrai parti pris au lieu du réflexe « sections empilées » :

| Archétype | Parti pris |
|---|---|
| `editorial-asymetrique` | Deux colonnes inégales, rythme de magazine |
| `cinematique-plein-ecran` | Grandes images, texte rare et fort |
| `galerie-grille` | La grille d'images **est** la structure |
| `document-centre` | Une colonne étroite, typographie dominante |
| `panneau-fixe` | Une colonne fixe, une colonne qui défile |
| `vitrine-sectionnee` | Le classique — à ne choisir que s'il est le plus juste |

La direction décide aussi la palette (en `oklch` avec ses dérivations), l'échelle
typographique, le traitement des surfaces, la politique de mouvement (liste
**fermée** de ce qui s'anime), et une **signature** : ce qui, dans ce site, ne
pourrait appartenir à aucun autre client.

Trois conséquences en chaîne :

- **Le designer** reçoit ces valeurs à la place des principes génériques — le
  prompt ne grossit pas, il se précise (+100 tokens environ).
- **La critique visuelle** juge l'**écart** entre les décisions annoncées et le
  rendu réel, au lieu de donner un avis de goût. Un écart avec la direction est
  au minimum « majeur ».
- **L'itération devient bon marché** : changer d'archétype et relancer
  `design-only` coûte une fraction d'une génération complète.

---

## Les vraies images du client

### Les photos piégées dans les documents

Les clients joignent rarement leurs photos : ils les **collent dans un document
Word**. Un `.docx` de 380 Ko peut ne contenir que 379 caractères de texte et
quatre photos — invisibles pour qui ne lit que les paragraphes.

L'ingestion ouvre donc les `.docx` et les `.pdf` pour en sortir les images, et
les dépose dans `data/images-extraites/` sous un nom dérivé du document
(`LA CABANE INFOS.docx` → `la-cabane-infos-1.png`). Elles rejoignent ensuite le
flux normal : catalogue, suggestion d'emplacement, copie vers `output/assets/`.

Deux filtrages, parce qu'un document contient autre chose que des photos :

- **Les artefacts de mise en page** sont écartés — moins de 5 Ko, ou moins de
  120 px de côté : ce sont des filets, des puces, des images d'espacement. Les
  fichiers `.wdp` que Word range à côté des PNG le sont aussi, aucun navigateur
  ne les lit.
- **Les doublons** sont écartés par empreinte du contenu. Un logo présent dans
  chaque document ne serait sinon proposé cinq fois au designer.

L'opération est idempotente : une image déjà extraite n'est pas réécrite, ce qui
garde l'empreinte de `data/` stable et le cache d'ingestion valide.

### Toutes les images

Tout fichier image déposé dans `data/` est **copié automatiquement** dans
`output/assets/` sous un nom compatible URL (`Portrait Denis Moulin.jpg` →
`portrait-denis-moulin.jpg`), et ses **dimensions réelles sont lues** en
décodant l'en-tête du fichier — PNG, JPEG, GIF, WebP et SVG, en Python pur,
sans dépendance ni appel IA.

Le designer reçoit alors un manifeste (chemin, dimensions, ratio, orientation,
poids) et doit s'en servir **en priorité** : les images de remplissage
`picsum.photos` ne sont tolérées que là où aucune photo du client ne convient.

Pourquoi les dimensions comptent : sans `width` et `height` sur une balise
`<img>`, le navigateur ne connaît la place à réserver qu'une fois l'image
chargée, et la page **saute** sous les yeux du visiteur. C'est le défaut le plus
visible d'un site amateur, et il se corrige avec deux attributs.

Les images déjà déposées à la main dans `output/assets/` (un logo fourni, par
exemple) sont reprises dans le manifeste, jamais ignorées.

Le validateur contrôle ensuite, gratuitement :

| Problème | Niveau | Ce qu'il attrape |
|---|---|---|
| `ressource_cassee` | erreur | Une image ou un script référencé dont le fichier n'existe pas |
| `image_inutilisee` | avertissement | Une photo fournie par le client jamais affichée |
| `placeholder_en_production` | avertissement | Du remplissage alors que le client a fourni ses visuels |

---

## CSS moderne

Les sites livrés sont en HTML/CSS/JS statique — c'est un choix, pas une limite :
hébergement gratuit, chargement instantané, aucune dépendance à maintenir, et un
livrable que le client peut déposer où il veut. La modernité est allée dans le
**CSS**, pas dans un framework.

Le designer a pour consigne d'employer, là où ils servent vraiment :

| Outil | Ce qu'il apporte |
|---|---|
| `@layer` | Feuille rangée en couches — **et les correctifs visuels, écrits hors couche, l'emportent sans `!important`** |
| Container queries | Un composant s'adapte à la largeur de **son conteneur**, pas de l'écran |
| `:has()` | Mise en page qui réagit au contenu réel (`.card:has(img)`) |
| `oklch()` + `color-mix()` | Système tonal dérivé de 3-4 couleurs, dégradés sans zone grisâtre |
| `subgrid` | Titres et boutons alignés d'une carte à l'autre |
| `text-wrap: balance` / `pretty` | Plus de lignes veuves ni de coupures disgracieuses |
| Propriétés logiques | `margin-inline`, `padding-block`, `inset` |
| `animation-timeline: view()` | Révélation au défilement sans JavaScript, sous `@supports` avec repli |

Le point structurant est le premier. Sans couches, un correctif `.hero{…}` ajouté
en fin de feuille **ne bat pas** un `.section .hero{…}` existant, plus spécifique —
la correction automatique deviendrait un coup de dés. Avec les couches, une règle
hors couche l'emporte sur toutes les couches, quelle que soit sa spécificité.

Le validateur vérifie gratuitement ces exigences : `cascade_sans_layer`,
`motion_non_geree` (absence de `prefers-reduced-motion`) et `cascade_forcee`
(abus de `!important`) — trois avertissements non bloquants.

---

## Critique visuelle

Le validateur prouve que le HTML est *valide* ; il ne dira jamais qu'il est *beau*.
La commande `visuel` photographie le site rendu (Playwright, en local) à trois
largeurs — mobile 390 px, tablette 820 px, bureau 1440 px — et soumet les images
à un directeur artistique qui juge la conformité à la maquette, la composition,
la typographie, les contrastes et le comportement responsive.

```bash
pip install playwright && playwright install chromium   # une seule fois
python3 main.py visuel --project mon-client --corriger --tours 2
```

Le verdict arrive dans `temp/critique_visuelle.json` (score /10, conformité au
brief, problèmes classés par gravité), les captures dans `logs/captures/`.

**Seule la critique coûte des tokens** (~0,15 $ la passe) : les correctifs CSS
qu'elle rédige sont appliqués mécaniquement, sans nouvel appel au modèle. Itérer
sur le rendu revient donc à une fraction du prix d'une régénération complète.

---

## Structure d'un projet client

Le code est un **plugin** : il ne change jamais. Chaque client est un dossier autonome.

```
projects/mon-client/
├── brief.md        # le cahier des charges en langage naturel
├── config.json     # config technique (sections, style, SEO, client)
├── data/           # données brutes fournies par le client (docx, pdf, images)
│   └── articles/   # un .txt par page de collection (blog, réalisations…)
├── output/         # site généré (HTML/CSS/JS) — JETABLE          ← non versionné
├── output_prev/    # sauvegarde du run précédent (diff / restore) ← non versionné
├── temp/           # fichiers d'échange inter-agents              ← non versionné
└── logs/           # un log par agent + captures d'écran          ← non versionné
```

### `config.json`

```json
{
  "client":  { "nom": "…", "localisation": "…", "contact_principal": "…" },
  "site": {
    "objectifs": ["…"],
    "cibles":    ["…"],
    "sections":  ["Hero — accroche", "À propos", "Services", "Contact"],
    "style":     { "ambiance": "…", "couleurs_suggérées": ["…"], "typographie": "…" },
    "formspree_id": ""
  },
  "seo": {
    "type_schema": "LocalBusiness",
    "secteur": "…",
    "mots_cles_prioritaires": ["…"],
    "zone_geographique": "…"
  },
  "output": { "project_id": "mon-client", "type": "site vitrine statique" }
}
```

**`formspree_id`** : identifiant [Formspree](https://formspree.io) pour l'envoi réel des
formulaires (les 8 caractères après `/f/` dans l'URL du formulaire). S'il est renseigné,
le designer génère des formulaires branchés (action + envoi fetch) ; sinon, le JS affiche
un message honnête invitant à contacter le client par email — jamais de faux « message envoyé ».

**Clés `_note…`** : toute clé dont le nom commence par `_note` (sous `site` ou sous
`site.style`) est une **consigne adressée aux agents**, transmise telle quelle au designer.
C'est le moyen d'imposer une contrainte que le reste de la config ne sait pas exprimer :

```json
"_note_sections":   "Corps en deux colonnes : gauche étroite, droite large.",
"_note_formulaire": "PAS de formulaire de contact — un simple lien mailto."
```

### Galerie vidéo / audio

Le champ `site.medias` déclare des lecteurs hébergés chez différents fournisseurs.
**Il suffit de coller l'URL publique** : le fournisseur est reconnu automatiquement et
l'URL d'intégration est construite en Python (zéro token, aucun format inventé).

```json
"site": {
  "medias": {
    "titre_section": "Les vidéos",
    "items": [
      { "titre": "L'Auberge Aveyronnaise",
        "url": "https://youtu.be/XXXXXXXXXXX",
        "description": "Le premier épisode, dans le 12e." },
      { "titre": "La playlist du studio",
        "url": "https://open.spotify.com/playlist/XXXXXXXX" }
    ]
  }
}
```

Fournisseurs reconnus : **YouTube** (en `youtube-nocookie`), **Vimeo**, **Dailymotion**,
**PeerTube**, **Spotify**, **SoundCloud**, **Deezer**. Les vidéos gardent leurs proportions
via `aspect-ratio`, les lecteurs audio leur hauteur propre, et tous les iframes sont en
`loading="lazy"`. La **mise en page** de la galerie, elle, suit le brief du client.

Le validateur vérifie que chaque média déclaré est bien présent dans le HTML livré
(`media_manquant`) et signale les URL non reconnues (`media_invalide`).
Pour ajouter un fournisseur : une entrée dans `_FOURNISSEURS` ([utils/embeds.py](utils/embeds.py)),
rien d'autre à toucher.

---

## Ajouter un client

1. Créer `projects/mon-client/`
2. Écrire `brief.md` (les consignes, en prose)
3. Écrire `config.json` (copier la structure ci-dessus)
4. Déposer les documents dans `data/` (optionnel)
5. `python3 main.py generate --project mon-client`

Aucune ligne de code à modifier.

---

## Ajouter un agent

Tous les agents héritent de `BaseAgent`, mais il en existe **deux familles**,
selon qui décide de les lancer.

**Agents planifiés** — l'orchestrateur choisit de les mobiliser ou non, selon le
brief. Ce sont ceux du registre : copywriter, designer, seo.

1. Créer `agents/mon_agent.py` héritant de `BaseAgent`
2. L'ajouter à `AGENT_REGISTRY` dans `main.py`
3. Le présenter dans le system prompt de l'orchestrateur

**Agents à étape fixe** — leur place dans la chaîne ne se discute pas : ingestion
et direction artistique arrivent forcément avant la production, validateur,
critique, critique visuelle et sécurité forcément après. Ils ne sont pas dans le
registre : ils sont appelés explicitement par `main.py`, et exposés en commande.

1. Créer `agents/mon_agent.py` héritant de `BaseAgent`
2. L'appeler à l'endroit voulu dans `main.py`, et lui donner sa commande

Le choix entre les deux tient à une seule question : **l'orchestrateur peut-il
légitimement décider de sauter cette étape ?** Si non, elle n'a rien à faire dans
le registre.

---

## Stack technique

- **Python 3** — Typer (CLI), python-dotenv
- **API Claude** (SDK `anthropic`) — Opus 5 / Sonnet 5 / Haiku 4.5 selon l'agent, raisonnement adaptatif et `effort` réglable
- **Playwright** (optionnel) — capture du rendu pour la critique visuelle
- **Extraction** — pypdf, python-docx
- **Sortie** — HTML5, CSS3, JavaScript vanilla (zéro dépendance front)

---

## Architecture en bref

- **`utils/project.py`** — la classe `Project` calcule tous les chemins depuis le seul nom du client. Pièce centrale du modèle « plugin branchable ».
- **`agents/base_agent.py`** — classe mère : appels API (avec suivi des tokens), lecture/écriture JSON scopée projet, logs par agent, modèle et raisonnement configurables par agent.
- **`utils/cleaners.py`** — nettoyage des sorties du modèle, parsing JSON défensif, sérialisation compacte pour les prompts.
- **`main.py`** — CLI + registre d'agents + dispatch piloté par le plan de l'orchestrateur.
