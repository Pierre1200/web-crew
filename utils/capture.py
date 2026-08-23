"""
Capture d'écran du site généré — zéro token, pur Python (Playwright).

Sert de « yeux » à l'agent Critique visuelle : le validateur prouve que le
HTML est valide, jamais qu'il est beau. Pour juger une composition, il faut
la regarder.

Principe : plutôt qu'une seule capture pleine page (qui, sur un site long,
est réduite par le modèle jusqu'à devenir illisible), on prend plusieurs
« tranches » de la hauteur d'un écran, à trois largeurs. Chaque image reste
nette, et le coût en tokens reste maîtrisé (~1700 tokens par tranche).

Installation (une seule fois) :
    pip install playwright
    playwright install chromium
"""
from __future__ import annotations
import math
from pathlib import Path

from utils.cleaners import slugifier

# Formats testés : un téléphone, une tablette, un écran de bureau.
FORMATS = {
    "mobile":   (390, 844),
    "tablette": (820, 1180),
    "bureau":   (1440, 900),
}

# Formats utilisés pour les pages SECONDAIRES (collections). Deux largeurs
# et un seul écran suffisent à repérer un gabarit cassé, sans multiplier
# le nombre d'images envoyées au modèle.
FORMATS_SECONDAIRES = ("mobile", "bureau")
TRANCHES_SECONDAIRES = 1

# Nombre maximal de tranches par format. 3 couvre l'essentiel de la
# composition sans faire exploser le nombre d'images envoyées au modèle.
TRANCHES_MAX = 3

# Neutralise les animations d'apparition AVANT la capture. Sans ça, tout ce
# qui est animé au défilement est photographié à opacity:0 — la critique
# jugerait une page à moitié vide et signalerait des sections « manquantes ».
_CSS_NEUTRALISE_ANIMATIONS = """
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
}
.fade-in, .reveal, [class*="fade"], [class*="reveal"], [data-animate] {
  opacity: 1 !important;
  transform: none !important;
  filter: none !important;
}
"""


class CaptureIndisponible(RuntimeError):
    """Playwright absent ou navigateur non installé — message actionnable."""


def _importer_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise CaptureIndisponible(
            "Playwright n'est pas installé — la critique visuelle a besoin d'un "
            "navigateur pour photographier le site.\n"
            "   Installe-le une seule fois :\n"
            "     pip install playwright\n"
            "     playwright install chromium"
        ) from e
    return sync_playwright


def capturer_site(
    html_path: Path,
    dossier_sortie: Path,
    tranches_max: int = TRANCHES_MAX,
    pages_secondaires: list[Path] | None = None,
) -> list[dict]:
    """Photographie le site et retourne la liste des images.

    La page d'accueil est couverte à trois largeurs sur plusieurs écrans. Les
    `pages_secondaires` (listes de collection, pages de contenu) reçoivent un
    traitement allégé : deux largeurs, un seul écran.

    Pourquoi les inclure : lors du premier run réel, la critique visuelle n'a
    jamais vu les treize pages de collection, soit la majorité du site. C'est
    précisément là que se trouvait le bug des images de couverture.

    Chaque entrée : {"page", "format", "largeur", "tranche",
    "total_tranches", "chemin"}. Les images sont écrites dans
    `dossier_sortie` et écrasées à chaque passage.
    """
    if not html_path.exists():
        raise CaptureIndisponible(f"{html_path} introuvable — génère le site d'abord.")

    sync_playwright = _importer_playwright()
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    url = html_path.resolve().as_uri()
    images: list[dict] = []

    pages = [(html_path, "accueil", tuple(FORMATS), tranches_max)]
    for secondaire in (pages_secondaires or []):
        if secondaire.exists():
            etiquette = secondaire.relative_to(html_path.parent).as_posix()
            pages.append(
                (secondaire, etiquette, FORMATS_SECONDAIRES, TRANCHES_SECONDAIRES)
            )

    with sync_playwright() as p:
        try:
            navigateur = p.chromium.launch()
        except Exception as e:  # navigateur non téléchargé
            raise CaptureIndisponible(
                f"Impossible de lancer Chromium ({e}).\n"
                "   Lance : playwright install chromium"
            ) from e

        try:
            for chemin_page, etiquette, formats, tranches in pages:
                images += _photographier(
                    navigateur, chemin_page, etiquette, formats,
                    tranches, dossier_sortie,
                )
        finally:
            navigateur.close()

    return images


def _photographier(navigateur, chemin_page: Path, etiquette: str,
                   formats, tranches_max: int, dossier_sortie: Path) -> list[dict]:
    """Photographie UNE page, à chacun des formats demandés."""
    url = chemin_page.resolve().as_uri()
    prises: list[dict] = []

    for nom_format in formats:
        largeur, hauteur = FORMATS[nom_format]
        page = navigateur.new_page(
            viewport={"width": largeur, "height": hauteur},
            device_scale_factor=1,
        )
        # Les images distantes (picsum) peuvent traîner : on tente le réseau
        # au repos, et on se contente du chargement de base sinon.
        try:
            page.goto(url, wait_until="networkidle", timeout=15000)
        except Exception:
            page.goto(url, wait_until="load", timeout=15000)

        # Déclenche les IntersectionObserver de haut en bas, puis neutralise
        # les animations : la page est photographiée dans son état final.
        hauteur_totale = page.evaluate("document.body.scrollHeight") or hauteur
        # Borné : sur une page anormalement longue, on ne veut pas passer une
        # minute à faire défiler avant la moindre capture.
        for y in range(0, min(hauteur_totale, hauteur * 30), hauteur):
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(120)
        page.add_style_tag(content=_CSS_NEUTRALISE_ANIMATIONS)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(200)

        total = max(1, min(tranches_max, math.ceil(hauteur_totale / hauteur)))
        prefixe = slugifier(etiquette) or "page"
        for i in range(total):
            page.evaluate(f"window.scrollTo(0, {i * hauteur})")
            page.wait_for_timeout(150)
            chemin = dossier_sortie / f"{prefixe}-{nom_format}-{i + 1}.png"
            page.screenshot(path=str(chemin))  # capture du viewport
            prises.append({
                "page": etiquette,
                "format": nom_format,
                "largeur": largeur,
                "tranche": i + 1,
                "total_tranches": total,
                "chemin": chemin,
            })
        page.close()

    return prises
