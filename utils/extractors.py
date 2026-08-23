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

# Les PDF sont autrement plus bavards que les documents Word. Un livret mis en
# page peut rendre une centaine de morceaux : bandeaux découpés, vignettes de
# catalogue, fragments de fond. Le premier run réel en a sorti 103, dont la
# quasi-totalité inutilisables, qui sont ensuite allées polluer le manifeste
# soumis au designer. Seuils volontairement plus sévères, donc.
_PDF_COTE_MINI_PIXELS = 400
_PDF_MAX_PAR_DOCUMENT = 20

# Un rapport de forme extrême trahit une bande de mise en page, pas une photo.
_RATIO_MAXI = 5.0

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


def extract_odt(path: Path) -> str:
    """Extrait le texte d'un document LibreOffice / OpenOffice.

    Un .odt est une archive ZIP dont le texte vit dans content.xml. Chaque
    paragraphe est un <text:p>, chaque titre un <text:h>, et le texte réel
    peut être découpé en <text:span> imbriqués dès qu'un mot est en gras.
    D'où itertext(), qui ramasse tout le texte d'un sous-arbre au lieu de
    lire le seul contenu direct de la balise.

    Aucune dépendance : zipfile et ElementTree sont dans la bibliothèque
    standard, contrairement au .docx qui passe par python-docx.
    """
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as archive:
        racine = ET.fromstring(archive.read("content.xml"))

    ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    lignes = []
    for bloc in racine.iter():
        if bloc.tag in (f"{ns}p", f"{ns}h"):
            texte = "".join(bloc.itertext()).strip()
            if texte:
                lignes.append(texte)
    return "\n".join(lignes)


EXTRACTORS = {
    ".txt": extract_txt,
    ".md": extract_txt,
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".odt": extract_odt,
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


def _images_odt(path: Path) -> list[tuple[str, bytes]]:
    """Images embarquées dans un .odt, rangées dans Pictures/."""
    images = []
    with zipfile.ZipFile(path) as archive:
        for nom in sorted(archive.namelist()):
            if not nom.startswith("Pictures/"):
                continue
            if Path(nom).suffix.lower() not in _FORMATS_IMAGES_UTILES:
                continue
            images.append((Path(nom).name, archive.read(nom)))
    return images


EXTRACTEURS_IMAGES = {
    ".docx": _images_docx,
    ".pdf": _images_pdf,
    ".odt": _images_odt,
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
    est_pdf = path.suffix.lower() == ".pdf"
    cote_mini = _PDF_COTE_MINI_PIXELS if est_pdf else _COTE_MINI_PIXELS

    for nom, donnees in images:
        if len(donnees) < _TAILLE_MINI_OCTETS:
            continue
        taille = dimensions_depuis_octets(donnees)
        if taille:
            if max(taille) < cote_mini:
                continue
            # Bande de mise en page : très longue et très fine, ou l'inverse.
            grand, petit = max(taille), min(taille)
            if petit and grand / petit > _RATIO_MAXI:
                continue
        utiles.append((nom, donnees, taille))

    # Un PDF qui rend plus d'une vingtaine d'images est un document mis en
    # page, pas un album photo : on ne garde que les plus grandes, qui sont
    # les seules susceptibles d'être de vraies illustrations.
    if est_pdf and len(utiles) > _PDF_MAX_PAR_DOCUMENT:
        utiles.sort(
            key=lambda e: (e[2][0] * e[2][1]) if e[2] else len(e[1]), reverse=True
        )
        utiles = utiles[:_PDF_MAX_PAR_DOCUMENT]
        print(
            f"   ℹ️  {path.name} : {_PDF_MAX_PAR_DOCUMENT} images retenues sur "
            f"{len(images)}, les plus grandes (document mis en page)"
        )

    return [(nom, donnees) for nom, donnees, _ in utiles]


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