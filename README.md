# web-crew

Générateur de sites vitrines statiques piloté par une équipe d'agents IA.
On ne touche pas au code : on le branche sur un dossier client contenant un
brief et une configuration, et il produit un site HTML/CSS/JS complet, validé,
optimisé et durci.

```
  ENTRÉES      brief.md  ·  config.json  ·  data/ (docx, pdf, images, textes)
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  CADRAGE      INGESTION ──────────────▶  temp/context.json
  ~0,20 $      ORCHESTRATEUR ──────────▶  temp/plan.json
               DIRECTION ARTISTIQUE ───▶  temp/direction.json
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  PRODUCTION   COPYWRITER ───────────▶  temp/textes.json
  ~1,30 $      DESIGNER ─────────────▶  index.html · style.css · main.js
               PAGES ────────────────▶  collections (1 appel, quel que soit N)
               SEO ──────────────────▶  balises · sitemap.xml · robots.txt
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  CONTRÔLE     VALIDATEUR ──────────▶  structure, liens, médias   (0 token)
               CRITIQUE ────────────▶  fond des textes
               CRITIQUE VISUELLE ───▶  rendu réel, en images      (~0,15 $)
                                    │
  ══════════════════════════════════▼══════════════════════════════════════
  LIVRAISON    SÉCURITÉ ────────────▶  durcissement · SECURITE.md  (0 token)
```

Chaque étape écrit son résultat sur le disque et reste rejouable seule : on ne
repaie jamais une phase pour en corriger une autre.

---

## Installation

