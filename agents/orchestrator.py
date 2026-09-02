from __future__ import annotations
import typer
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import compact_json


# LES AGENTS D'EXÉCUTION, décrits comme des données et non comme une prose
# figée dans le prompt. C'est ce qui permet à deux pipelines différents de
# partager cet agent sans que l'un annonce au modèle des agents que l'autre
# n'a pas. Un plan qui prévoit un agent inexistant n'échoue pas : il est
# ignoré en silence, et personne ne comprend pourquoi l'étape n'a rien fait.
AGENTS_V1 = [
    {
        "nom": "copywriter", "priorite": 1,
        "role": "rédige tous les textes du site à partir des sections définies dans le brief",
        "quand": "toujours, pour un site vitrine",
    },
    {
        "nom": "designer", "priorite": 2,
        "role": "génère le CSS, l'HTML et le JS du site en une seule requête cohérente",
        "quand": "toujours, pour un site vitrine",
    },
    {
        "nom": "seo", "priorite": 3,
        "role": "génère title, meta description, Open Graph, Schema.org, robots.txt, sitemap.xml",
        "quand": "si le brief mentionne le référencement, une zone géographique ou une visibilité locale",
    },
]


def bloc_agents(agents: list[dict]) -> str:
    """La section du prompt qui décrit les agents réellement disponibles."""
    lignes = [
        "Agents disponibles. Tu décides lesquels inclure, selon le projet :",
        *(f"- {a['nom']} : {a['role']}" for a in agents),
        "",
        "Règles de décision, et priorité à donner à chacun :",
        *(f"- {a['nom']} (priorité {a['priorite']}) : {a['quand']}" for a in agents),
        "",
        "N'inscris AUCUN agent absent de cette liste : il serait ignoré sans "
        "que rien ne le signale.",
    ]
    return "\n".join(lignes)


class OrchestratorAgent(BaseAgent):
    """Chef de brigade, lit le brief et coordonne les agents."""

    # PLUS une tâche mécanique depuis que le plan porte la maquette : c'est
    # l'orchestrateur qui transcrit la structure décrite dans brief.md en
    # instruction exploitable par le designer. Si cette transcription est
    # approximative, tout le rendu en pâtit — Haiku était trop juste ici.
    MODEL = "claude-sonnet-5"
    THINKING = {"type": "adaptive"}
    EFFORT = "high"

    def __init__(self, project: Project):
        super().__init__(
            name="orchestrator",
            role="Chef de projet, analyse le brief et planifie les tâches",
            project=project
        )

    def _bloc_contexte_ingestion(self) -> str:
        """Formate le contexte d'ingestion en bloc prêt à injecter dans le prompt.

        Retourne une chaîne vide si l'ingestion n'a rien produit, ainsi
        l'orchestrateur fonctionne à l'identique quand data/ est absent.
        (La lecture défensive vit dans BaseAgent.lire_contexte_ingestion.)
        """
        ctx = self.lire_contexte_ingestion()
        if not ctx:
            return ""

        digest = {
            "resume": ctx.get("resume", ""),
            "themes_couverts": list(ctx.get("contenu_par_theme", {}).keys()),
            "manques": ctx.get("manques", []),
        }
        self.logger.info(
            f"Contexte d'ingestion injecté, {len(digest['themes_couverts'])} thème(s), "
            f"{len(digest['manques'])} manque(s)"
        )
        return (
            "\nDonnées client déjà digérées par l'agent Ingestion "
            "(à utiliser pour calibrer le plan, PAS pour inventer) :\n"
            + compact_json(digest)
            + "\n"
        )

    def run(self, context: dict) -> dict:
        """Lit le brief et produit un plan de travail pour les autres agents.

        `context["agents_disponibles"]` décrit les agents du pipeline qui
        appelle. Absent, on retombe sur ceux de la V1 : la commande `generate`
        se comporte donc exactement comme avant.
        """
        typer.echo("🎯 Orchestrateur : lecture du brief...")
        agents = context.get("agents_disponibles") or AGENTS_V1

        brief_text = self.read_text("brief.md")
        config = self.load_config()
        contexte_client = self._bloc_contexte_ingestion()

        system_prompt = """Tu es un chef de projet web expert.
Tu reçois un brief client et tu produis un plan de travail structuré.
Un agent d'ingestion a parfois déjà digéré les données réelles du client
(textes fournis, thèmes disponibles, manques) : sers-t'en pour calibrer les
instructions des agents et le style_guide, sans jamais inventer de contenu absent.
Réponds UNIQUEMENT en JSON valide, sans texte avant ou après, sans balises markdown, sans ```json.

""" + bloc_agents(agents) + """

L'INSTRUCTION QUE TU ÉCRIS POUR CHAQUE AGENT EST TRANSMISE TELLE QUELLE. Celle
de l'agent qui produit le site porte la maquette : ordre des blocs, colonnes,
contraintes de mise en page. Transcris fidèlement ce que décrit le brief, sans
résumer et sans ajouter. C'est le seul chemin par lequel la structure voulue
par le client atteint la génération.

Le JSON doit avoir cette structure exacte :
{
  "projet": "nom du projet",
  "taches": [
    {
      "agent": "copywriter",
      "priorite": 1,
      "instruction": "instruction précise pour cet agent"
    }
  ],
  "style_guide": {
    "ambiance": "description courte de l'ambiance visuelle",
    "couleurs": {
      "primaire": "#xxxxxx",
      "secondaire": "#xxxxxx",
      "accent": "#xxxxxx",
      "texte": "#xxxxxx",
      "fond": "#xxxxxx"
    },
    "fonts": {
      "heading": "Nom exact d'une Google Font pour les titres (ex: Playfair Display, Cormorant Garamond, Raleway)",
      "body": "Nom exact d'une Google Font pour le corps (ex: Lato, Inter, Source Sans 3)"
    }
  }
}

Règles pour le style_guide :
- couleurs : choisir des hex cohérents avec l'ambiance du brief, contrastes WCAG AA respectés
- fonts.heading : police avec personnalité (serif, display ou sans-serif distinctif selon l'ambiance)
- fonts.body : police lisible, poids variés disponibles sur Google Fonts"""

        user_message = f"""Voici le brief client (en langage naturel) :
{brief_text}

Voici la configuration technique du projet :
{compact_json(config)}
{contexte_client}
Décide quels agents lancer et produis le plan de travail."""

        self.logger.info("Génération du plan de travail...")
        response = self.call_claude(system_prompt, user_message)

        plan = self.parse_json_response(response)

        required = {"projet", "taches", "style_guide"}
        missing = required - set(plan.keys())
        if missing:
            raise ValueError(f"Plan invalide, clés manquantes : {missing}")
        if not isinstance(plan.get("taches"), list) or not plan["taches"]:
            raise ValueError("Plan invalide, 'taches' doit être une liste non vide")
        # Valide aussi chaque tâche : un champ absent ici donnerait un KeyError
        # cryptique plus loin (tri par priorité, dispatch, copywriter).
        for i, tache in enumerate(plan["taches"]):
            manquants = {"agent", "priorite", "instruction"} - set(tache)
            if manquants:
                raise ValueError(f"Plan invalide, tâche {i} sans champ(s) : {manquants}")

        self.write_json("temp/plan.json", plan)
        typer.echo(f"✅ Plan de travail généré → {self.project.temp_dir}/plan.json")

        return plan
