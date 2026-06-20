from __future__ import annotations
import json
import typer
from pathlib import Path
from agents.base_agent import BaseAgent

class DesignerAgent(BaseAgent):
    """Génère le HTML et CSS complet du site."""

    def __init__(self):
        super().__init__(
            name="designer",
            role="Designer — génère le HTML/CSS du site"
        )

    def _generate_html(self, textes: dict, style_guide: dict, css: str) -> str:
        """Génère index.html en se basant sur le CSS déjà produit."""
        typer.echo("   → Génération du HTML (basé sur le CSS)...")

        system_prompt = """Tu es un développeur web senior.
    Tu génères UNIQUEMENT la structure HTML5, sans CSS inline, sans balise <style>.
    Commence directement par <!DOCTYPE html> et termine par </html>."""

        sections_str = ", ".join(["nav"] + list(textes.keys()) + ["footer"])
        user_message = f"""Voici le fichier style.css DÉJÀ ÉCRIT :
    {css}

    Génère un index.html qui utilise EXACTEMENT les classes CSS définies ci-dessus.
    N'invente AUCUNE nouvelle classe — utilise uniquement celles du CSS.

    INTERDIT : balise <style>, CSS inline, attributs style="..."
    OBLIGATOIRE : <link rel="stylesheet" href="style.css"> dans le <head>
    OBLIGATOIRE : <script src="main.js"></script> avant </body>

    Sections dans le <body> : {sections_str}.

    Textes à intégrer :
    {json.dumps(textes, ensure_ascii=False, indent=2)}"""

        from utils.cleaners import clean_code_output
        response = self.call_claude(system_prompt, user_message, max_tokens=8192)
        return clean_code_output(response)

    def _generate_css(self, style_guide: dict) -> str:
        """Génère le fichier style.css."""
        typer.echo("   → Génération du CSS...")

        system_prompt = """Tu es un designer CSS expert.
Tu génères UNIQUEMENT du code CSS pur, sans aucun texte avant ou après.
Commence directement par les variables CSS et termine par la dernière règle."""

        ambiance = style_guide.get("ambiance", "site web professionnel")
        user_message = f"""Génère un style.css complet pour : {ambiance}.

Style guide à respecter scrupuleusement :
{json.dumps(style_guide, ensure_ascii=False, indent=2)}

Contraintes techniques :
- Variables CSS en :root pour toutes les couleurs et fontes (utilise les couleurs du style guide)
- Reset CSS minimal en début de fichier
- Mobile-first avec breakpoints 768px et 1200px
- Navigation sticky transparente qui devient colorée au scroll
- Hero plein écran avec overlay sombre
- Grilles de contenu : 1 col mobile / 2 col tablette / 3 col desktop
- Animations fade-in avec classe .visible
- Footer sobre
- Sections alternées
- Code organisé et commenté par section"""

        from utils.cleaners import clean_code_output
        response = self.call_claude(system_prompt, user_message, max_tokens=8192)
        return clean_code_output(response)

    def _generate_js(self) -> str:
        """Génère le fichier main.js."""
        typer.echo("   → Génération du JavaScript...")

        system_prompt = """Tu es un développeur JavaScript vanilla expert.
Tu génères UNIQUEMENT du code JavaScript pur, sans aucun texte avant ou après."""

        user_message = """Génère un main.js pour un site vitrine statique.

Fonctionnalités :
- Intersection Observer pour les animations fade-in au scroll (ajoute classe .visible)
- Navigation sticky : ajout classe .scrolled sur nav après 80px de scroll
- Smooth scroll sur les liens d'ancre
- Menu burger pour mobile (toggle classe .open)
- Formulaire de contact : validation basique + message de confirmation
- Lazy loading des images avec attribut data-src"""

        from utils.cleaners import clean_code_output
        response = self.call_claude(system_prompt, user_message, max_tokens=8192)
        return clean_code_output(response)

    def run(self, context: dict) -> dict:
        typer.echo("🎨 Designer : génération du site en 3 étapes...")

        plan = self.read_json("temp/plan.json")
        textes = self.read_json("temp/textes.json")
        style_guide = plan["style_guide"]

        # 3 appels séparés — plus fiable et plus précis
        css = self._generate_css(style_guide)
        html = self._generate_html(textes, style_guide, css)
        js = self._generate_js()

        # Lit le projet cible depuis le brief
        brief = self.read_json("input/brief.json")
        project_id = brief["output"]["project_id"]

        # Écrit les fichiers
        output_dir = Path("workspace/output") / project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        (output_dir / "index.html").write_text(html, encoding="utf-8")
        (output_dir / "style.css").write_text(css, encoding="utf-8")
        (output_dir / "main.js").write_text(js, encoding="utf-8")

        typer.echo(f"✅ Site généré → workspace/output/{project_id}/")
        typer.echo("   • index.html")
        typer.echo("   • style.css")
        typer.echo("   • main.js")

        return {
            "output_dir": str(output_dir),
            "fichiers": ["index.html", "style.css", "main.js"]
        }
    
    def fix(self, problemes: list, css: str, html: str) -> str:
        """
        Génère UNIQUEMENT les règles CSS manquantes (pas tout le CSS).
        Retourne les nouvelles règles à ajouter.
        """
        typer.echo("   🔧 Designer : génération des règles manquantes...")

        classes_manquantes = [
            p for p in problemes
            if "absente du CSS" in p
        ]

        if not classes_manquantes:
            typer.echo("   ℹ️  Aucun problème de classe à corriger")
            return ""

        system_prompt = """Tu es un développeur CSS expert.
On te donne une liste de classes CSS manquantes et le HTML qui les utilise.
Tu génères UNIQUEMENT les nouvelles règles CSS pour ces classes.
Ne réécris PAS le CSS existant. Génère SEULEMENT les règles manquantes.
Réponds sans balise markdown, juste les règles CSS."""

        # Extrait juste les noms de classes des messages de problème
        noms_classes = []
        for p in classes_manquantes:
            # Le message est : "⚠️  Classe 'xxx' utilisée..."
            debut = p.find("'") + 1
            fin = p.find("'", debut)
            noms_classes.append(p[debut:fin])

        plan = self.read_json("temp/plan.json")
        couleurs = plan.get("style_guide", {}).get("couleurs", [])
        couleurs_str = ", ".join(couleurs) if couleurs else "les couleurs définies dans le projet"

        user_message = f"""Voici le HTML qui utilise ces classes :
{html}

Classes à styler (actuellement absentes du CSS) :
{', '.join(noms_classes)}

Génère UNIQUEMENT les règles CSS pour ces {len(noms_classes)} classes.
Respecte la palette du projet : {couleurs_str}.
Commence directement par la première règle CSS."""

        from utils.cleaners import clean_code_output
        response = self.call_claude(system_prompt, user_message, max_tokens=2048)
        nouvelles_regles = clean_code_output(response)

        # On retourne SEULEMENT les nouvelles règles
        return nouvelles_regles