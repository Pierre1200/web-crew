"""
Agent Ingestion — digère les données client en désordre.
Lit le dossier data/, extrait le texte de tous les formats,
catalogue les images, puis trie/structure le tout avec l'IA.
"""
from __future__ import annotations
import hashlib
import shutil
import typer
from pathlib import Path
from agents.base_agent import BaseAgent
from utils.extractors import EXTRACTEURS_IMAGES, EXTRACTORS, extract_text, extraire_images
from utils.cleaners import slugifier
from utils.images import dimensions
from utils.cleaners import compact_json

# Extensions d'images qu'on catalogue (sans les lire)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}

# Budget de caractères injectés dans le prompt de tri (~15-20k tokens).
# Garde-fou : sans ça, un client fournissant de gros PDF/DOCX fait exploser
# le contexte et le coût, et peut tronquer le JSON de sortie.
MAX_TEXTE_CHARS = 60_000

# Où atterrissent les photos sorties des documents Word et PDF.
DOSSIER_IMAGES_EXTRAITES = "images-extraites"


class IngestionAgent(BaseAgent):
    """Transforme les données brutes du client en contexte structuré."""

    # Agent CRITIQUE : c'est lui qui décide quel contenu client remonte au reste
    # du pipeline (copywriter inclus). On le maintient volontairement sur un
    # modèle performant + raisonnement adaptatif — NE PAS dégrader pour économiser.
    MODEL = "claude-sonnet-5"
    THINKING = {"type": "adaptive"}
    EFFORT = "high"

    def __init__(self, project):
        super().__init__(
            name="ingestion",
            role="Ingestion — digère et structure les données client",
            project=project,
        )

    # ── ÉTAPE 0 : LIBÉRER LES IMAGES PIÉGÉES (zéro token) ──────────
    def _liberer_images_embarquees(self, rebatir: bool = False) -> int:
        """Sort les photos collées dans les .docx et les .pdf.

        Les clients envoient rarement leurs photos en pièces jointes : ils les
        collent dans un document Word. Un .docx de 380 Ko peut ne contenir que
        379 caractères de texte et quatre photos — que personne ne verrait,
        puisque l'extraction de texte ne lit que les paragraphes.

        Les images sont écrites dans data/images-extraites/ sous un nom dérivé
        du document d'origine, donc elles rejoignent le flux normal : catalogue
        de l'ingestion, puis copie vers output/assets/ par le designer.

        Opération idempotente : un fichier déjà extrait n'est pas réécrit, ce
        qui garde l'empreinte de data/ stable et le cache d'ingestion valide.
        """
        data_dir = self.project.data_dir
        if not data_dir.is_dir():
            return 0

        cible = data_dir / DOSSIER_IMAGES_EXTRAITES

        # L'extraction est idempotente : un fichier déjà sorti n'est pas
        # réécrit. C'est ce qu'on veut au quotidien, mais ça fige aussi le
        # résultat d'un ancien filtrage. Quand les seuils changent, il faut
        # pouvoir tout refaire — d'où `rebatir`, branché sur `ingest --force`.
        # Le dossier est entièrement généré : le vider ne perd rien.
        if rebatir and cible.is_dir():
            anciennes = sum(1 for f in cible.iterdir() if f.is_file())
            shutil.rmtree(cible)
            self.logger.info(f"Images extraites remises à zéro ({anciennes} fichiers)")
            typer.echo(f"   ♻️  {anciennes} image(s) extraite(s) précédemment, remises à zéro")

        # Déduplication par CONTENU. Un logo revient dans chaque document, et
        # deux versions d'un même dossier (« INFOS » et « INFOS-1 ») donnent
        # les mêmes photos : sans cette empreinte, le client verrait la même
        # image proposée cinq fois au designer.
        empreintes = set()
        if cible.is_dir():
            for existant in cible.iterdir():
                if existant.is_file():
                    empreintes.add(hashlib.sha256(existant.read_bytes()).hexdigest())

        nouvelles, doublons = 0, 0

        for document in sorted(data_dir.rglob("*")):
            if not document.is_file() or document.suffix.lower() not in EXTRACTEURS_IMAGES:
                continue
            if cible in document.parents:      # ne pas se relire soi-même
                continue

            images = extraire_images(document)
            if not images:
                continue

            base = slugifier(document.stem) or "document"
            for numero, (nom_origine, donnees) in enumerate(images, start=1):
                empreinte = hashlib.sha256(donnees).hexdigest()
                if empreinte in empreintes:
                    doublons += 1
                    continue

                extension = Path(nom_origine).suffix.lower() or ".png"
                fichier = cible / f"{base}-{numero}{extension}"
                if fichier.exists():
                    continue

                cible.mkdir(parents=True, exist_ok=True)
                fichier.write_bytes(donnees)
                empreintes.add(empreinte)
                nouvelles += 1
                self.logger.info(
                    f"Image libérée : {document.name} → {fichier.name} "
                    f"({len(donnees) // 1024} ko)"
                )

        if nouvelles:
            message = (f"   📎 {nouvelles} image(s) sortie(s) des documents "
                       f"→ data/{DOSSIER_IMAGES_EXTRAITES}/")
            if doublons:
                message += f" ({doublons} doublon(s) écarté(s))"
            typer.echo(message)
        return nouvelles

    # ── CACHE (zéro token) ─────────────────────────────────────────
    def _empreinte_data(self, fichiers: list[Path]) -> str:
        """Empreinte du contenu de data/ : chemin + taille + date de modif.

        Sert de clé de cache. L'ingestion tournait à CHAQUE generate même si
        data/ n'avait pas bougé — ~2-3k tokens Sonnet repayés à chaque run.
        Si l'empreinte n'a pas changé, on réutilise temp/context.json.
        (Analogie C : un checksum du dossier, comme un hash de fichier objet
        pour savoir s'il faut recompiler.)
        """
        h = hashlib.sha256()
        for f in sorted(fichiers):
            st = f.stat()
            ligne = f"{f.relative_to(self.project.data_dir)}|{st.st_size}|{st.st_mtime_ns}\n"
            h.update(ligne.encode("utf-8"))
        return h.hexdigest()

    def _contexte_en_cache(self, empreinte: str) -> dict | None:
        """Retourne le contexte précédent si data/ n'a pas changé, sinon None."""
        path = self.project.temp_dir / "context.json"
        if not path.exists():
            return None
        try:
            cache = self.read_json("temp/context.json")
        except (ValueError, OSError):
            return None
        if cache.get("_empreinte_data") == empreinte:
            return cache
        return None

    # ── BORNAGE DU VOLUME (zéro token) ─────────────────────────────
    def _borner_textes(self, textes: dict) -> dict:
        """Plafonne le volume total de texte injecté dans le prompt IA.

        Tronque document par document, dans l'ordre, jusqu'au budget. Signale
        clairement ce qui a été coupé pour que tu saches qu'il manque du contenu.
        """
        total = sum(len(t) for t in textes.values())
        if total <= MAX_TEXTE_CHARS:
            return textes

        typer.echo(
            f"   ⚠️  {total} caractères extraits > budget {MAX_TEXTE_CHARS} "
            f"— troncature pour tenir dans le contexte"
        )
        self.logger.warning(f"Textes tronqués : {total} > {MAX_TEXTE_CHARS} chars")

        bornes = {}
        restant = MAX_TEXTE_CHARS
        for cle, contenu in textes.items():
            if restant <= 0:
                bornes[cle] = "[…document omis, budget de contexte atteint…]"
            elif len(contenu) > restant:
                bornes[cle] = contenu[:restant] + "\n[…tronqué…]"
                restant = 0
            else:
                bornes[cle] = contenu
                restant -= len(contenu)
        return bornes

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
        """Recense les images avec leurs dimensions réelles (zéro token).

        L'orientation est déterminante pour suggérer un emplacement : un
        portrait vertical n'a pas la même place qu'un panoramique. On lit donc
        l'en-tête de chaque fichier, sans jamais charger l'image entière.
        """
        images = []
        for f in fichiers:
            if f.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            entree = {
                "nom": f.name,
                "chemin": str(f.relative_to(self.project.data_dir)),
                "taille_ko": round(f.stat().st_size / 1024, 1),
            }
            taille = dimensions(f)
            if taille:
                largeur, hauteur = taille
                entree["dimensions"] = f"{largeur}x{hauteur}"
                entree["orientation"] = (
                    "paysage" if largeur > hauteur * 1.05
                    else "portrait" if hauteur > largeur * 1.05
                    else "carré"
                )
            images.append(entree)
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
{compact_json(sections)}

