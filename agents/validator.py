from __future__ import annotations
import re
import typer
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import extract_css_classes

# Classes ajoutées dynamiquement par main.js — absentes du CSS statique, c'est normal
_JS_DYNAMIC_CLASSES = {"visible", "scrolled", "open", "active", "loaded", "is-open", "is-active"}


class ValidatorAgent(BaseAgent):
    """Inspecte le site généré et détecte les problèmes — sans appeler l'IA."""

    def __init__(self, project: Project):
        super().__init__(
            name="validator",
            role="Validateur — contrôle qualité du site généré",
            project=project
        )
        self.problemes = []

    def _lire(self, fichier: str) -> str:
        """Lit un fichier du dossier de sortie du projet."""
        path = self.project.output_dir / fichier
        if not path.exists():
            self.problemes.append(f"❌ Fichier manquant : {fichier}")
            return ""
        return path.read_text(encoding="utf-8")

    def check_html_complet(self, html: str, sections_keywords: list = None):
        """Vérifie que le HTML n'est pas tronqué."""
        if not html:
            return
        if "</html>" not in html:
            self.problemes.append("❌ HTML tronqué : balise </html> manquante")
        if "<body" not in html:
            self.problemes.append("❌ HTML incomplet : pas de <body>")
        for section in (sections_keywords or []):
            if section not in html.lower():
                self.problemes.append(f"⚠️  Section possiblement manquante : {section}")

    def check_classes_coherentes(self, html: str, css: str):
        """Pour chaque classe du HTML, vérifie qu'elle existe dans le CSS."""
        if not html or not css:
            return

        classes_html = set()
        for match in re.findall(r'class="([^"]*)"', html):
            for classe in match.split():
                classes_html.add(classe)

        classes_css = set(extract_css_classes(css))

        for classe in classes_html:
            if classe not in classes_css and classe not in _JS_DYNAMIC_CLASSES:
                self.problemes.append(
                    f"⚠️  Classe '{classe}' utilisée dans le HTML mais absente du CSS"
                )

    def check_liens_fichiers(self, html: str):
        """Vérifie que le HTML lie bien le CSS et le JS."""
        if not html:
            return
        if 'href="style.css"' not in html:
            self.problemes.append("❌ Lien vers style.css manquant dans le HTML")
        if 'src="main.js"' not in html:
            self.problemes.append("❌ Lien vers main.js manquant dans le HTML")

    def check_js_complet(self, js: str):
        """Détecte un JS tronqué en comptant les accolades."""
        if not js:
            return
        ouvrantes = js.count("{")
        fermantes = js.count("}")
        if ouvrantes != fermantes:
            self.problemes.append(
                f"❌ JS possiblement tronqué : {ouvrantes} '{{' mais {fermantes} '}}'"
            )

    def run(self, context: dict) -> dict:
        typer.echo("✅ Validateur : inspection du site...")
        self.problemes = []

        sections_keywords = []
        try:
            textes = self.read_json("temp/textes.json")
            sections_keywords = [k.replace("_", "-") for k in textes.keys()]
        except Exception:
            pass

        html = self._lire("index.html")
        css = self._lire("style.css")
        js = self._lire("main.js")

        self.check_html_complet(html, sections_keywords)
        self.check_classes_coherentes(html, css)
        self.check_liens_fichiers(html)
        self.check_js_complet(js)

        if not self.problemes:
            typer.echo("✅ Aucun problème détecté — le site est valide !")
        else:
            typer.echo(f"⚠️  {len(self.problemes)} problème(s) détecté(s) :")
            for p in self.problemes:
                typer.echo(f"   {p}")

        return {"problemes": self.problemes, "valide": len(self.problemes) == 0}
