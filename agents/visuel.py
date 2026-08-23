"""
Agent Critique visuelle — REGARDE le site rendu et juge ce qu'il voit.

Le chaînon qui manquait. Le validateur prouve que le HTML est valide, la
critique de contenu vérifie les faits : ni l'un ni l'autre ne peut dire si
la page est belle, si elle respecte la maquette, ou si elle a l'air d'un
gabarit. Pour ça il faut des yeux.

Le site est photographié en local (Playwright, zéro token) à trois largeurs,
puis les images sont soumises au modèle avec le cahier des charges du client.
Le verdict revient en JSON structuré, avec des corrections CSS directement
applicables par le designer.

Coût indicatif : ~9 images ≈ 15k tokens d'entrée, soit environ 0,15 $ par passe.
"""
from __future__ import annotations
import typer

from agents.base_agent import BaseAgent
from utils.capture import capturer_site, CaptureIndisponible
from utils.cleaners import compact_json
from utils.pages import collections_declarees

# Gravités, de la plus grave à la plus légère
GRAVITES = ("bloquant", "majeur", "mineur")


class VisuelAgent(BaseAgent):
    """Photographie le site généré et le critique comme un directeur artistique."""

    # Juger une composition demande un vrai regard : c'est le même niveau
    # d'exigence que la génération elle-même, pour un coût bien inférieur
    # (une passe de critique vaut ~15 % d'une génération complète).
    MODEL = "claude-opus-5"
    EFFORT = "xhigh"

    def __init__(self, project):
        super().__init__(
            name="visuel",
            role="Critique visuelle — juge le rendu réel du site",
            project=project,
        )

    def _dossier_captures(self):
        return self.project.logs_dir / "captures"

    def _pages_secondaires(self) -> list:
        """Échantillon de pages de collection à photographier en plus de l'accueil.

        Lors du premier run réel, seule `index.html` a été photographiée : les
        treize pages de collection, soit la majorité du site, n'ont jamais été
        vues. C'est pourtant là que se trouvait le bug qui les privait toutes
        d'images de couverture.

        On prend deux pages par collection, la liste et un contenu : assez pour
        repérer un gabarit cassé, sans faire exploser le nombre d'images.
        """
        try:
            collections = collections_declarees(self.load_config())
        except (OSError, ValueError):
            return []

        echantillon = []
        for collection in collections:
            dossier = self.project.output_dir / collection["url"]
            liste = dossier / "index.html"
            if not liste.exists():
                continue
            echantillon.append(liste)
            contenus = sorted(
                p for p in dossier.glob("*.html") if p.name != "index.html"
            )
            if contenus:
                echantillon.append(contenus[0])

        if echantillon:
            self.logger.info(
                f"{len(echantillon)} page(s) de collection ajoutée(s) aux captures"
            )
        return echantillon

    def _construire_blocs(self, images: list[dict], contexte: str) -> list:
        """Assemble le message mixte : consignes, puis chaque image légendée.

        Chaque image est précédée d'un court texte qui dit ce qu'on regarde —
        sans ça, le modèle ne sait pas si la 4e image est le bas de la page
        bureau ou le haut de la page mobile.
        """
        blocs = [{"type": "text", "text": contexte}]
        for img in images:
            blocs.append({
                "type": "text",
                "text": (
                    f"\n--- Page « {img.get('page', 'accueil')} », rendu "
                    f"{img['format']} ({img['largeur']}px de large), écran "
                    f"{img['tranche']}/{img['total_tranches']} en partant du haut ---"
                ),
            })
            blocs.append(self.build_bloc_image(img["chemin"]))
        return blocs

    def _prompt_systeme(self) -> str:
        return """Tu es directeur artistique senior. On te soumet les captures d'écran \
d'un site qui vient d'être produit, et le cahier des charges du client.
Ton travail : dire honnêtement si ce rendu est livrable, et sinon pourquoi.

Tu regardes, dans cet ordre de priorité :
1. CONFORMITÉ AU CAHIER DES CHARGES — structure, ordre des blocs, répartition \
des colonnes, présence ou absence de navigation, contraintes explicites. Un \
écart ici est BLOQUANT, même si la page est jolie.
2. COMPOSITION — hiérarchie (une chose domine-t-elle par écran ?), rythme \
vertical (les sections respirent-elles différemment ou tout est-il uniforme ?), \
alignements, marges, équilibre des masses.
3. TYPOGRAPHIE — échelle cohérente, largeur de lecture raisonnable, interlignage, \
contraste de graisses, titres qui ne se noient pas. Signale les lignes veuves \
(un mot seul en fin de titre) et les alignements qui décrochent d'une carte à \
l'autre : ce sont les défauts qui trahissent un travail non fini.
4. COULEUR ET LISIBILITÉ — contraste texte/fond suffisant, palette tenue, \
accent utilisé avec parcimonie.
5. RESPONSIVE — le rendu mobile est-il pensé, ou juste écrasé ? Débordements, \
textes coupés, images déformées, cibles tactiles trop petites.
6. SIGNATURE « GABARIT » — le site a-t-il l'air fabriqué à la chaîne ? \
(hero plein écran générique, trois cartes identiques, tout centré, animations \
partout, aucune personnalité liée au secteur du client).

Sois SÉVÈRE et concret. Un site simplement « correct » mérite 6, pas 9. \
Ne félicite pas : décris ce qui cloche et comment le corriger.
Chaque problème doit venir avec une correction CSS applicable telle quelle \
(sélecteur + propriétés). Si un problème ne peut PAS se régler en CSS \
(structure HTML absente, section manquante), laisse "correction_css" vide et \
dis-le dans le constat.

Écris ces correctifs en CSS moderne — container queries, :has(), color-mix(), \
text-wrap, propriétés logiques — et SANS `!important` : ils sont insérés hors \
couche en fin de feuille, ce qui leur donne déjà la priorité sur tout le reste.

Réponds UNIQUEMENT en JSON valide, sans balise markdown."""

    def _lire_direction(self) -> str:
        """Relit la direction artistique arrêtée avant la génération.

        C'est ce qui rend la critique précise plutôt que de simple bon goût :
        au lieu de juger « en général », on vérifie que le rendu exécute les
        décisions annoncées (archétype, rythme, palette, signature).
        """
        chemin = self.project.temp_dir / "direction.json"
        if not chemin.exists():
            return ""
        try:
            direction = self.read_json("temp/direction.json")
        except (ValueError, OSError):
            return ""
        if not direction:
            return ""
        return f"""

DIRECTION ARTISTIQUE QUI AVAIT ÉTÉ ARRÊTÉE — le rendu doit l'exécuter :
{compact_json(direction)}

Juge d'abord l'ÉCART entre ces décisions et ce que tu vois : archétype de mise
en page réellement appliqué, rythme des sections conforme aux valeurs annoncées,
usage de l'accent respecté, éléments animés limités à la liste fermée. Un écart
avec la direction est au minimum « majeur ». Et si le rendu n'incarne pas la
« signature » annoncée, dis-le franchement."""

    def _prompt_contexte(self, plan: dict) -> str:
        cahier = self.cahier_des_charges(plan)
        style_guide = plan.get("style_guide", {})

        return f"""{cahier}{self._lire_direction()}

Identité visuelle décidée pour ce projet :
{compact_json(style_guide)}

Voici les captures du site tel qu'il est rendu aujourd'hui, à trois largeurs.
Les animations d'apparition ont été neutralisées pour la capture : ne juge PAS
l'absence d'animation, juge la composition figée que tu vois.

Produis un JSON avec exactement cette structure :
{{
  "score": <entier 0 à 10 — 10 = livrable tel quel à un client payant>,
  "conforme_au_brief": <true/false — la structure demandée est-elle respectée ?>,
  "verdict": "<2 phrases : ce qui marche, ce qui bloque>",
  "problemes": [
    {{
      "gravite": "bloquant|majeur|mineur",
      "zone": "<section ou élément concerné>",
      "format": "mobile|tablette|bureau|tous",
      "constat": "<ce que tu vois et pourquoi c'est un problème>",
      "correction_css": "<règles CSS complètes à ajouter, ou chaîne vide>"
    }}
  ]
}}"""

    def run(self, context: dict) -> dict:
        typer.echo("👁  Critique visuelle : capture du site...")

        html_path = self.project.output_dir / "index.html"
        try:
            images = capturer_site(
                html_path,
                self._dossier_captures(),
                pages_secondaires=self._pages_secondaires(),
            )
        except CaptureIndisponible as e:
            typer.echo(f"\n❌ {e}")
            raise

        typer.echo(
            f"   → {len(images)} capture(s) dans {self._dossier_captures()}/"
        )

        try:
            plan = self.read_json("temp/plan.json")
        except (OSError, ValueError):
            plan = {}
            self.logger.warning("plan.json illisible — critique sans cahier des charges")

        blocs = self._construire_blocs(images, self._prompt_contexte(plan))

        typer.echo("   → Analyse du rendu par le modèle...")
        # 48 000 et non 16 000 : en effort xhigh avec une dizaine d'images, le
        # raisonnement consomme l'essentiel du budget avant la première ligne
        # de JSON. Le premier run réel s'est fait couper au milieu d'une chaîne.
        reponse = self.call_claude_vision(self._prompt_systeme(), blocs, max_tokens=48000)
        critique = self.parse_json_response(reponse)

        self.write_json("temp/critique_visuelle.json", critique)
        self._afficher(critique)
        return critique

    def _afficher(self, critique: dict):
        score = critique.get("score", "?")
        conforme = critique.get("conforme_au_brief")
        problemes = critique.get("problemes", []) or []

        etiquette = {True: "✅ conforme au brief",
                     False: "❌ NON conforme au brief"}.get(conforme, "conformité inconnue")
        typer.echo(f"\n   🎨 Score visuel : {score}/10 — {etiquette}")

        if critique.get("verdict"):
            typer.echo(f"   💬 {critique['verdict']}")

        # Tri par gravité pour que le pire saute aux yeux en premier
        ordre = {g: i for i, g in enumerate(GRAVITES)}
        for p in sorted(problemes, key=lambda x: ordre.get(x.get("gravite"), 9)):
            icone = {"bloquant": "🛑", "majeur": "⚠️ ", "mineur": "·"}.get(
                p.get("gravite"), "·"
            )
            typer.echo(
                f"   {icone} [{p.get('format', '?')}] {p.get('zone', '?')} — "
                f"{p.get('constat', '')}"
            )

        corrigeables = [p for p in problemes if p.get("correction_css")]
        self.logger.info(
            f"Critique visuelle : score {score}/10, conforme={conforme}, "
            f"{len(problemes)} problème(s) dont {len(corrigeables)} corrigeable(s) en CSS"
        )
        if problemes and not corrigeables:
            typer.echo(
                "   ℹ️  Aucun problème corrigeable en CSS — il faut régénérer "
                "(design-only --replan) ou préciser le brief."
            )
