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

Produis le plan de travail pour les agents : copywriter, designer, seo."""

        self.logger.info("Génération du plan de travail...")
        response = self.call_claude(system_prompt, user_message)

        from utils.cleaners import parse_json_safe
        plan = parse_json_safe(response)

        self.write_json("temp/plan.json", plan)
        typer.echo(f"✅ Plan de travail généré → {self.project.temp_dir}/plan.json")

        return plan
