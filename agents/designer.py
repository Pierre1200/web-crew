from __future__ import annotations
import json
import typer
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import clean_code_output, extract_css_classes, strip_markdown_fences

_FORM_KEYWORDS = {"contact", "newsletter", "reserver", "formulaire", "rdv", "inscription"}

_SEP_HTML = "===HTML==="
_SEP_CSS  = "===CSS==="
_SEP_JS   = "===JS==="


class DesignerAgent(BaseAgent):
    """Génère le HTML, CSS et JS du site en une seule requête cohérente."""

    def __init__(self, project: Project):
        super().__init__(
            name="designer",
            role="Designer — génère le HTML/CSS/JS du site",
            project=project
        )

    def _valider_html(self, html: str) -> bool:
        return "</html>" in html and "<body" in html

    def _parse_site_response(self, response: str) -> tuple[str, str, str]:
        """Extrait HTML, CSS et JS depuis la réponse multi-sections."""

        def extract(text: str, start_marker: str, end_marker: str | None = None) -> str:
            i = text.find(start_marker)
            if i == -1:
                return ""
            i += len(start_marker)
            if end_marker:
                j = text.find(end_marker, i)
                return text[i:j].strip() if j != -1 else text[i:].strip()
            return text[i:].strip()

        html = extract(response, _SEP_HTML, _SEP_CSS)
        css  = extract(response, _SEP_CSS,  _SEP_JS)
        js   = extract(response, _SEP_JS)

        html = strip_markdown_fences(html) if html else ""
        css  = strip_markdown_fences(css)  if css  else ""
        js   = strip_markdown_fences(js)   if js   else ""

        return html, css, js

    def _build_fonts_link(self, fonts: dict) -> str:
        """Construit le <link> Google Fonts depuis les noms de polices."""
        heading = fonts.get("heading", "")
        body    = fonts.get("body", "")
        if not heading and not body:
            return ""
        # Encode les noms pour l'URL (espaces → +)
        parts = []
        if heading:
            slug = heading.replace(" ", "+")
            parts.append(f"family={slug}:ital,wght@0,400;0,600;0,700;1,400")
        if body:
            slug = body.replace(" ", "+")
            parts.append(f"family={slug}:wght@300;400;600")
        query = "&".join(parts) + "&display=swap"
        return (
            '    <link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?{query}">'
        )

    def _generate_site(self, plan: dict, textes: dict) -> tuple[str, str, str]:
        """Génère HTML + CSS + JS en une seule requête pour garantir la cohérence."""
        style_guide  = plan["style_guide"]
        sections     = list(textes.keys())
        sections_str = ", ".join(["nav"] + sections + ["footer"])

        fonts        = style_guide.get("fonts", {})
        font_heading = fonts.get("heading", "")
        font_body    = fonts.get("body", "")
        fonts_link   = self._build_fonts_link(fonts)

        fonts_html_note = (
            f"\nOBLIGATOIRE dans le <head> (avant style.css) :\n{fonts_link}"
            if fonts_link else ""
        )
        fonts_css_note = ""
        if font_heading or font_body:
            fonts_css_note = f"\nPolices à utiliser dans les variables :root :"
            if font_heading:
                fonts_css_note += f'\n- --font-heading: "{font_heading}", serif;'
            if font_body:
                fonts_css_note += f'\n- --font-body: "{font_body}", sans-serif;'

        form_sections = [s for s in sections if any(kw in s.lower() for kw in _FORM_KEYWORDS)]
        form_info = (
            f"\nSections avec formulaire (validation JS requise) : {', '.join(form_sections)}."
            if form_sections else ""
        )

        system_prompt = f"""\
Tu es un développeur web full-stack expert.
Tu génères les 3 fichiers d'un site vitrine statique en UNE SEULE réponse.
Utilise EXACTEMENT ces séparateurs dans cet ordre, sans aucun texte entre les sections :

{_SEP_HTML}
(code HTML complet de <!DOCTYPE html> à </html>)
{_SEP_CSS}
(code CSS complet)
{_SEP_JS}
(code JavaScript complet)

Règle absolue : aucun texte avant {_SEP_HTML}, aucun texte après le dernier bloc JS.
Aucune explication. Si la génération est interrompue et reprise, continue directement \
le code sans rien résumer."""

        user_message = f"""Génère les 3 fichiers d'un site vitrine professionnel.

Style guide :
{json.dumps(style_guide, ensure_ascii=False, indent=2)}

Sections ({sections_str}) avec leurs textes :
{json.dumps(textes, ensure_ascii=False, indent=2)}

RÈGLES HTML :
- De <!DOCTYPE html> à </html>, complet, sans omission ni troncature
- lang="fr" sur la balise <html>
- <meta name="viewport" content="width=device-width, initial-scale=1.0"> dans le <head>
- <meta charset="UTF-8"> dans le <head>{fonts_html_note}
- <link rel="stylesheet" href="style.css"> dans le <head>
- <script src="main.js"></script> juste avant </body>
- Pas de <style> ni de CSS inline
- Classes BEM cohérentes avec le CSS généré
- Les <img> sans src réel : utiliser src="" et classe img-placeholder

RÈGLES CSS :{fonts_css_note}
- Variables CSS dans :root (--color-primaire, --color-fond, --color-texte, --color-accent, --color-secondaire, --font-heading, --font-body)
- Reset CSS minimal en début
- Mobile-first, breakpoints 768px et 1200px
- Navigation sticky transparente → colorée (.scrolled) au scroll, hauteur 70px
- Hero plein écran (min-height: 100vh) avec image de fond simulée (gradient sombre), overlay, texte centré
- Grilles : 1 col mobile / 2 col tablette / 3 col desktop
- Échelle typographique : h1 clamp(2.5rem, 6vw, 5rem), h2 clamp(1.8rem, 4vw, 3rem), h3 clamp(1.2rem, 2.5vw, 1.8rem)
- Boutons : .btn (base), .btn--primary (couleur primaire), .btn--secondary (contour) — padding 0.8rem 2rem, border-radius 4px, transition
- Cartes : .card avec box-shadow subtil, border-radius 8px, overflow hidden
- img et .img-placeholder : display block, width 100%, aspect-ratio 4/3, object-fit cover; .img-placeholder avec background gradient gris élégant
- Animations fade-in avec classe .visible (opacity + translateY)
- Sections alternées (fond clair / fond légèrement teinté)
- Footer sobre avec padding généreux

RÈGLES JS (vanilla, aucune librairie) :
- IntersectionObserver → ajoute classe .visible au scroll (threshold 0.15)
- Nav sticky : classe .scrolled après 80px de scroll
- Smooth scroll sur liens d'ancre
- Menu burger mobile (toggle classe .open sur nav){form_info}"""

        typer.echo("   → Génération HTML + CSS + JS en une seule requête...")
        response = self.call_claude_continuable(system_prompt, user_message, max_tokens=8192)
        return self._parse_site_response(response)

    def run(self, context: dict) -> dict:
        typer.echo("🎨 Designer : génération du site...")

        plan   = self.read_json("temp/plan.json")
        textes = self.read_json("temp/textes.json")

        html, css, js = self._generate_site(plan, textes)

        output_dir = self.project.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "assets").mkdir(exist_ok=True)

        (output_dir / "style.css").write_text(css, encoding="utf-8")
        (output_dir / "main.js").write_text(js, encoding="utf-8")

        if self._valider_html(html):
            (output_dir / "index.html").write_text(html, encoding="utf-8")
            typer.echo(f"✅ Site généré → {output_dir}/")
            typer.echo("   • index.html")
            typer.echo("   • style.css")
            typer.echo("   • main.js")
        else:
            self.logger.error("HTML invalide après génération — index.html non écrasé")
            typer.echo("   ❌ HTML incomplet — index.html existant conservé")
            typer.echo(f"   ✅ style.css et main.js écrits → {output_dir}/")

        return {
            "output_dir": str(output_dir),
            "fichiers": ["index.html", "style.css", "main.js"]
        }

    def regenerate_html(self) -> bool:
        """Re-génère index.html depuis le CSS existant sur disque."""
        textes      = self.read_json("temp/textes.json")
        css         = (self.project.output_dir / "style.css").read_text(encoding="utf-8")
        sections    = list(textes.keys())
        sections_str = ", ".join(["nav"] + sections + ["footer"])
        classes_str  = ", ".join(extract_css_classes(css))

        system_prompt = """\
Tu es un développeur web senior.
Tu génères UNIQUEMENT la structure HTML5 complète.
Commence directement par <!DOCTYPE html> et termine obligatoirement par </body></html>."""

        user_message = f"""Génère un index.html complet pour un site vitrine.

Classes CSS disponibles — utilise UNIQUEMENT celles-ci, n'en invente aucune :
{classes_str}

OBLIGATOIRE : <link rel="stylesheet" href="style.css"> dans le <head>
OBLIGATOIRE : <script src="main.js"></script> avant </body>
INTERDIT : balise <style>, CSS inline

Sections dans le <body> : {sections_str}

Textes à intégrer :
{json.dumps(textes, ensure_ascii=False, indent=2)}"""

        html = clean_code_output(
            self.call_claude_continuable(system_prompt, user_message, max_tokens=8192)
        )
        if self._valider_html(html):
            (self.project.output_dir / "index.html").write_text(html, encoding="utf-8")
            self.logger.info("index.html régénéré avec succès")
            return True
        self.logger.error("HTML toujours invalide après regenerate_html")
        return False

    def fix(self, problemes: list, css: str, html: str) -> str:
        """Génère UNIQUEMENT les règles CSS manquantes signalées par le validateur."""
        typer.echo("   🔧 Designer : génération des règles manquantes...")

        classes_manquantes = [p for p in problemes if "absente du CSS" in p]
        if not classes_manquantes:
            typer.echo("   ℹ️  Aucun problème de classe à corriger")
            return ""

        system_prompt = """\
Tu es un développeur CSS expert.
Tu génères UNIQUEMENT les nouvelles règles CSS pour des classes manquantes.
Ne réécris PAS le CSS existant.
Réponds sans balise markdown, juste les règles CSS."""

        noms_classes = []
        for p in classes_manquantes:
            debut = p.find("'") + 1
            fin = p.find("'", debut)
            noms_classes.append(p[debut:fin])

        plan = self.read_json("temp/plan.json")
        couleurs = plan.get("style_guide", {}).get("couleurs", {})
        if isinstance(couleurs, dict):
            couleurs_str = ", ".join(f"{k}: {v}" for k, v in couleurs.items())
        elif isinstance(couleurs, list):
            couleurs_str = ", ".join(couleurs)
        else:
            couleurs_str = "les couleurs définies dans le projet"

        user_message = f"""CSS existant (ne pas réécrire) :
{css}

HTML utilisant les classes manquantes :
{html}

Classes absentes du CSS à styler :
{', '.join(noms_classes)}

Génère UNIQUEMENT les règles CSS pour ces {len(noms_classes)} classes.
Respecte les conventions (BEM, variables CSS) du CSS existant.
Palette du projet : {couleurs_str}."""

        response = self.call_claude_continuable(system_prompt, user_message, max_tokens=2048)
        return clean_code_output(response)