```bash
python3 -m venv .venv              # Python 3.12+ requis
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

La critique visuelle a besoin d'un navigateur, à télécharger une seule fois
(~150 Mo) :

```bash
playwright install chromium
```

Sans lui, tout le reste fonctionne. Seule la commande `visuel` s'arrête, avec
un message indiquant quoi lancer.

Vérification :

```bash
python3 -m pytest tests/ -q       # 196 tests, aucun appel API, aucune clé requise
```

---

## Commandes

| Commande | Effet | Coût |
|---|---|---|
| `generate -p X` | Pipeline complet | ~1,50 $ |
| `generate-safe -p X --visuel 2` | Pipeline, correction auto, critique visuelle | ~3 $ |
| `ingest -p X [--force]` | Digère `data/` seul | ~0,10 $ |
| `direction -p X [--archetype …]` | Rejoue la direction artistique | ~0,40 $ |
| `design-only -p X [--replan]` | Redessine le site | ~1,20 $ |
| `pages -p X [--gabarits]` | (Re)génère les collections | 0 sans `--gabarits` |
| `seo-only -p X` | Métadonnées et sitemap | ~0,01 $ |
| `critique -p X` | Contrôle le fond des textes | ~0,09 $ |
| `visuel -p X [--corriger] [--tours N]` | Juge le rendu, applique les correctifs | ~0,15 $/passe |
| `securiser -p X [--durcir] [--injection]` | Audit, durcissement, rapport | 0 (ou ~0,11 $) |
| `validate -p X` | Contrôle structurel | 0 |
| `diff -p X` | Ce que le dernier run a changé | 0 |
| `restore -p X` | Annule le dernier run | 0 |
| `list-agents` | Agents du registre | 0 |

Prévisualiser :

```bash
cd projects/mon-client/output && python3 -m http.server 8080
```

### Itérer sans se ruiner

Le designer représente environ 40 % de la facture. Pour retravailler un rendu,
ne relancez pas `generate` :

```bash
python3 main.py direction   -p mon-client --archetype galerie-grille   # 0,40 $
python3 main.py design-only -p mon-client                              # 1,20 $
```

Si seul un détail visuel cloche, `visuel --corriger` coûte 0,15 $ et applique
les correctifs CSS sans rien régénérer.

> `design-only` sans `--replan` rejoue l'ancien plan. Après toute modification
> de `brief.md` ou `config.json`, `--replan` rafraîchit le cadrage pour quelques
> centimes. Sans lui, vous payez une génération qui reproduit l'ancienne maquette.

---

## Structure d'un projet

```
projects/mon-client/
├── brief.md        # le cahier des charges en langage naturel
├── config.json     # sections, style, SEO, collections, médias
├── data/           # documents et photos fournis par le client
│   ├── articles/   # un .txt par page de collection
│   └── images-extraites/   # photos sorties des .docx et .pdf (généré)
├── output/         # le site généré, JETABLE          ← non versionné
├── output_prev/    # sauvegarde du run précédent      ← non versionné
├── temp/           # échanges entre agents            ← non versionné
└── logs/           # un log par agent, plus les captures ← non versionné
```

### `output/` est jetable

Chaque génération l'écrase. Toute correction faite à la main dedans disparaît au
run suivant : la valeur doit remonter dans `brief.md` ou `config.json`. Un
branchement Formspree posé à la main dans le HTML, par exemple, doit devenir
`site.formspree_id` dans la configuration.

Deux filets protègent les runs payants. Avant chaque génération, `output/` est
copié dans `output_prev/` : `diff` montre ce qui a changé, `restore` revient en
arrière. Et un contrôle de pré-vol signale, avant toute dépense, un branchement
présent dans le site mais absent de la configuration.

---

## `config.json`

```json
{
  "client": { "nom": "…", "localisation": "…", "contact_principal": "…" },
  "site": {
    "sections": ["Hero : accroche", "À propos", "Services", "Contact"],
    "style": { "ambiance": "…", "couleurs_suggérées": ["…"], "typographie": "…" },
    "formspree_id": "",
    "url": "https://exemple.fr",
    "collections": [
      { "id": "blog", "titre": "Le blog", "source": "articles", "flux": true }
    ],
    "medias": {
      "titre_section": "Les vidéos",
      "items": [{ "titre": "…", "url": "https://youtu.be/XXXXXXXXXXX" }]
    }
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

| Champ | Rôle |
|---|---|
| `site.sections` | Structure imposée au designer, dans cet ordre |
| `site.style` | Point de départ de la direction artistique |
| `site.formspree_id` | Les 8 caractères après `/f/` dans l'URL [Formspree](https://formspree.io). Vide : le JS affiche un message honnête au lieu d'un faux « message envoyé » |
| `site.url` | Domaine, pour les URL absolues du sitemap et des flux |
| `site.collections` | Voir [Collections](#collections) |
| `site.medias` | Voir [Médias](#médias) |
| `_note…` | Toute clé commençant par `_note`, sous `site` ou `site.style`, est une consigne transmise telle quelle au designer |

Exemple de consignes :

```json
"_note_sections":   "Corps en deux colonnes : gauche étroite, droite large.",
"_note_formulaire": "PAS de formulaire de contact, un simple lien mailto."
```

---

## Collections

Un site peut porter des ensembles de pages produites à partir de textes écrits
par le client : blog, réalisations, fiches services, actualités. Le client dépose
ses textes dans `data/<source>/`, un fichier `.txt` par page.

```
Titre: D'où vient le nom de l'atelier ?
Chapo: Une histoire de famille, et un mot inventé sur place.
Date: 2026-08-14
Couverture: atelier.jpg
Statut: publie

Le premier atelier a ouvert rue des Lilas, dans un ancien entrepôt.

## Les débuts

Trois personnes, deux établis, et beaucoup de patience.

> On ne savait pas encore ce qu'on faisait, mais on le faisait bien.
```

Ce n'est pas du Markdown, volontairement. Une ligne vide sépare deux paragraphes,
`## ` ouvre un sous-titre, `> ` une citation. Le client n'a aucune syntaxe à
apprendre, et comme le crew n'insère jamais de HTML écrit par lui (tout est
échappé avant insertion), l'injection est impossible par construction.

Le format est permissif : sans en-tête, le titre vient du nom du fichier et la
date de sa dernière modification. `Statut: brouillon` garde une page hors ligne.

**Le coût ne dépend pas du nombre de pages.** Le modèle produit un jeu de
gabarits par collection (page de liste, page de contenu, balisage des
paragraphes, sous-titres, citations et images) que Python remplit ensuite pour
chaque texte. Cinquante articles coûtent un seul appel.

Les gabarits sont mis en cache dans `temp/`. Corriger une faute et régénérer est
gratuit :

```bash
python3 main.py pages -p mon-client              # gratuit
python3 main.py pages -p mon-client --gabarits   # redessine les gabarits
```

Chaque collection reçoit un flux RSS, et le `sitemap.xml` est recalculé pour
lister toutes les pages.

---

## Médias

Le champ `site.medias` déclare des lecteurs vidéo ou audio. Il suffit de coller
l'URL publique : le fournisseur est reconnu et l'URL d'intégration construite en
Python, sans qu'aucun format soit inventé par un modèle.

Fournisseurs reconnus : YouTube (en `youtube-nocookie`), Vimeo, Dailymotion,
PeerTube, Spotify, SoundCloud, Deezer.

Les vidéos gardent leurs proportions via `aspect-ratio`, les lecteurs audio leur
hauteur propre, et tous les iframes sont en `loading="lazy"`. La mise en page de
la galerie suit le brief. Le validateur vérifie que chaque média déclaré est
présent dans le HTML livré.

Pour ajouter un fournisseur : une entrée dans `_FOURNISSEURS`
([utils/embeds.py](utils/embeds.py)).

---

## Images

### Photos piégées dans les documents

Les clients joignent rarement leurs photos : ils les collent dans un document
Word. Un `.docx` de 380 Ko peut ne contenir que 379 caractères de texte et quatre
photos, invisibles pour qui ne lit que les paragraphes.

L'ingestion ouvre donc les `.docx` et les `.pdf`, en sort les images et les
dépose dans `data/images-extraites/` sous un nom dérivé du document. Elles
rejoignent ensuite le flux normal : catalogue, suggestion d'emplacement, copie
vers `output/assets/`.

Deux filtrages, parce qu'un document contient autre chose que des photos. Les
artefacts de mise en page sont écartés (moins de 5 Ko, ou moins de 120 px de
côté : filets, puces, images d'espacement), ainsi que les fichiers `.wdp` que
Word range à côté des PNG. Les doublons le sont aussi, par empreinte du contenu :
un logo présent dans chaque document ne serait sinon proposé cinq fois.

### Toutes les images

Tout fichier image de `data/` est copié dans `output/assets/` sous un nom
compatible URL, et ses dimensions réelles sont lues en décodant l'en-tête du
fichier (PNG, JPEG, GIF, WebP, SVG), en Python pur, sans dépendance.

Le designer reçoit un manifeste (chemin, dimensions, ratio, orientation, poids)
et doit s'en servir en priorité. Les images de remplissage ne sont tolérées que
là où aucune photo du client ne convient.

Sans `width` et `height` sur une balise `<img>`, le navigateur ne connaît la
place à réserver qu'une fois l'image chargée et la page saute pendant le
chargement. C'est le défaut le plus visible d'un site amateur, et il se corrige
avec deux attributs.

Contrôles du validateur : `ressource_cassee` (fichier référencé mais absent),
`image_inutilisee` (photo fournie jamais affichée), `placeholder_en_production`.

---

## Direction artistique

Avant qu'une ligne de code soit écrite, un agent arrête la composition du site
et l'écrit dans `temp/direction.json` : archétype de mise en page, palette en
`oklch` avec ses dérivations, échelle typographique, rythme section par section,
traitement des surfaces, politique de mouvement, et une signature (ce qui rend
ce site reconnaissable entre tous).

L'archétype est choisi dans un vocabulaire fermé, ce qui force un parti pris :

| Archétype | Parti pris |
|---|---|
| `editorial-asymetrique` | Deux colonnes inégales, rythme de magazine |
| `cinematique-plein-ecran` | Grandes images, texte rare et fort |
| `galerie-grille` | La grille d'images est la structure |
| `document-centre` | Une colonne étroite, typographie dominante |
| `panneau-fixe` | Une colonne fixe, une colonne qui défile |
| `vitrine-sectionnee` | Le classique, à ne choisir que s'il est le plus juste |

Ces décisions remplacent les principes génériques dans le prompt du designer, et
servent de référence à la critique visuelle, qui juge l'écart entre ce qui était
annoncé et ce qui est rendu.

---

## CSS moderne

Les sites livrés sont en HTML/CSS/JS statique. C'est un choix : hébergement
gratuit, chargement instantané, aucune dépendance à maintenir, et un livrable que
le client peut déposer où il veut. La modernité est allée dans le CSS.

| Outil | Apport |
|---|---|
| `@layer` | Feuille rangée en couches, et les correctifs visuels écrits hors couche l'emportent sans `!important` |
| Container queries | Un composant s'adapte à la largeur de son conteneur, pas de l'écran |
| `:has()` | Mise en page qui réagit au contenu réel |
| `oklch()` + `color-mix()` | Système tonal dérivé de 3 ou 4 couleurs |
| `subgrid` | Titres et boutons alignés d'une carte à l'autre |
| `text-wrap: balance` / `pretty` | Plus de lignes veuves ni de coupures disgracieuses |
| Propriétés logiques | `margin-inline`, `padding-block`, `inset` |
| `animation-timeline: view()` | Révélation au défilement sans JavaScript, sous `@supports` |

Le premier point est structurant. Sans couches, un correctif `.hero{…}` ajouté en
fin de feuille ne bat pas un `.section .hero{…}` existant, plus spécifique : la
correction automatique deviendrait un coup de dés.

---

## Critique visuelle

Le validateur prouve que le HTML est valide, jamais qu'il est beau. La commande
`visuel` photographie le site rendu à trois largeurs (mobile 390 px, tablette
820 px, bureau 1440 px) et soumet les images à un directeur artistique qui juge
la conformité à la maquette, la composition, la typographie, les contrastes et le
comportement responsive.

Le verdict arrive dans `temp/critique_visuelle.json`, les captures dans
`logs/captures/`. Seule la critique coûte des tokens : les correctifs CSS qu'elle
rédige sont appliqués mécaniquement, sans nouvel appel.

---

## Sécurité

Un site statique a une surface d'attaque réduite : pas de serveur applicatif, pas
de base de données, pas de dépendances à patcher, pas de comptes utilisateurs.
Les vrais sujets sont les services tiers, le durcissement absent et les secrets
oubliés.

Le durcissement est une commande séparée, à lancer quand le rendu convient : il
modifie le site généré.

| Action | Raison |
|---|---|
| Polices hébergées sur le site | Sans cela, chaque visiteur transmet son adresse IP à Google. Rapatrier les fichiers supprime le transfert, la dépendance au CDN et deux connexions au chargement |
| `_headers` et `.htaccess` | En-têtes pour Netlify/Cloudflare et Apache, avec une CSP calculée depuis le site réel |
| `rel="noopener noreferrer"` | Une page ouverte dans un nouvel onglet ne peut plus agir sur celle du site |
| Pot de miel anti-robot | Un champ invisible que seuls les robots remplissent |

L'audit est gratuit et produit `output/SECURITE.md` : le site est livré avec son
audit. Le rapport liste les services extérieurs contactés, ce qui a été durci, et
ce qui reste à la charge du client.

L'option `--injection` ajoute le seul appel au modèle de cet agent : la relecture
des documents de `data/` à la recherche de passages rédigés pour détourner un
automate. Le risque est réel puisque l'ingestion insère ces textes dans les
prompts des autres agents.

---

## Modèles

| Agent | Modèle | Raisonnement | Effort |
|---|---|---|---|
| Ingestion | Sonnet 5 | ✅ | high |
| Orchestrateur | Sonnet 5 | ✅ | high |
| Direction artistique | Opus 5 | ✅ | **xhigh** |
| Copywriter | Opus 5 | ✅ | high |
| Designer | Opus 5 | ✅ | **xhigh** |
| Pages | Opus 5 | ✅ | xhigh |
| SEO | Haiku 4.5 | non | non |
| Validateur | *aucun appel* | non | non |
| Critique | Sonnet 5 | ✅ | high |
| Critique visuelle | Opus 5 | ✅ | **xhigh** |
| Sécurité | Sonnet 5 *(1 appel optionnel)* | ✅ | high |

`effort` (de `low` à `max`) règle la profondeur de travail du modèle. C'est le
principal levier qualité/coût. Haiku 4.5 refuse `effort` et le raisonnement
adaptatif, d'où `EFFORT = None` et `THINKING = None` sur l'agent SEO.

L'extraction de texte et d'images, le catalogage, la validation, le rendu des
collections, l'injection SEO, le durcissement et l'audit sont réalisés en Python
pur. Les tokens ne sont dépensés que là où l'intelligence apporte quelque chose.

---

## Ajouter un agent

Tous les agents héritent de `BaseAgent`, mais il en existe deux familles selon
qui décide de les lancer.

**Agents planifiés.** L'orchestrateur choisit de les mobiliser selon le brief.
Ce sont ceux du registre : copywriter, designer, seo.

1. Créer `agents/mon_agent.py` héritant de `BaseAgent`
2. L'ajouter à `AGENT_REGISTRY` dans `main.py`
3. Le présenter dans le system prompt de l'orchestrateur

**Agents à étape fixe.** Leur place ne se discute pas : ingestion et direction
arrivent avant la production, validateur, critique, critique visuelle et sécurité
après. Ils sont appelés explicitement par `main.py` et exposés en commande.

Le choix tient à une question : l'orchestrateur peut-il légitimement décider de
sauter cette étape ? Si non, elle n'a rien à faire dans le registre.

---

## Stack

- **Python 3.12+**, Typer (CLI), python-dotenv
- **API Claude** (SDK `anthropic`) : Opus 5, Sonnet 5, Haiku 4.5 selon l'agent
- **Playwright** (optionnel) : capture du rendu pour la critique visuelle
- **Extraction** : pypdf, python-docx
- **Sortie** : HTML5, CSS3, JavaScript vanilla, zéro dépendance front

196 tests, exécutables sans clé API.
