from __future__ import annotations
import json
import typer
from agents.base_agent import BaseAgent
from utils.project import Project


class SeoAgent(BaseAgent):
    """Génère les métadonnées SEO et les injecte dans le HTML. Agent hybride."""

    def __init__(self, project: Project):
        super().__init__(
            name="seo",
            role="SEO — optimise le site pour les moteurs de recherche",
            project=project
        )

    def _generer_metadonnees(self, config: dict, textes: dict) -> dict:
        """Partie IA : génère les balises meta et le schema.org."""
        typer.echo("   → Génération des métadonnées (IA)...")

        seo_config = config.get("seo", {})
        client = config.get("client", {})

        system_prompt = """Tu es un expert SEO technique.
Tu génères des métadonnées pour un site vitrine, optimisées pour le référencement local.
Réponds UNIQUEMENT en JSON valide, sans balise markdown."""

        user_message = f"""Voici les infos du client :
{json.dumps(client, ensure_ascii=False, indent=2)}

Voici la config SEO :
{json.dumps(seo_config, ensure_ascii=False, indent=2)}

Voici les textes du site :
{json.dumps(textes, ensure_ascii=False, indent=2)}

Produis un JSON avec cette structure exacte :
{{
  "title": "balise title, 55-60 caractères, avec localisation",
  "meta_description": "description engageante, 150-160 caractères",
  "og_title": "titre pour partage réseaux sociaux",
  "og_description": "description pour partage social",
  "keywords": ["mot-clé 1", "mot-clé 2", "..."],
  "schema_org": {{
    "@context": "https://schema.org",
    "@type": "{seo_config.get('type_schema', 'LocalBusiness')}",
    "name": "nom de l'établissement",
    "description": "courte description",
    "address": {{
      "@type": "PostalAddress",
      "addressRegion": "région",
      "addressCountry": "FR"
    }}
  }}
}}"""

        from utils.cleaners import parse_json_safe
        response = self.call_claude(system_prompt, user_message, max_tokens=2048)
        return parse_json_safe(response)

    def _injecter_dans_html(self, meta: dict):
        """Partie mécanique : insère les balises dans le <head> du HTML. Zéro token."""
        typer.echo("   → Injection des balises dans le HTML...")

        html_path = self.project.output_dir / "index.html"

        if not html_path.exists():
            typer.echo("   ⚠️  index.html introuvable — lance le designer d'abord")
            return

        html = html_path.read_text(encoding="utf-8")

        balises = []
        balises.append(f'    <title>{meta["title"]}</title>')
        balises.append(f'    <meta name="description" content="{meta["meta_description"]}">')
        balises.append(f'    <meta name="keywords" content="{", ".join(meta["keywords"])}">')
        balises.append(f'    <meta property="og:title" content="{meta["og_title"]}">')
        balises.append(f'    <meta property="og:description" content="{meta["og_description"]}">')
        balises.append('    <meta property="og:type" content="website">')

        schema_json = json.dumps(meta["schema_org"], ensure_ascii=False, indent=2)
        balises.append(f'    <script type="application/ld+json">\n{schema_json}\n    </script>')

        bloc_seo = "\n".join(balises)

        import re
        if "<title>" in html:
            html = re.sub(r'\s*<title>.*?</title>', '', html, flags=re.DOTALL)

        html = re.sub(
            r'(<head[^>]*>)',
            lambda m: m.group(1) + '\n' + bloc_seo,
            html,
            count=1
        )

        html_path.write_text(html, encoding="utf-8")
        typer.echo("   ✅ Balises SEO injectées dans index.html")

    def _generer_fichiers_seo(self):
        """Génère sitemap.xml et robots.txt. Mécanique, zéro token."""
        typer.echo("   → Génération sitemap.xml et robots.txt...")

        output_dir = self.project.output_dir

        robots = """User-agent: *
Allow: /

Sitemap: sitemap.xml
"""
        (output_dir / "robots.txt").write_text(robots, encoding="utf-8")

        sitemap = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>/index.html</loc>
    <changefreq>monthly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
        (output_dir / "sitemap.xml").write_text(sitemap, encoding="utf-8")
        typer.echo("   ✅ sitemap.xml et robots.txt créés")

    def run(self, context: dict) -> dict:
        typer.echo("🔍 SEO : optimisation du site...")

        config = self.read_json("config.json")
        textes = self.read_json("temp/textes.json")

        meta = self._generer_metadonnees(config, textes)
        self.write_json("temp/seo_meta.json", meta)

        self._injecter_dans_html(meta)
        self._generer_fichiers_seo()

        typer.echo("✅ SEO terminé — métadonnées générées et injectées")
        return meta
