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

    def _generate_html(self, textes: dict, style_guide: dict) -> str:
        """Génère le fichier index.html — structure uniquement, sans CSS inline."""
        typer.echo("   → Génération du HTML...")

        system_prompt = """Tu es un développeur web senior.
    Tu génères UNIQUEMENT la structure HTML5, sans aucun CSS inline, sans balise <style>.
    Commence directement par <!DOCTYPE html> et termine par </html>.
    Sois concis : pas de commentaires excessifs, va droit au but."""

        user_message = f"""Génère un index.html pour une galerie d'art.
    INTERDIT : balise <style>, CSS inline, attributs style="..."
    OBLIGATOIRE : lien <link rel="stylesheet" href="style.css"> dans le <head>

    Sections obligatoires dans le <body> :
    - <nav> navigation avec liens : Accueil, À propos, Expositions, Artistes, Visiter, Contact
    - <section id="hero"> avec h1 et p sous-titre
    - <section id="a-propos"> avec h2 et texte
    - <section id="expositions"> avec h2 et 1 carte exemple
    - <section id="artistes"> avec h2 et 1 carte exemple
    - <section id="visiter"> avec h2, texte, bouton RDV
    - <section id="newsletter"> avec h2, texte, input email + bouton
    - <section id="contact"> avec h2, formulaire complet
    - <footer> avec nom association et copyright
    Textes à intégrer :
    {json.dumps(textes, ensure_ascii=False, indent=2)}

    Lien vers main.js avant </body>."""

        return self.call_claude(system_prompt, user_message, max_tokens=8192)

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

        return self.call_claude(system_prompt, user_message, max_tokens=8192)

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

        return self.call_claude(system_prompt, user_message, max_tokens=2048)

    def run(self, context: dict) -> dict:
        typer.echo("🎨 Designer : génération du site en 3 étapes...")

        plan = self.read_json("temp/plan.json")
        textes = self.read_json("temp/textes.json")
        style_guide = plan["style_guide"]

        # 3 appels séparés — plus fiable et plus précis
        html = self._generate_html(textes, style_guide)
        css = self._generate_css(style_guide)
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