"""Tests de la libération des images piégées dans les documents — zéro token.

Les clients collent leurs photos dans Word plutôt que de les joindre. Sans
cette extraction, un .docx de 380 Ko livre 379 caractères de texte et ses
quatre photos restent invisibles.
"""
import struct
import zipfile

from agents.ingestion import DOSSIER_IMAGES_EXTRAITES, IngestionAgent
from utils.extractors import extract_text, extraire_images
from utils.images import dimensions_depuis_octets


def _png(largeur, hauteur, remplissage=0):
    """PNG minimal valide, gonflé pour dépasser le seuil de taille."""
    return (b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", largeur, hauteur)
            + b"\x08\x06\x00\x00\x00" + b"\x00" * remplissage)


def _docx(proj, nom, medias: dict):
    """Fabrique un .docx : c'est une archive ZIP, les images sont dans word/media/."""
    chemin = proj.data_dir / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
        for nom_media, donnees in medias.items():
            archive.writestr(f"word/media/{nom_media}", donnees)
    return chemin


_ODT_CONTENU = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><office:text>
    <text:h text:outline-level="1">Ma démarche</text:h>
    <text:p>Un premier paragraphe.</text:p>
    <text:p>Un mot <text:span>en gras</text:span> au milieu.</text:p>
    <text:p/>
    <text:p>   </text:p>
  </office:text></office:body>
</office:document-content>"""


def _odt(proj, nom, medias: dict | None = None, contenu: str = _ODT_CONTENU):
    """Fabrique un .odt : archive ZIP, texte dans content.xml, images dans Pictures/."""
    chemin = proj.data_dir / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", contenu)
        for nom_media, donnees in (medias or {}).items():
            archive.writestr(f"Pictures/{nom_media}", donnees)
    return chemin


GROSSE = _png(800, 600, remplissage=20_000)      # une vraie photo
PETITE = _png(60, 60, remplissage=20_000)        # trop petite : artefact de mise en page
LEGERE = _png(800, 600, remplissage=100)         # trop légère : filet ou puce


def test_dimensions_depuis_octets():
    assert dimensions_depuis_octets(_png(1200, 800)) == (1200, 800)
    assert dimensions_depuis_octets(b"pas une image") is None


def test_images_extraites_d_un_docx(proj):
    chemin = _docx(proj, "infos.docx", {"image1.png": GROSSE, "image2.png": GROSSE})
    images = extraire_images(chemin)
    assert len(images) == 2
    assert all(donnees.startswith(b"\x89PNG") for _, donnees in images)


def test_texte_extrait_d_un_odt(proj):
    """LibreOffice est courant chez les clients : .odt doit être lu comme .docx."""
    texte = extract_text(_odt(proj, "demarche.odt"))
    lignes = texte.splitlines()
    assert lignes == [
        "Ma démarche",
        "Un premier paragraphe.",
        "Un mot en gras au milieu.",
    ]


def test_odt_recolle_le_texte_coupe_par_la_mise_en_forme(proj):
    """Un mot en gras découpe le paragraphe en <text:span> imbriqués.

    Lire le seul contenu direct de la balise rendrait « Un mot » et perdrait
    la suite : c'est tout le sous-arbre qu'il faut ramasser.
    """
    assert "Un mot en gras au milieu." in extract_text(_odt(proj, "gras.odt"))


def test_images_extraites_d_un_odt(proj):
    chemin = _odt(proj, "photos.odt", {"image1.png": GROSSE, "image2.png": PETITE})
    images = extraire_images(chemin)
    assert [nom for nom, _ in images] == ["image1.png"]


def test_artefacts_de_mise_en_page_ecartes(proj):
    """Filets, puces et images d'espacement ne sont pas des photos."""
    chemin = _docx(proj, "doc.docx", {
        "image1.png": GROSSE,      # gardée
        "image2.png": PETITE,      # 60x60 : écartée
        "image3.png": LEGERE,      # trop légère : écartée
    })
    assert len(extraire_images(chemin)) == 1


def test_format_wdp_de_word_ecarte(proj):
    """Word range une copie HD Photo qu'aucun navigateur ne sait lire."""
    chemin = _docx(proj, "doc.docx", {"image1.png": GROSSE, "hdphoto1.wdp": GROSSE})
    noms = [nom for nom, _ in extraire_images(chemin)]
    assert noms == ["image1.png"]


