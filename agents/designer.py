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

        user_message = f"""Voici le fichier style.css DÉJÀ ÉCRIT :
    {css}

    Génère un index.html qui utilise EXACTEMENT les classes CSS définies ci-dessus.
    N'invente AUCUNE nouvelle classe — utilise uniquement celles du CSS.

    INTERDIT : balise <style>, CSS inline, attributs style="..."
    OBLIGATOIRE : <link rel="stylesheet" href="style.css"> dans le <head>
    OBLIGATOIRE : <script src="main.js"></script> avant </body>

    Sections dans le <body> : nav, hero, à-propos, expositions, artistes, visiter, newsletter, contact, footer.

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

        user_message = f"""Génère un style.css complet pour une galerie d'art rurale contemporaine.

Style guide :
{json.dumps(style_guide, ensure_ascii=False, indent=2)}

Contraintes :
- Variables CSS en :root pour toutes les couleurs et fontes
- Reset CSS minimal en début de fichier
- Mobile-first avec breakpoints 768px et 1200px
- Navigation sticky transparente qui devient blanche au scroll
- Hero plein écran avec overlay sombre
- Grille expositions : 1 col mobile / 2 col tablette / 3 col desktop
- Grille artistes : 2 col mobile / 4 col desktop
- Boutons CTA en terre de sienne (#A0522D)
- Animations fade-in avec classe .visible
- Footer sobre en anthracite
- Sections alternées blanc cassé et blanc pur
- Code organisé et commenté par section"""

        from utils.cleaners import clean_code_output
        response = self.call_claude(system_prompt, user_message, max_tokens=8192)
        return clean_code_output(response)

    def _generate_js(self) -> str:
        """Génère le fichier main.js."""
        typer.echo("   → Génération du JavaScript...")

        system_prompt = """Tu es un développeur JavaScript vanilla expert.
Tu génères UNIQUEMENT du code JavaScript pur, sans aucun texte avant ou après."""

        user_message = """Génère un main.js pour un site vitrine de galerie d'art.

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

        # Écrit les fichiers
        output_dir = Path("workspace/output/projet-exemple")
        output_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        (output_dir / "index.html").write_text(html, encoding="utf-8")
        (output_dir / "style.css").write_text(css, encoding="utf-8")
        (output_dir / "main.js").write_text(js, encoding="utf-8")

        typer.echo("✅ Site généré → workspace/output/projet-exemple/")
        typer.echo("   • index.html")
        typer.echo("   • style.css")
        typer.echo("   • main.js")

        return {
            "output_dir": str(output_dir),
            "fichiers": ["index.html", "style.css", "main.js"]
        }