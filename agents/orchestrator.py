from __future__ import annotations
import typer
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import compact_json


class OrchestratorAgent(BaseAgent):
    """Chef de brigade — lit le brief et coordonne les agents."""

    # Tâche mécanique (produire un plan JSON à schéma fixe) : Haiku 4.5, sans
    # raisonnement. Qualité inchangée, coût divisé.
    MODEL = "claude-haiku-4-5"
    THINKING = None

    def __init__(self, project: Project):
        super().__init__(
            name="orchestrator",
            role="Chef de projet — analyse le brief et planifie les tâches",
            project=project
        )

    def _lire_contexte_ingestion(self) -> str:
        """Relit temp/context.json produit par l'agent Ingestion, s'il existe.

        Retourne un bloc prêt à injecter dans le prompt (résumé, thèmes couverts,
        manques) — ou une chaîne vide si l'ingestion n'a rien produit. Ainsi
        l'orchestrateur fonctionne à l'identique quand data/ est absent.
        """
        context_path = self.project.temp_dir / "context.json"
        if not context_path.exists():
            return ""

        try:
            ctx = self.read_json("temp/context.json")
        except (ValueError, OSError) as e:
            self.logger.warning(f"context.json illisible, ignoré : {e}")
            return ""

        if not ctx or ctx.get("vide"):
            return ""

        digest = {
            "resume": ctx.get("resume", ""),
            "themes_couverts": list(ctx.get("contenu_par_theme", {}).keys()),
            "manques": ctx.get("manques", []),
        }
        self.logger.info(
            f"Contexte d'ingestion injecté — {len(digest['themes_couverts'])} thème(s), "
            f"{len(digest['manques'])} manque(s)"
        )
        return (
            "\nDonnées client déjà digérées par l'agent Ingestion "
            "(à utiliser pour calibrer le plan, PAS pour inventer) :\n"
            + compact_json(digest)
            + "\n"
        )

    def run(self, context: dict) -> dict:
        """Lit le brief et produit un plan de travail pour les autres agents."""

        typer.echo("🎯 Orchestrateur : lecture du brief...")

        brief_text = self.read_text("brief.md")
        config = self.load_config()
        contexte_client = self._lire_contexte_ingestion()

        system_prompt = """Tu es un chef de projet web expert.
Tu reçois un brief client et tu produis un plan de travail structuré.
Un agent d'ingestion a parfois déjà digéré les données réelles du client
(textes fournis, thèmes disponibles, manques) : sers-t'en pour calibrer les
instructions des agents et le style_guide, sans jamais inventer de contenu absent.
Réponds UNIQUEMENT en JSON valide, sans texte avant ou après, sans balises markdown, sans ```json.

Agents disponibles — tu décides lesquels inclure et dans quel ordre selon le projet :
- copywriter : rédige tous les textes du site à partir des sections définies dans le brief
- designer   : génère le CSS, l'HTML et le JS du site en une seule requête cohérente
- seo        : génère title, meta description, Open Graph, Schema.org, robots.txt, sitemap.xml

Règles de décision :
- copywriter (priorité 1) + designer (priorité 2) : toujours pour un site vitrine
- seo (priorité 3) : inclure si le brief mentionne référencement, zone géographique ou visibilité locale

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

        from utils.cleaners import parse_json_safe
        plan = parse_json_safe(response)

        required = {"projet", "taches", "style_guide"}
        missing = required - set(plan.keys())
        if missing:
            raise ValueError(f"Plan invalide — clés manquantes : {missing}")
        if not isinstance(plan.get("taches"), list) or not plan["taches"]:
            raise ValueError("Plan invalide — 'taches' doit être une liste non vide")

        self.write_json("temp/plan.json", plan)
        typer.echo(f"✅ Plan de travail généré → {self.project.temp_dir}/plan.json")

        return plan
