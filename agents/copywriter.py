from __future__ import annotations
import json
import typer
from agents.base_agent import BaseAgent
from utils.project import Project


class CopywriterAgent(BaseAgent):
    """Rédige tous les textes du site à partir du plan et des sections du projet."""

    def __init__(self, project: Project):
        super().__init__(
            name="copywriter",
            role="Rédacteur — génère tous les textes du site",
            project=project
        )

    def run(self, context: dict) -> dict:
        typer.echo("✍️  Copywriter : rédaction des textes...")

        plan = self.read_json("temp/plan.json")
        config = self.read_json("config.json")

        instruction = next(
            t["instruction"] for t in plan["taches"]
            if t["agent"] == "copywriter"
        )

        style_guide = plan["style_guide"]
        sections = config["site"]["sections"]
        sections_str = "\n".join(f"  - {s}" for s in sections)

        system_prompt = """Tu es un rédacteur web expert.
Tu rédiges des textes professionnels adaptés au secteur et au ton définis dans le brief.
Réponds UNIQUEMENT en JSON valide, sans balises markdown, sans ```json.
Les textes doivent être immédiatement utilisables sur le site, en français."""

        user_message = f"""Voici ta mission :
{instruction}

Style guide à respecter :
{json.dumps(style_guide, ensure_ascii=False, indent=2)}

Voici les sections du site à rédiger :
{sections_str}

Génère un JSON avec une clé par section (snake_case, ex: "a_propos", "prestations").
Pour chaque section, génère les sous-champs texte adaptés à son type :
- Section d'accroche (hero, bannière...) → accroche + sous_titre
- Section de présentation (à propos, histoire...) → titre + texte (150-200 mots)
- Section liste (prestations, artistes, expositions, galerie...) → titre_section + au moins un exemple avec ses champs propres
- Section pratique (horaires, accès, RDV, visiter...) → titre_section + texte_intro + informations pratiques + cta
- Section formulaire (contact, newsletter, réserver...) → titre + texte + cta
- Section témoignages/avis → titre_section + au moins un exemple avec auteur et texte
Adapte librement la structure à chaque section du projet."""

        response = self.call_claude(system_prompt, user_message)

        from utils.cleaners import parse_json_safe
        textes = parse_json_safe(response)

        self.write_json("temp/textes.json", textes)
        typer.echo(f"✅ Textes générés → {self.project.temp_dir}/textes.json")

        return textes
