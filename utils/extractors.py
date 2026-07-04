"""
Extraction de texte depuis différents formats de fichiers.
Utilisé par l'agent Ingestion pour lire les données client en désordre.
Zéro token — pur Python, aucun appel IA.
"""
from pathlib import Path


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