def test_format_non_gere_retourne_vide(proj):
    fichier = proj.data_dir / "note.txt"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text("du texte", encoding="utf-8")
    assert extraire_images(fichier) == []


def test_document_corrompu_ne_plante_pas(proj):
    """Un fichier récalcitrant ne doit jamais interrompre l'ingestion."""
    fichier = proj.data_dir / "casse.docx"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(b"ceci n'est pas une archive ZIP")
    assert extraire_images(fichier) == []


# ── Intégration dans l'ingestion ───────────────────────────────────────

def test_liberation_nomme_les_images_d_apres_le_document(proj):
    # deux images DIFFÉRENTES : deux fois la même serait dédupliquée, à raison
    _docx(proj, "INFOS PRATIQUES.docx",
          {"image1.png": _png(800, 600, 20_000), "image2.png": _png(1024, 768, 20_000)})
    nouvelles = IngestionAgent(proj)._liberer_images_embarquees()

    assert nouvelles == 2
    dossier = proj.data_dir / DOSSIER_IMAGES_EXTRAITES
    assert sorted(f.name for f in dossier.iterdir()) == [
        "infos-pratiques-1.png", "infos-pratiques-2.png"
    ]


def test_liberation_idempotente(proj):
    """Réécrire les fichiers changerait l'empreinte de data/ et invaliderait le cache."""
    _docx(proj, "doc.docx", {"image1.png": GROSSE})
    agent = IngestionAgent(proj)
    assert agent._liberer_images_embarquees() == 1
    assert agent._liberer_images_embarquees() == 0


def test_liberation_ne_se_relit_pas_elle_meme(proj):
    """Le dossier d'extraction ne doit pas être re-parcouru comme une source."""
    _docx(proj, "doc.docx", {"image1.png": GROSSE})
    agent = IngestionAgent(proj)
    agent._liberer_images_embarquees()
    # un .docx déposé DANS le dossier d'extraction serait ignoré
    _docx(proj, f"{DOSSIER_IMAGES_EXTRAITES}/piege.docx", {"image1.png": GROSSE})
    assert agent._liberer_images_embarquees() == 0


def test_images_liberees_rejoignent_le_flux_normal(proj):
    """Extraites, elles doivent être copiées vers output/assets/ comme les autres."""
    from utils.images import preparer_assets

    _docx(proj, "galerie.docx", {"image1.png": GROSSE})
    IngestionAgent(proj)._liberer_images_embarquees()

    manifeste = preparer_assets(proj)
    fichiers = [i["fichier"] for i in manifeste]
    assert "galerie-1.png" in fichiers
    image = next(i for i in manifeste if i["fichier"] == "galerie-1.png")
    assert (image["largeur"], image["hauteur"]) == (800, 600)
    assert image["orientation"] == "paysage"


def test_sans_document_rien_a_liberer(proj):
    assert IngestionAgent(proj)._liberer_images_embarquees() == 0


def test_meme_image_dans_deux_documents_extraite_une_seule_fois(proj):
    """Un logo répété dans chaque document ne doit pas être proposé cinq fois."""
    _docx(proj, "doc-a.docx", {"logo.png": GROSSE})
    _docx(proj, "doc-b.docx", {"logo.png": GROSSE})

    assert IngestionAgent(proj)._liberer_images_embarquees() == 1
    dossier = proj.data_dir / DOSSIER_IMAGES_EXTRAITES
    assert len(list(dossier.iterdir())) == 1


def test_deduplication_tient_entre_deux_executions(proj):
    _docx(proj, "doc-a.docx", {"logo.png": GROSSE})
    agent = IngestionAgent(proj)
    agent._liberer_images_embarquees()

    _docx(proj, "doc-b.docx", {"logo.png": GROSSE})   # même image, autre document
    assert agent._liberer_images_embarquees() == 0


def test_images_differentes_toutes_conservees(proj):
    _docx(proj, "doc.docx", {"a.png": _png(800, 600, 20_000), "b.png": _png(640, 480, 20_000)})
    assert IngestionAgent(proj)._liberer_images_embarquees() == 2
