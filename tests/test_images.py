"""Tests de la préparation des vraies images — zéro token, zéro API.

Le décodage d'en-têtes binaires est du code sensible : une erreur d'offset
donne des dimensions fausses, donc des width/height faux dans le HTML livré,
donc une page qui saute au chargement. On vérifie chaque format sur un
en-tête construit à la main, avec des dimensions volontairement asymétriques
(largeur ≠ hauteur) pour attraper toute inversion.
"""
import struct

from utils.images import (
    EXTENSIONS_IMAGES,
    dimensions,
    images_lourdes,
    nom_web,
    preparer_assets,
)


# ── Fabrication d'en-têtes valides (le contenu image n'a pas d'importance) ──

def _png(largeur, hauteur):
    return (b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", largeur, hauteur)
            + b"\x08\x06\x00\x00\x00" + b"\x00" * 16)


def _gif(largeur, hauteur):
    return b"GIF89a" + struct.pack("<HH", largeur, hauteur) + b"\x00" * 16


def _jpeg(largeur, hauteur):
    # Un segment APP0 à sauter, PUIS le SOF0 : vérifie que le parcours
    # de segments fonctionne et ne lit pas simplement à un offset fixe.
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = (b"\xff\xc0" + struct.pack(">H", 17) + b"\x08"
            + struct.pack(">HH", hauteur, largeur) + b"\x03" + b"\x00" * 9)
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


def _webp_lossy(largeur, hauteur):
    # Structure VP8 : 3 octets d'étiquette de trame, puis le code de
    # synchronisation, puis les dimensions sur 14 bits chacune.
    corps = (b"VP8 " + struct.pack("<I", 24)
             + b"\x00" * 3 + b"\x9d\x01\x2a"
             + struct.pack("<HH", largeur, hauteur) + b"\x00" * 4)
    return b"RIFF" + struct.pack("<I", len(corps) + 4) + b"WEBP" + corps


def _webp_extended(largeur, hauteur):
    corps = (b"VP8X" + struct.pack("<I", 10) + b"\x00" * 4
             + (largeur - 1).to_bytes(3, "little")
             + (hauteur - 1).to_bytes(3, "little"))
    return b"RIFF" + struct.pack("<I", len(corps) + 4) + b"WEBP" + corps


SVG_ATTRIBUTS = b'<svg xmlns="http://www.w3.org/2000/svg" width="388" height="189"></svg>'
SVG_VIEWBOX = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450"></svg>'


def _ecrire(proj, nom, donnees, dossier="data"):
    cible = getattr(proj, f"{dossier}_dir") / nom
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(donnees)
    return cible


# ── Dimensions par format ──────────────────────────────────────────────

def test_dimensions_png(proj):
    assert dimensions(_ecrire(proj, "a.png", _png(1200, 800))) == (1200, 800)


def test_dimensions_gif(proj):
    assert dimensions(_ecrire(proj, "a.gif", _gif(320, 240))) == (320, 240)


def test_dimensions_jpeg_apres_segment_a_sauter(proj):
    assert dimensions(_ecrire(proj, "a.jpg", _jpeg(1920, 1080))) == (1920, 1080)


def test_dimensions_webp_avec_perte(proj):
    assert dimensions(_ecrire(proj, "a.webp", _webp_lossy(640, 480))) == (640, 480)


def test_dimensions_webp_etendu(proj):
    assert dimensions(_ecrire(proj, "b.webp", _webp_extended(2000, 1500))) == (2000, 1500)


def test_dimensions_svg_par_attributs(proj):
    assert dimensions(_ecrire(proj, "a.svg", SVG_ATTRIBUTS)) == (388, 189)


def test_dimensions_svg_par_viewbox(proj):
    assert dimensions(_ecrire(proj, "b.svg", SVG_VIEWBOX)) == (800, 450)


