from __future__ import annotations
import json
import typer
from agents.base_agent import BaseAgent
from utils.project import Project


class CopywriterAgent(BaseAgent):
    """Rédige tous les textes du site à partir du plan de l'orchestrateur."""

    def __init__(self, project: Project):
        super().__init__(
            name="copywriter",
            role="Rédacteur — génère tous les textes du site",
            project=project
        )

    def run(self, context: dict) -> dict:
        typer.echo("✍️  Copywriter : rédaction des textes...")

        plan = self.read_json("temp/plan.json")

        instruction = next(
            t["instruction"] for t in plan["taches"]
            if t["agent"] == "copywriter"
        )

        style_guide = plan["style_guide"]

        system_prompt = """Tu es un rédacteur web expert.
Tu rédiges des textes professionnels adaptés au secteur et au ton définis dans le brief.
Réponds UNIQUEMENT en JSON valide, sans balises markdown, sans ```json.
Les textes doivent être immédiatement utilisables sur le site, en français."""

        user_message = f"""Voici ta mission :
{instruction}

Voici le style guide à respecter :
{json.dumps(style_guide, ensure_ascii=False, indent=2)}

Produis un JSON avec cette structure exacte :
{{
  "hero": {{
    "accroche": "phrase principale percutante",
    "sous_titre": "phrase secondaire évocatrice"
  }},
  "a_propos": {{
    "titre": "titre de la section",
    "texte": "texte complet 150-200 mots"
  }},
  "expositions": {{
    "titre_section": "titre",
    "exposition_exemple": {{
      "titre": "titre expo",
      "dates": "dates types",
      "description": "texte 80-100 mots"
    }}
  }},
  "artistes": {{
    "titre_section": "titre",
    "biographie_exemple": {{
      "nom": "Prénom Nom",
      "discipline": "discipline artistique",
      "biographie": "texte 60-80 mots"
    }}
  }},
  "visiter": {{
    "titre_section": "titre",
    "texte_intro": "texte d'introduction",
    "cta": "texte du bouton de prise de RDV",
    "horaires": "horaires types",
    "acces": "texte d'accès"
  }},
  "newsletter": {{
    "titre": "titre accroche",
    "texte": "2-3 lignes max"
  }},
  "contact": {{
    "titre_section": "titre",
    "texte_intro": "texte chaleureux d'introduction"
  }}
}}"""

        response = self.call_claude(system_prompt, user_message)

        from utils.cleaners import parse_json_safe
        textes = parse_json_safe(response)

        self.write_json("temp/textes.json", textes)
        typer.echo(f"✅ Textes générés → {self.project.temp_dir}/textes.json")

        return textes
