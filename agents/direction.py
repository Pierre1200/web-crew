"""
Agent Direction artistique — décide de la composition AVANT d'écrire du code.

Le problème qu'il résout : jusqu'ici, le seul cadrage visuel transmis au
designer était `style_guide` (cinq couleurs et deux polices). Tout le reste —
archétype de mise en page, échelle d'espacement, rythme des sections,
traitement des surfaces, politique de mouvement — était décidé implicitement
par le designer, au milieu de la génération de 25 000 tokens de code. C'est le
pire moment pour faire des choix de composition : le modèle est occupé à
intégrer.

Cet agent sépare les deux gestes, comme dans un vrai studio : on arrête une
direction, ensuite on l'exécute. Il produit `temp/direction.json`, un petit
document de décisions CONCRÈTES (des valeurs, pas des conseils) que le designer
applique et que la critique visuelle vérifie.

Coût : une petite sortie JSON, ~0,15 $ — la décision la plus structurante du
pipeline pour un dixième du prix de la génération qu'elle oriente.
"""
from __future__ import annotations
import typer

from agents.base_agent import BaseAgent
from utils.cleaners import compact_json

# Vocabulaire de mises en page. Nommer les options force un choix explicite :
# sans cette liste, le modèle retombe toujours sur la vitrine sectionnée.
ARCHETYPES = {
    "editorial-asymetrique":
        "deux colonnes inégales, lecture verticale, rythme de magazine",
    "cinematique-plein-ecran":
        "grandes images, texte rare et fort, sections qui occupent l'écran",
    "galerie-grille":
        "la grille d'images EST la structure ; le texte s'y insère",
    "document-centre":
        "une seule colonne étroite, typographie dominante, esprit imprimé",
    "panneau-fixe":
        "une colonne fixe (identité, navigation) et une colonne qui défile",
    "vitrine-sectionnee":
        "sections empilées contrastées — le classique, à ne choisir que s'il "
        "est réellement le plus juste pour ce client",
}

CLES_ATTENDUES = {
    "archetype", "intention", "palette", "typographie",
    "espacement", "surfaces", "mouvement", "signature",
}


