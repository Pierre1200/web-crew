"""
Extraction depuis les documents fournis par le client — texte ET images.
Utilisé par l'agent Ingestion pour lire les données client en désordre.
Zéro token — pur Python, aucun appel IA.

Les clients envoient rarement des fichiers bien rangés : ils collent leurs
photos DANS un document Word ou un PDF. Un .docx de 380 Ko peut ne contenir
que 379 caractères de texte et quatre photos — invisibles pour qui ne lit que
les paragraphes. D'où l'extraction des images embarquées : sans elle, les
vraies photos du client n'atteignent jamais le site.
"""
import zipfile
from pathlib import Path

# En dessous, c'est presque toujours un artefact de mise en page (filet,
# puce, image d'espacement) plutôt qu'une photo à publier.
_TAILLE_MINI_OCTETS = 5 * 1024
_COTE_MINI_PIXELS = 120

# Word range parfois une copie « HD Photo » (.wdp) à côté du PNG : aucun
# navigateur ne la lit, et c'est un doublon de l'image voisine.
_FORMATS_IMAGES_UTILES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def extract_txt(path: Path) -> str:
    """Lit un fichier texte brut (.txt, .md)."""
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_pdf(path: Path) -> str:
    """Extrait le texte d'un PDF avec pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    morceaux = []
    for page in reader.pages:
        texte_page = page.extract_text()
        if texte_page:
            morceaux.append(texte_page)
    return "\n".join(morceaux)


def extract_docx(path: Path) -> str:
    """Extrait le texte d'un document Word avec python-docx."""
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text)


EXTRACTORS = {
    ".txt": extract_txt,
    ".md": extract_txt,
    ".pdf": extract_pdf,
    ".docx": extract_docx,
}


def _images_docx(path: Path) -> list[tuple[str, bytes]]:
    """Images embarquées dans un .docx.

    Un document Word est une archive ZIP : les images vivent dans word/media/.
    On les lit directement, sans passer par python-docx qui n'expose que les
    paragraphes.
    """
    images = []
    with zipfile.ZipFile(path) as archive:
        for nom in sorted(archive.namelist()):
            if not nom.startswith("word/media/"):
                continue
            if Path(nom).suffix.lower() not in _FORMATS_IMAGES_UTILES:
                continue
            images.append((Path(nom).name, archive.read(nom)))
    return images


def _images_pdf(path: Path) -> list[tuple[str, bytes]]:
    """Images embarquées dans un PDF, page après page."""
    from pypdf import PdfReader

    images = []
    for numero, page in enumerate(PdfReader(str(path)).pages, start=1):
        for image in page.images:
            suffixe = Path(image.name).suffix.lower() or ".png"
            if suffixe not in _FORMATS_IMAGES_UTILES:
                continue
            images.append((f"p{numero}-{Path(image.name).name}", image.data))
    return images


EXTRACTEURS_IMAGES = {
    ".docx": _images_docx,
    ".pdf": _images_pdf,
}


def extraire_images(path: Path) -> list[tuple[str, bytes]]:
    """Images embarquées dans un document, filtrées de leurs artefacts.

    Retourne une liste de (nom d'origine, contenu binaire). Liste vide si le
    format ne contient pas d'images ou si l'extraction échoue — un document
    récalcitrant ne doit jamais interrompre l'ingestion.
    """
    extracteur = EXTRACTEURS_IMAGES.get(path.suffix.lower())
    if extracteur is None:
        return []

    try:
        images = extracteur(path)
    except Exception as e:
        print(f"   ⚠️  Images illisibles dans {path.name} : {e}")
        return []

    # Le filtrage a besoin des dimensions : import tardif pour éviter une
    # dépendance circulaire (utils.images lit déjà les en-têtes binaires).
    from utils.images import dimensions_depuis_octets

    utiles = []
    for nom, donnees in images:
        if len(donnees) < _TAILLE_MINI_OCTETS:
            continue
        taille = dimensions_depuis_octets(donnees)
        if taille and max(taille) < _COTE_MINI_PIXELS:
            continue
        utiles.append((nom, donnees))
    return utiles


def extract_text(path: Path) -> str:
    """
    Regarde l'extension et appelle la bonne extraction.
    Retourne le texte, ou une chaîne vide si le format n'est pas géré
    ou si l'extraction échoue.
    """
    extension = path.suffix.lower()
    extracteur = EXTRACTORS.get(extension)

    if extracteur is None:
        return ""

    try:
        return extracteur(path)
    except Exception as e:
        print(f"   ⚠️  Impossible de lire {path.name} : {e}")
        return ""