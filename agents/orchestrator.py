from __future__ import annotations
import json
import typer
from agents.base_agent import BaseAgent
from utils.project import Project


class OrchestratorAgent(BaseAgent):
    """Chef de brigade — lit le brief et coordonne les agents."""

    def __init__(self, project: Project):
        super().__init__(
            name="orchestrator",
            role="Chef de projet — analyse le brief et planifie les tâches",
            project=project
        )

    def run(self, context: dict) -> dict:
        """Lit le brief et produit un plan de travail pour les autres agents."""

        typer.echo("🎯 Orchestrateur : lecture du brief...")

        brief_text = self.read_text("brief.md")
        config = self.read_json("config.json")

        system_prompt = """Tu es un chef de projet web expert.
Tu reçois un brief client et tu produis un plan de travail structuré.
Réponds UNIQUEMENT en JSON valide, sans texte avant ou après, sans balises markdown, sans ```json.

Agents disponibles — tu décides lesquels inclure et dans quel ordre selon le projet :
- copywriter : rédige tous les textes du site à partir des sections définies dans le brief
- designer   : génère le CSS, l'HTML (basé sur le CSS) et le JS du site
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
    "ambiance": "...",
    "couleurs": [],
    "typographie": "..."
  }
}"""

        user_message = f"""Voici le brief client (en langage naturel) :
{brief_text}

Voici la configuration technique du projet :
{json.dumps(config, ensure_ascii=False, indent=2)}

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
