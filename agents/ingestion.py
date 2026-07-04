"""
Agent Ingestion — digère les données client en désordre.
Lit le dossier data/, extrait le texte de tous les formats,
catalogue les images, puis trie/structure le tout avec l'IA.
"""
from __future__ import annotations
import json
import typer
from pathlib import Path
from agents.base_agent import BaseAgent
from utils.extractors import extract_text, EXTRACTORS
from utils.cleaners import parse_json_safe

# Extensions d'images qu'on catalogue (sans les lire)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


class IngestionAgent(BaseAgent):
    """Transforme les données brutes du client en contexte structuré."""

    def __init__(self, project):
        super().__init__(
            name="ingestion",
            role="Ingestion — digère et structure les données client",
            project=project,
        )

    # ── ÉTAPE 1 : COLLECTE (zéro token) ────────────────────────────
    def _collecter_fichiers(self) -> list[Path]:
        """Parcourt data/ récursivement et liste tous les fichiers."""
        data_dir = self.project.data_dir
        if not data_dir.exists():
            return []
        # rglob("*") parcourt récursivement tous les fichiers et sous-dossiers
        return [f for f in data_dir.rglob("*") if f.is_file()]

    # ── ÉTAPE 2 : EXTRACTION TEXTE (zéro token) ────────────────────
    def _extraire_textes(self, fichiers: list[Path]) -> dict:
        """Extrait le texte de tous les documents lisibles."""
        textes = {}
        for f in fichiers:
            if f.suffix.lower() in EXTRACTORS:
                contenu = extract_text(f)
                if contenu.strip():
                    # clé = chemin relatif au data_dir, plus lisible
                    cle = str(f.relative_to(self.project.data_dir))
                    textes[cle] = contenu
        return textes

    # ── ÉTAPE 3 : CATALOGAGE IMAGES (zéro token) ───────────────────
    def _cataloguer_images(self, fichiers: list[Path]) -> list[dict]:
        """Recense les images sans les lire (nom, chemin, taille)."""
        images = []
        for f in fichiers:
            if f.suffix.lower() in IMAGE_EXTENSIONS:
                images.append({
                    "nom": f.name,
                    "chemin": str(f.relative_to(self.project.data_dir)),
                    "taille_ko": round(f.stat().st_size / 1024, 1),
                })
        return images

    # ── ÉTAPE 4 : TRI INTELLIGENT (IA) ─────────────────────────────
    def _trier_avec_ia(self, textes: dict, images: list[dict], config: dict) -> dict:
        """Le cœur : Claude organise le contenu brut par thème."""
        typer.echo("   → Tri intelligent du contenu (IA)...")

        sections = config.get("site", {}).get("sections", [])

        system_prompt = """Tu es un assistant qui structure des données client brutes \
pour préparer la création d'un site web.
On te donne des textes en vrac (extraits de fichiers) et une liste d'images.
Tu organises ce contenu par thème, tu identifies ce qui est utile, \
et tu signales ce qui manque.
Réponds UNIQUEMENT en JSON valide, sans balise markdown."""

        user_message = f"""Voici les sections prévues pour le site :
{json.dumps(sections, ensure_ascii=False, indent=2)}

Voici les textes bruts extraits des fichiers du client :
{json.dumps(textes, ensure_ascii=False, indent=2)}

Voici les images disponibles :
{json.dumps(images, ensure_ascii=False, indent=2)}

Produis un JSON avec cette structure :
{{
  "contenu_par_theme": {{
    "nom_du_theme": "contenu pertinent rassemblé et nettoyé"
  }},
  "images_suggerees": [
    {{"nom": "...", "section_suggeree": "...", "raison": "..."}}
  ],
  "manques": [
    "ce qui manque pour faire un bon site (ex: pas d'horaires, bio d'artiste absente)"
  ],
  "resume": "résumé en 2-3 phrases de ce que le client a fourni"
}}"""

        response = self.call_claude(system_prompt, user_message, max_tokens=4096)
        return parse_json_safe(response)

    # ── ÉTAPE 5 : ORCHESTRATION DES ÉTAPES ─────────────────────────
    def run(self, context: dict) -> dict:
        typer.echo("🗂  Ingestion : digestion des données client...")

        config = self.project.load_config()

        # Étape 1 : collecte
        fichiers = self._collecter_fichiers()
        if not fichiers:
            typer.echo("   ℹ️  Aucune donnée dans data/ — ingestion sautée")
            return {"vide": True}
        typer.echo(f"   → {len(fichiers)} fichier(s) trouvé(s)")

        # Étape 2 : extraction texte
        textes = self._extraire_textes(fichiers)
        typer.echo(f"   → {len(textes)} document(s) texte extrait(s)")

        # Étape 3 : catalogage images
        images = self._cataloguer_images(fichiers)
        typer.echo(f"   → {len(images)} image(s) cataloguée(s)")

        # Étape 4 : tri intelligent (IA) — seulement s'il y a du texte
        if textes:
            contexte = self._trier_avec_ia(textes, images, config)
        else:
            contexte = {"contenu_par_theme": {}, "images_suggerees": [],
                        "manques": ["aucun texte fourni"], "resume": "Images seulement."}

        # Ajoute le catalogue brut au contexte
        contexte["images_brutes"] = images

        # Sauvegarde
        self.write_json("temp/context.json", contexte)
        typer.echo("✅ Contexte structuré → temp/context.json")

        # Affiche les manques (très utile pour toi)
        if contexte.get("manques"):
            typer.echo("\n   📋 Ce qui manque pour un bon site :")
            for manque in contexte["manques"]:
                typer.echo(f"      • {manque}")

        return contexte