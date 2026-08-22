"""
Agent Critique — contrôle la QUALITÉ DU CONTENU produit par le copywriter.

Complémentaire du validateur : le validateur vérifie la STRUCTURE (HTML
complet, classes cohérentes...), le critique vérifie le FOND — sections
creuses, texte passe-partout, et surtout FAITS INVENTÉS par rapport aux
données réellement fournies par le client (temp/context.json).
Un appel Haiku par contrôle : la supervision de contenu coûte quelques
centimes, pas une relecture humaine complète.
"""
from __future__ import annotations
import typer
from agents.base_agent import BaseAgent
from utils.cleaners import compact_json


class CritiqueAgent(BaseAgent):
    """Relit textes.json et signale inventions, sections vides et texte générique."""

    # Un juge trop indulgent ne sert à rien : le critique doit repérer des
    # inventions factuelles subtiles, ce qui demande du raisonnement. Haiku
    # laissait passer trop de choses pour un contrôle qui précède une livraison.
    MODEL = "claude-sonnet-5"
    THINKING = {"type": "adaptive"}
    EFFORT = "high"

    def __init__(self, project):
        super().__init__(
            name="critique",
            role="Critique — contrôle le fond des textes générés",
            project=project,
        )

    def run(self, context: dict) -> dict:
        typer.echo("🧐 Critique : relecture du fond des textes...")

        textes_path = self.project.temp_dir / "textes.json"
        if not textes_path.exists():
            raise FileNotFoundError(
                "temp/textes.json introuvable — lance d'abord generate "
                "(le critique relit le travail du copywriter)."
            )
        textes = self.read_json("temp/textes.json")
        config = self.load_config()
        ctx = self.lire_contexte_ingestion()

        sections_prevues = config.get("site", {}).get("sections", [])

        # La référence factuelle : sans données ingérées, TOUT fait précis
        # est suspect (le copywriter n'avait aucune source pour l'affirmer).
        if ctx.get("contenu_par_theme"):
            bloc_reference = f"""
Données RÉELLES fournies par le client — seule source de vérité factuelle :
{compact_json(ctx["contenu_par_theme"])}"""
        else:
            bloc_reference = """
Aucune donnée client n'a été ingérée : tout fait précis (adresse, horaire,
téléphone, nom propre, date, tarif) est par définition inventé — signale-le."""

        system_prompt = """Tu es un relecteur éditorial rigoureux pour sites vitrines.
On te donne les textes générés, les sections prévues, et les données réelles du client.
Tu contrôles le FOND, pas le code. Trois types de problèmes, dans cet ordre de gravité :
- "invention" : fait précis (adresse, horaire, téléphone, nom, date, tarif, chiffre)
  absent des données réelles du client
- "vide" : section prévue absente des textes, ou quasi sans contenu
- "generique" : texte passe-partout qui pourrait décrire n'importe quelle entreprise
Sois exigeant sur les inventions (risque réel pour le client), mesuré sur le style.
Réponds UNIQUEMENT en JSON valide, sans balise markdown."""

        user_message = f"""Sections prévues dans la config :
{compact_json(sections_prevues)}

Textes générés à contrôler :
{compact_json(textes)}
{bloc_reference}

Produis un JSON avec cette structure exacte :
{{
  "score": <entier 0 à 10, 10 = irréprochable>,
  "problemes": [
    {{"section": "...", "type": "invention|vide|generique", "detail": "explication courte avec citation du passage fautif"}}
  ],
  "resume": "verdict global en 2 phrases"
}}"""

        response = self.call_claude(system_prompt, user_message, max_tokens=8192)
        critique = self.parse_json_response(response)

        self.write_json("temp/critique.json", critique)

        score = critique.get("score", "?")
        problemes = critique.get("problemes", [])
        inventions = [p for p in problemes if p.get("type") == "invention"]

        typer.echo(f"   📝 Score contenu : {score}/10 — {len(problemes)} problème(s)")
        for p in problemes:
            icone = "❌" if p.get("type") == "invention" else "⚠️ "
            typer.echo(f"   {icone} [{p.get('type', '?')}] {p.get('section', '?')} : {p.get('detail', '')}")
        if inventions:
            typer.echo(f"   🚨 {len(inventions)} invention(s) factuelle(s) — à vérifier avant livraison !")
        if critique.get("resume"):
            typer.echo(f"   💬 {critique['resume']}")

        self.logger.info(f"Critique : score {score}/10, {len(problemes)} problème(s), "
                         f"dont {len(inventions)} invention(s)")
        return critique
