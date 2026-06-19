from __future__ import annotations
import json
import typer
from agents.base_agent import BaseAgent

class OrchestratorAgent(BaseAgent):
    """Chef de brigade — lit le brief et coordonne les agents."""

    def __init__(self):
        super().__init__(
            name="orchestrator",
            role="Chef de projet — analyse le brief et planifie les tâches"
        )

    def run(self, context: dict) -> dict:
        """Lit le brief et produit un plan de travail pour les autres agents."""

        typer.echo("🎯 Orchestrateur : lecture du brief...")
        brief = self.read_json("input/brief.json")

        system_prompt = """Tu es un chef de projet web expert.
Tu reçois un brief client en JSON et tu produis un plan de travail structuré.
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

        user_message = f"""Voici le brief client :
{json.dumps(brief, ensure_ascii=False, indent=2)}

Produis le plan de travail pour les agents : copywriter, designer, seo."""

        self.logger.info("Génération du plan de travail...")
        response = self.call_claude(system_prompt, user_message)

        # Nettoyage défensif
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()

        # Parse le JSON nettoyé
        plan = json.loads(clean)

        # Sauvegarde le plan pour les autres agents
        self.write_json("temp/plan.json", plan)
        typer.echo("✅ Plan de travail généré → workspace/temp/plan.json")

        return plan