def test_extension_mensongere_detectee_par_signature(proj):
    """L'extension ment parfois : c'est la signature qui fait foi."""
    assert dimensions(_ecrire(proj, "faux.jpg", _png(500, 250))) == (500, 250)


def test_fichier_illisible_retourne_none(proj):
    assert dimensions(_ecrire(proj, "a.png", b"pas une image")) is None


# ── Normalisation des noms ─────────────────────────────────────────────

def test_nom_web_normalise_espaces_accents_et_casse():
    assert nom_web("1.2 La Charte Graphique 2025.PNG") == "1-2-la-charte-graphique-2025.png"
    assert nom_web("Portrait Denis Moulin.jpg") == "portrait-denis-moulin.jpg"
    assert nom_web("été à la mer.JPEG") == "ete-a-la-mer.jpeg"


def test_nom_web_gere_les_ligatures():
    assert nom_web("œuvre n°3.png") == "oeuvre-n3.png"


def test_nom_web_jamais_vide():
    assert nom_web("---.png") == "image.png"


# ── Manifeste ──────────────────────────────────────────────────────────

def test_manifeste_copie_les_images_de_data(proj):
    _ecrire(proj, "Mon Portrait.png", _png(1200, 1600))
    manifeste = preparer_assets(proj)

    assert len(manifeste) == 1
    image = manifeste[0]
    assert image["chemin_web"] == "assets/mon-portrait.png"
    assert (proj.output_dir / "assets" / "mon-portrait.png").exists()
    assert (image["largeur"], image["hauteur"]) == (1200, 1600)
    assert image["ratio"] == "3 / 4"
    assert image["orientation"] == "portrait"
    assert image["nom_origine"] == "Mon Portrait.png"


def test_manifeste_inclut_les_assets_deposes_a_la_main(proj):
    """Un logo déjà placé dans output/assets/ ne doit pas être ignoré."""
    dossier = proj.output_dir / "assets"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "logo.svg").write_bytes(SVG_ATTRIBUTS)

    manifeste = preparer_assets(proj)
    logos = [i for i in manifeste if i["fichier"] == "logo.svg"]
    assert len(logos) == 1
    assert logos[0]["source"] == "assets"


def test_manifeste_ignore_les_non_images(proj):
    _ecrire(proj, "brief.docx", b"PK\x03\x04 contenu word")
    assert preparer_assets(proj) == []


def test_manifeste_reprend_les_suggestions_de_l_ingestion(proj):
    _ecrire(proj, "Portrait.jpg", _jpeg(800, 1000))
    contexte = {"images_suggerees": [
        {"nom": "Portrait.jpg", "section_suggeree": "hero",
         "raison": "portrait du réalisateur"}
    ]}
    image = preparer_assets(proj, contexte)[0]
    assert image["section_suggeree"] == "hero"
    assert image["description"] == "portrait du réalisateur"


def test_manifeste_est_idempotent(proj):
    _ecrire(proj, "a.png", _png(10, 10))
    assert len(preparer_assets(proj)) == 1
    assert len(preparer_assets(proj)) == 1  # pas de doublon au second passage


def test_orientation_paysage_et_carre(proj):
    _ecrire(proj, "large.png", _png(1600, 900))
    _ecrire(proj, "carre.png", _png(500, 500))
    par_nom = {i["fichier"]: i for i in preparer_assets(proj)}
    assert par_nom["large.png"]["orientation"] == "paysage"
    assert par_nom["carre.png"]["orientation"] == "carré"


def test_images_lourdes_signalees():
    manifeste = [{"fichier": "a.jpg", "poids_ko": 1500},
                 {"fichier": "b.jpg", "poids_ko": 90}]
    assert [i["fichier"] for i in images_lourdes(manifeste)] == ["a.jpg"]


def test_svg_fait_partie_des_extensions_gerees():
    assert ".svg" in EXTENSIONS_IMAGES and ".webp" in EXTENSIONS_IMAGES