Voici les textes bruts extraits des fichiers du client :
{compact_json(textes)}

Voici les images disponibles :
{compact_json(images)}

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

        # Continuable + auto : le JSON de sortie doit être complet pour être
        # parsé, et l'ingestion tourne comme pré-étape non interactive.
        response = self.call_claude_continuable(
            system_prompt, user_message, max_tokens=16000, auto_continue=True
        )
        return self.parse_json_response(response)

    # ── ÉTAPE 5 : ORCHESTRATION DES ÉTAPES ─────────────────────────
    def run(self, context: dict) -> dict:
        typer.echo("🗂  Ingestion : digestion des données client...")

        config = self.load_config()

        # Étape 0 : libérer les photos piégées dans les documents. AVANT la
        # collecte et l'empreinte, pour que les images extraites soient
        # cataloguées dès ce run et que le cache reste cohérent.
        self._liberer_images_embarquees(rebatir=bool(context.get("force")))

        # Étape 1 : collecte
        fichiers = self._collecter_fichiers()
        if not fichiers:
            typer.echo("   ℹ️  Aucune donnée dans data/ — ingestion sautée")
            return {"vide": True}
        typer.echo(f"   → {len(fichiers)} fichier(s) trouvé(s)")

        # Cache : si data/ n'a pas changé depuis la dernière ingestion,
        # on réutilise le contexte existant sans appel IA (--force pour ignorer)
        empreinte = self._empreinte_data(fichiers)
        if not context.get("force"):
            cache = self._contexte_en_cache(empreinte)
            if cache is not None:
                typer.echo("   ♻️  data/ inchangé — contexte réutilisé (0 token)")
                self.logger.info("Cache d'ingestion réutilisé (empreinte identique)")
                return cache

        # Étape 2 : extraction texte
        textes = self._extraire_textes(fichiers)
        typer.echo(f"   → {len(textes)} document(s) texte extrait(s)")

        # Étape 3 : catalogage images
        images = self._cataloguer_images(fichiers)
        typer.echo(f"   → {len(images)} image(s) cataloguée(s)")

        # Étape 4 : tri intelligent (IA) — seulement s'il y a du texte
        if textes:
            textes = self._borner_textes(textes)
            contexte = self._trier_avec_ia(textes, images, config)
        else:
            contexte = {"contenu_par_theme": {}, "images_suggerees": [],
                        "manques": ["aucun texte fourni"], "resume": "Images seulement."}

        # Ajoute le catalogue brut au contexte + l'empreinte pour le cache
        contexte["images_brutes"] = images
        contexte["_empreinte_data"] = empreinte

        # Sauvegarde
        self.write_json("temp/context.json", contexte)
        typer.echo("✅ Contexte structuré → temp/context.json")

        # Affiche les manques (très utile pour toi)
        if contexte.get("manques"):
            typer.echo("\n   📋 Ce qui manque pour un bon site :")
            for manque in contexte["manques"]:
                typer.echo(f"      • {manque}")

        return contexte