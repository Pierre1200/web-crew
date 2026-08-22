# web-crew

**Une brigade d'agents IA qui génère des sites vitrines statiques, du brief client au site livré.**

`web-crew` est un pipeline multi-agents en Python, inspiré de l'organisation d'une brigade de cuisine : chaque agent a un rôle précis, et un orchestrateur coordonne le tout. On ne touche jamais au code — on « branche » le crew sur un dossier client contenant un brief et une config, et il produit un site complet (HTML/CSS/JS), optimisé SEO et validé.

---

## Fonctionnement

```
   data/ client (docx, pdf, images…)
        │
        ▼
  ┌─────────────┐   context.json
  │  INGESTION  │──────────────┐   digère et structure les données brutes
  └─────────────┘              │
                               ▼
 brief.md + config.json → ┌──────────────┐   plan.json
                          │ ORCHESTRATEUR│─────────────┐   décide quels agents lancer
                          └──────────────┘             │
                                                       ▼
                                                ┌──────────────┐   textes.json
                                                │  COPYWRITER  │──────────────┐   rédige les textes
                                                └──────────────┘              │
                                                                              ▼
                                                                     ┌──────────────┐   index.html
                                                                     │   DESIGNER   │   style.css
                                                                     └──────────────┘   main.js
                                                                              │
                                                              ┌───────────────┴───────────────┐
                                                              ▼                                ▼
                                                       ┌─────────────┐                  ┌──────────┐
                                                       │  VALIDATEUR │  (0 token)       │   SEO    │
                                                       └─────────────┘  boucle          └──────────┘
                                                       correction auto                   meta + sitemap
```

L'orchestrateur lit le brief en langage naturel et décide **dynamiquement** quels agents mobiliser et dans quel ordre. Ajouter un agent au registre suffit pour qu'il puisse être planifié — aucun chemin ni séquence en dur.

---

## La brigade

Chaque agent tourne sur le modèle et la profondeur de raisonnement adaptés à sa tâche — un arbitrage **qualité / coût** assumé : les modèles les plus puissants là où la valeur se joue (contenu, design), les plus économiques sur les tâches mécaniques à schéma fixe.

| Agent | Rôle | Modèle | Raisonnement | Effort |
|---|---|---|---|---|
| **Ingestion** | Digère les données client brutes (docx/pdf/images) en contexte structuré | Sonnet 5 | ✅ | high |
| **Orchestrateur** | Lit le brief, transcrit la maquette, produit le plan de travail | Sonnet 5 | ✅ | high |
| **Copywriter** | Rédige tous les textes du site à partir du contenu réel | Opus 5 | ✅ | high |
| **Designer** | Génère HTML + CSS + JS cohérents en une passe | Opus 5 | ✅ | **xhigh** |
| **Validateur** | Contrôle qualité pur Python (HTML complet, classes cohérentes, médias…) | — *(0 token)* | — | — |
| **Critique** | Contrôle du fond des textes : faits inventés, sections creuses, générique | Sonnet 5 | ✅ | high |
| **SEO** | Métadonnées, Open Graph, Schema.org, sitemap, robots.txt | Haiku 4.5 | — | — |

`effort` (`low` → `max`) règle la profondeur de travail du modèle : c'est le principal levier qualité/coût. Le designer tourne en `xhigh`, le réglage le plus adapté aux tâches de code. **Haiku 4.5 refuse `effort` et le raisonnement adaptatif** — d'où `EFFORT = None` et `THINKING = None` sur l'agent SEO.

L'extraction de texte, le catalogage d'images et toute la validation sont réalisés en **Python pur, sans appel IA** — les tokens ne sont dépensés que là où l'intelligence apporte réellement quelque chose.

---

## Installation

```bash
git clone <url-du-repo>
cd web-crew

python3 -m venv .venv              # Python 3.12+ recommandé
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

---

## Utilisation

```bash
# Pipeline complet : ingestion → orchestrateur → copywriter → designer
python3 main.py generate --project mon-client

# Pipeline + boucle de validation/correction automatique
python3 main.py generate-safe --project mon-client

# Étapes isolées (économise des tokens)
python3 main.py ingest       --project mon-client   # digère data/ uniquement
python3 main.py design-only  --project mon-client   # relance le designer seul
python3 main.py validate     --project mon-client   # validateur seul (0 token)
python3 main.py critique     --project mon-client   # contrôle du fond des textes (1 appel Haiku)
python3 main.py seo-only     --project mon-client   # métadonnées SEO seules

python3 main.py list-agents                          # agents du registre
```

Prévisualiser le site généré :

```bash
cd projects/mon-client/output && python3 -m http.server 8080
# → http://localhost:8080
```

---

## Structure d'un projet client

Le code est un **plugin** : il ne change jamais. Chaque client est un dossier autonome.

```
projects/mon-client/
├── brief.md        # le cahier des charges en langage naturel
├── config.json     # config technique (sections, style, SEO, client)
├── data/           # données brutes fournies par le client (docx, pdf, images)
├── output/         # site généré (HTML/CSS/JS)                    ← non versionné
├── temp/           # fichiers d'échange inter-agents              ← non versionné
└── logs/           # un log par agent, avec suivi des tokens      ← non versionné
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

1. Créer `agents/mon_agent.py` héritant de `BaseAgent`
2. L'ajouter à `AGENT_REGISTRY` dans `main.py`
3. Le présenter dans le system prompt de l'orchestrateur

Le pipeline le mobilisera automatiquement selon le brief.

---

## Stack technique

- **Python 3** — Typer (CLI), python-dotenv
- **API Claude** (SDK `anthropic`) — Haiku 4.5 / Sonnet 4.6 / Opus 4.8 selon l'agent, raisonnement adaptatif
- **Extraction** — pypdf, python-docx
- **Sortie** — HTML5, CSS3, JavaScript vanilla (zéro dépendance front)

---

## Architecture en bref

- **`utils/project.py`** — la classe `Project` calcule tous les chemins depuis le seul nom du client. Pièce centrale du modèle « plugin branchable ».
- **`agents/base_agent.py`** — classe mère : appels API (avec suivi des tokens), lecture/écriture JSON scopée projet, logs par agent, modèle et raisonnement configurables par agent.
- **`utils/cleaners.py`** — nettoyage des sorties du modèle, parsing JSON défensif, sérialisation compacte pour les prompts.
- **`main.py`** — CLI + registre d'agents + dispatch piloté par le plan de l'orchestrateur.
