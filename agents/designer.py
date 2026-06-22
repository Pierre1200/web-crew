from __future__ import annotations
import json
import typer
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import clean_code_output, extract_css_classes

# Mots-clés qui identifient une section avec formulaire
_FORM_KEYWORDS = {"contact", "newsletter", "reserver", "formulaire", "rdv", "inscription"}


class DesignerAgent(BaseAgent):
    """Génère le HTML, CSS et JS complets du site."""

    def __init__(self, project: Project):
        super().__init__(
            name="designer",
            role="Designer — génère le HTML/CSS/JS du site",
            project=project
        )

    # ------------------------------------------------------------------
    # Amélioration 3 — guard interne : vérifie qu'un HTML est complet
    # ------------------------------------------------------------------
    def _valider_html(self, html: str) -> bool:
        return "</html>" in html and "<body" in html

    # ------------------------------------------------------------------
    # Amélioration 2 — CSS informé des sections du projet
    # ------------------------------------------------------------------
    def _generate_css(self, style_guide: dict, sections: list) -> str:
        """Génère style.css en connaissant les sections à styler."""
        typer.echo("   → Génération du CSS...")

        # Amélioration 4 — plus d'indentation parasite dans le prompt
        system_prompt = """\
Tu es un designer CSS expert.
Tu génères UNIQUEMENT du code CSS pur, sans aucun texte avant ou après.
Commence directement par les variables CSS et termine par la dernière règle."""

        ambiance = style_guide.get("ambiance", "site web professionnel")
        sections_str = ", ".join(sections)

        user_message = f"""Génère un style.css complet pour : {ambiance}.

Style guide à respecter scrupuleusement :
{json.dumps(style_guide, ensure_ascii=False, indent=2)}

Sections du site à styler (génère des règles pour chacune) : {sections_str}

Contraintes techniques :
- Variables CSS en :root pour toutes les couleurs et fontes
- Reset CSS minimal en début de fichier
- Mobile-first avec breakpoints 768px et 1200px
- Navigation sticky transparente qui devient colorée au scroll
- Hero plein écran avec overlay sombre
- Grilles de contenu : 1 col mobile / 2 col tablette / 3 col desktop
- Animations fade-in avec classe .visible
- Footer sobre
- Sections alternées
- Code organisé et commenté par section"""

        response = self.call_claude(system_prompt, user_message, max_tokens=8192)
        return clean_code_output(response)

    # ------------------------------------------------------------------
    # Améliorations 1 + 4 — retry si tronqué, prompt sans indentation
    # ------------------------------------------------------------------
    def _generate_html(self, textes: dict, css: str) -> str:
        """Génère index.html basé sur le CSS. Retry automatique si tronqué."""
        typer.echo("   → Génération du HTML (basé sur le CSS)...")

        system_prompt = """\
Tu es un développeur web senior.
Tu génères UNIQUEMENT la structure HTML5, sans CSS inline, sans balise <style>.
Commence directement par <!DOCTYPE html> et termine OBLIGATOIREMENT par </body> puis </html>."""

        sections_str = ", ".join(["nav"] + list(textes.keys()) + ["footer"])

        classes_str = ", ".join(extract_css_classes(css))

        user_message = f"""Génère un index.html complet pour un site vitrine.

Classes CSS disponibles — utilise UNIQUEMENT celles-ci, n'en invente aucune :
{classes_str}

INTERDIT : balise <style>, CSS inline, attributs style="..."
OBLIGATOIRE : <link rel="stylesheet" href="style.css"> dans le <head>
OBLIGATOIRE : <script src="main.js"></script> avant </body>
OBLIGATOIRE : le fichier doit se terminer par </body> puis </html> — ne tronque pas

Sections dans le <body> : {sections_str}.

Textes à intégrer :
{json.dumps(textes, ensure_ascii=False, indent=2)}"""

        html = clean_code_output(self.call_claude(system_prompt, user_message, max_tokens=8192))

        if not self._valider_html(html):
            self.logger.warning("HTML tronqué à la 1re tentative — retry...")
            typer.echo("   ⚠️  HTML tronqué, nouvelle tentative...")
            html = clean_code_output(self.call_claude(system_prompt, user_message, max_tokens=8192))


        return html

    # ------------------------------------------------------------------
    # Amélioration 5 — JS contextuel : connaît les sections + formulaires
    # ------------------------------------------------------------------
    def _generate_js(self, sections: list) -> str:
        """Génère main.js adapté aux sections du projet."""
        typer.echo("   → Génération du JavaScript...")

        system_prompt = """\
Tu es un développeur JavaScript vanilla expert.
Tu génères UNIQUEMENT du code JavaScript pur, sans aucun texte avant ou après."""

        form_sections = [s for s in sections if any(kw in s.lower() for kw in _FORM_KEYWORDS)]
        form_info = (
            f"\nSections avec formulaire à valider : {', '.join(form_sections)}."
            if form_sections else ""
        )

        user_message = f"""Génère un main.js pour un site vitrine statique.

Sections du site : {', '.join(sections)}.{form_info}

Fonctionnalités obligatoires :
- Intersection Observer pour les animations fade-in au scroll (ajoute classe .visible)
- Navigation sticky : ajout classe .scrolled sur nav après 80px de scroll
- Smooth scroll sur les liens d'ancre
- Menu burger pour mobile (toggle classe .open)
- Lazy loading des images avec attribut data-src
- Pour chaque section avec formulaire : validation des champs requis + message de confirmation"""

        response = self.call_claude(system_prompt, user_message, max_tokens=4096)
        return clean_code_output(response)

    # ------------------------------------------------------------------
    # run() — orchestre les 3 générations + guard avant écriture HTML
    # ------------------------------------------------------------------
    def run(self, context: dict) -> dict:
        typer.echo("🎨 Designer : génération du site en 3 étapes...")

        plan = self.read_json("temp/plan.json")
        textes = self.read_json("temp/textes.json")
        style_guide = plan["style_guide"]
        sections = list(textes.keys())

        css  = self._generate_css(style_guide, sections)
        html = self._generate_html(textes, css)
        js   = self._generate_js(sections)

        output_dir = self.project.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "assets").mkdir(exist_ok=True)

        # CSS et JS toujours écrits
        (output_dir / "style.css").write_text(css, encoding="utf-8")
        (output_dir / "main.js").write_text(js, encoding="utf-8")

        # Amélioration 3 — guard : n'écrase index.html que si le HTML est complet
        if self._valider_html(html):
            (output_dir / "index.html").write_text(html, encoding="utf-8")
            typer.echo(f"✅ Site généré → {output_dir}/")
            typer.echo("   • index.html")
            typer.echo("   • style.css")
            typer.echo("   • main.js")
        else:
            self.logger.error("HTML invalide après retry — index.html non écrasé")
            typer.echo("   ❌ HTML incomplet même après retry — index.html existant conservé")
            typer.echo(f"   ✅ style.css et main.js écrits → {output_dir}/")

        return {
            "output_dir": str(output_dir),
            "fichiers": ["index.html", "style.css", "main.js"]
        }

    # ------------------------------------------------------------------
    # regenerate_html() — re-génère index.html depuis les fichiers existants
    # ------------------------------------------------------------------
    def regenerate_html(self) -> bool:
        """Re-génère uniquement index.html (textes et CSS déjà sur disque)."""
        textes = self.read_json("temp/textes.json")
        css = (self.project.output_dir / "style.css").read_text(encoding="utf-8")
        html = self._generate_html(textes, css)
        if self._valider_html(html):
            (self.project.output_dir / "index.html").write_text(html, encoding="utf-8")
            self.logger.info("index.html régénéré avec succès")
            return True
        self.logger.error("HTML toujours invalide après regenerate_html")
        return False

    # ------------------------------------------------------------------
    # fix() — correction ciblée des classes CSS manquantes
    # ------------------------------------------------------------------
    def fix(self, problemes: list, css: str, html: str) -> str:
        """Génère UNIQUEMENT les règles CSS manquantes signalées par le validateur."""
        typer.echo("   🔧 Designer : génération des règles manquantes...")

        classes_manquantes = [p for p in problemes if "absente du CSS" in p]

        if not classes_manquantes:
            typer.echo("   ℹ️  Aucun problème de classe à corriger")
            return ""

        system_prompt = """\
Tu es un développeur CSS expert.
On te donne une liste de classes CSS manquantes et le HTML qui les utilise.
Tu génères UNIQUEMENT les nouvelles règles CSS pour ces classes.
Ne réécris PAS le CSS existant. Génère SEULEMENT les règles manquantes.
Réponds sans balise markdown, juste les règles CSS."""

        noms_classes = []
        for p in classes_manquantes:
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

        response = self.call_claude(system_prompt, user_message, max_tokens=2048)
        return clean_code_output(response)
