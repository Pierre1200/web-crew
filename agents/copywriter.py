from __future__ import annotations
import typer
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import parse_json_safe, compact_json


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
        config = self.load_config()
        # Lecture défensive mutualisée dans BaseAgent — on ne garde ici que
        # les champs utiles au copywriter.
        ctx = self.lire_contexte_ingestion()
        ingestion = {
            "contenu_par_theme": ctx.get("contenu_par_theme", {}),
            "manques": ctx.get("manques", []),
        } if ctx else {}

        # next(..., None) au lieu de next(...) : sans valeur par défaut, un
        # plan.json sans tâche copywriter lèverait StopIteration, illisible.
        instruction = next(
            (t["instruction"] for t in plan["taches"] if t["agent"] == "copywriter"),
            None,
        )
        if instruction is None:
            raise ValueError(
                "temp/plan.json ne contient aucune tâche 'copywriter' — "
                "relance l'orchestrateur (generate) ou corrige le plan."
            )

        style_guide = plan["style_guide"]
        sections = config.get("site", {}).get("sections") or []
        if not sections:
            raise ValueError(
                "config.json : champ 'site.sections' manquant ou vide — "
                "le copywriter ne sait pas quelles sections rédiger."
            )
        sections_str = "\n".join(f"  - {s}" for s in sections)

        # Bloc de contenu réel + consigne anti-invention, seulement s'il y a du digéré
        contenu_note = ""
        if ingestion.get("contenu_par_theme"):
            self.logger.info(
                f"Contenu client injecté — {len(ingestion['contenu_par_theme'])} thème(s)"
            )
            contenu_note = f"""

CONTENU RÉEL FOURNI PAR LE CLIENT (digéré par l'agent Ingestion), par thème :
{compact_json(ingestion['contenu_par_theme'])}

Éléments manquants signalés (ne les invente PAS — reste vague ou omets) :
{compact_json(ingestion.get('manques', []))}

RÈGLE ABSOLUE : appuie-toi sur ce contenu réel. N'invente jamais de faits
factuels (adresses, horaires, noms d'artistes, dates, tarifs). Reformule et
mets en valeur ce qui est fourni ; pour ce qui manque, écris un texte générique
sans inventer d'information précise."""

        system_prompt = """Tu es un rédacteur web expert.
Tu rédiges des textes professionnels adaptés au secteur et au ton définis dans le brief.
Tu t'appuies sur le contenu réel fourni par le client quand il est disponible,
sans jamais inventer de faits factuels absents.
Réponds UNIQUEMENT en JSON valide, sans balises markdown, sans ```json.
Les textes doivent être immédiatement utilisables sur le site, en français."""

        user_message = f"""Voici ta mission :
{instruction}

Style guide à respecter :
{compact_json(style_guide)}

Voici les sections du site à rédiger :
{sections_str}
{contenu_note}

Génère un JSON avec une clé par section (snake_case, ex: "a_propos", "prestations").
Pour chaque section, génère les sous-champs texte adaptés à son type :
- Section d'accroche (hero, bannière...) → accroche + sous_titre
- Section de présentation (à propos, histoire...) → titre + texte (150-200 mots)
- Section liste (prestations, artistes, expositions, galerie...) → titre_section + au moins un exemple avec ses champs propres
- Section pratique (horaires, accès, RDV, visiter...) → titre_section + texte_intro + informations pratiques + cta
- Section formulaire (contact, newsletter, réserver...) → titre + texte + cta
- Section témoignages/avis → titre_section + au moins un exemple avec auteur et texte
Adapte librement la structure à chaque section du projet."""

        # Poursuite automatique : le JSON doit être complet pour être parsable,
        # un arrêt sur max_tokens (souvent dû au budget de raisonnement) laisserait
        # une sortie tronquée inutilisable.
        response = self.call_claude_continuable(
            system_prompt, user_message, max_tokens=8192, auto_continue=True
        )

        textes = parse_json_safe(response)

        self.write_json("temp/textes.json", textes)
        typer.echo(f"✅ Textes générés → {self.project.temp_dir}/textes.json")

        return textes