class DirectionAgent(BaseAgent):
    """Arrête une direction artistique propre au projet, avant toute écriture de code."""

    # Décision la plus structurante du pipeline, pour une sortie minuscule :
    # c'est exactement là qu'il faut mettre le meilleur modèle et l'effort
    # maximal. Le surcoût est de l'ordre de quelques centimes.
    MODEL = "claude-opus-5"
    EFFORT = "xhigh"

    def __init__(self, project):
        super().__init__(
            name="direction",
            role="Direction artistique — arrête la composition du site",
            project=project,
        )

    def _prompt_systeme(self) -> str:
        archetypes = "\n".join(f"- {nom} : {desc}" for nom, desc in ARCHETYPES.items())
        return f"""Tu es directeur artistique. On te confie un projet de site \
et tu arrêtes sa direction visuelle AVANT que la moindre ligne de code soit écrite.

Tu ne donnes pas des conseils, tu prends des DÉCISIONS : des valeurs précises, \
chiffrées, directement applicables. « Varier le rythme vertical » est un conseil \
inutile ; « hero 160px, à propos 64px, galerie 96px » est une décision.

Choisis l'archétype de mise en page parmi ceux-ci, celui qui sert le mieux CE \
client — pas celui qui rassure :
{archetypes}

Exigences :
- La palette est exprimée en oklch() et les variantes sont dérivées par \
color-mix(in oklab, …) : un système tonal cohérent, pas une liste de couleurs \
sans lien. Respecte les couleurs voulues par le client, mais convertis-les et \
construis leurs déclinaisons (surfaces, survols, bordures, ombres).
- L'échelle d'espacement a des sauts francs, pas une suite de multiples de 1rem.
- Le rythme des sections est décrit section par section, avec des valeurs.
- La « signature » doit nommer ce qui, dans ce site, ne pourrait appartenir à \
aucun autre client. Si ta réponse pourrait décrire le site d'un plombier comme \
celui d'une galerie d'art, elle est ratée : recommence.
- Les pièges à éviter sont PROPRES à ce projet, pas des généralités.

Réponds UNIQUEMENT en JSON valide, sans balise markdown."""

    def _prompt_utilisateur(self, plan: dict) -> str:
        config = self.load_config()
        brief = ""
        try:
            brief = self.read_text("brief.md")
        except OSError:
            self.logger.warning("brief.md illisible — direction fondée sur config.json")

        contexte = self.lire_contexte_ingestion()
        bloc_contexte = ""
        if contexte.get("resume"):
            bloc_contexte = (
                f"\nCe que le client a réellement fourni (résumé de l'ingestion) :\n"
                f"{contexte['resume']}\n"
            )

        style_guide = plan.get("style_guide", {})
        polices = style_guide.get("fonts", {})

        return f"""Voici le brief du client :
{brief}

Configuration technique du projet :
{compact_json(config)}

Cadrage déjà décidé par le chef de projet (point de départ, à affiner) :
{compact_json(style_guide)}
{bloc_contexte}
Les familles de polices sont DÉJÀ arrêtées et ne doivent pas changer \
(elles sont chargées ailleurs dans la chaîne) : {compact_json(polices)}.
Tu décides en revanche de leur emploi : graisses, interlettrage, casse, échelle.

Produis un JSON avec exactement cette structure :
{{
  "archetype": "<un des archétypes proposés>",
  "intention": "<2 phrases : l'effet visé sur le visiteur, ancré dans le métier du client>",
  "palette": {{
    "variables": {{"--fond": "oklch(...)", "--texte": "oklch(...)", "--accent": "oklch(...)", "--secondaire": "oklch(...)"}},
    "derivations": ["--surface: color-mix(in oklab, var(--fond) 92%, var(--texte));", "..."],
    "usage_accent": "<où l'accent apparaît, et où il n'apparaît JAMAIS>"
  }},
  "typographie": {{
    "titres": {{"graisse": 700, "interlettrage": "-0.02em", "casse": "none", "interligne": 1.05}},
    "corps": {{"graisse": 400, "interligne": 1.65}},
    "echelle": {{"h1": "clamp(...)", "h2": "clamp(...)", "h3": "clamp(...)", "corps": "clamp(...)"}},
    "mesure": "<largeur de lecture max, ex: 62ch>"
  }},
  "espacement": {{
    "echelle": [4, 8, 16, 24, 40, 64, 96, 160],
    "rythme_sections": {{"<nom de section>": "<valeur et justification en quelques mots>"}}
  }},
  "surfaces": {{
    "traitement": "<comment naissent la matière et la profondeur>",
    "bordures": "<épaisseur, couleur, où>",
    "ombres": "<ou 'aucune' si le parti pris s'en passe>",
    "arrondis": "<valeur>"
  }},
  "mouvement": {{
    "politique": "<ce qui bouge et ce qui ne bouge surtout pas>",
    "elements_animes": ["<liste courte et fermée>"]
  }},
  "signature": "<ce qui rend ce site reconnaissable entre tous — 1 à 2 phrases>",
  "pieges_a_eviter": ["<propres à CE projet>"]
}}"""

    def run(self, context: dict) -> dict:
        typer.echo("🎨 Direction artistique : choix de composition...")

        try:
            plan = self.read_json("temp/plan.json")
        except (OSError, ValueError):
            plan = {}
            self.logger.warning("plan.json illisible — direction sans cadrage préalable")

        reponse = self.call_claude(
            self._prompt_systeme(), self._prompt_utilisateur(plan), max_tokens=16000
        )
        direction = self.parse_json_response(reponse)

        manquantes = CLES_ATTENDUES - set(direction)
        if manquantes:
            raise ValueError(
                f"Direction artistique invalide — clés manquantes : {sorted(manquantes)}"
            )

        archetype = direction.get("archetype", "")
        if archetype not in ARCHETYPES:
            # Non bloquant : un archétype inventé reste exploitable par le
            # designer, mais on le signale pour ne pas le découvrir au rendu.
            self.logger.warning(f"Archétype hors liste : {archetype!r}")
            typer.echo(f"   ⚠️  Archétype non répertorié : {archetype!r}")

        self.write_json("temp/direction.json", direction)
        typer.echo(f"   → Archétype retenu : {archetype}")
        if direction.get("signature"):
            typer.echo(f"   ✍️  Signature : {direction['signature']}")
        self.logger.info(f"Direction artistique arrêtée — archétype {archetype!r}")

        return direction
