"""Tests de la critique visuelle — sans navigateur ni appel API.

On teste tout ce qui est mécanique : l'assemblage du message mixte
(texte + images), l'encodage des images, et l'application des correctifs CSS
proposés par la critique (qui, elle, ne coûte aucun token).
"""
import base64

from agents.designer import DesignerAgent
from agents.visuel import VisuelAgent

# 1 pixel PNG transparent — suffisant pour vérifier l'encodage
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _image(proj, nom="bureau-1.png"):
    chemin = proj.logs_dir / nom
    chemin.write_bytes(PNG_1PX)
    return chemin


def test_bloc_image_encode_en_base64(proj):
    bloc = VisuelAgent(proj).build_bloc_image(_image(proj))
    assert bloc["type"] == "image"
    assert bloc["source"]["media_type"] == "image/png"
    # la donnée doit être du base64 décodable, redonnant l'image d'origine
    assert base64.b64decode(bloc["source"]["data"]) == PNG_1PX


def test_construire_blocs_legende_chaque_image(proj):
    images = [
        {"format": "bureau", "largeur": 1440, "tranche": 1,
         "total_tranches": 2, "chemin": _image(proj, "b1.png")},
        {"format": "mobile", "largeur": 390, "tranche": 2,
         "total_tranches": 2, "chemin": _image(proj, "m2.png")},
    ]
    blocs = VisuelAgent(proj)._construire_blocs(images, "CONTEXTE")

    # 1 bloc de contexte + (1 légende + 1 image) par capture
    assert len(blocs) == 5
    assert blocs[0]["text"] == "CONTEXTE"
    assert "bureau" in blocs[1]["text"] and "1440px" in blocs[1]["text"]
    assert blocs[2]["type"] == "image"
    assert "mobile" in blocs[3]["text"] and "2/2" in blocs[3]["text"]
    assert blocs[4]["type"] == "image"


def test_correctifs_css_ajoutes_en_fin_de_feuille(proj):
    """Les correctifs sont AJOUTÉS : la cascade CSS fait qu'ils l'emportent."""
    css_path = proj.output_dir / "style.css"
    css_path.write_text(".hero { padding: 1rem; }", encoding="utf-8")

    problemes = [
        {"gravite": "majeur", "zone": "hero", "format": "bureau",
         "constat": "Respiration insuffisante",
         "correction_css": ".hero { padding: 6rem 2rem; }"},
        {"gravite": "mineur", "zone": "footer", "format": "tous",
         "constat": "Contraste faible", "correction_css": ""},  # non corrigeable
    ]
    appliques = DesignerAgent(proj).appliquer_correctifs_css(problemes)

    assert appliques == 1
    css = css_path.read_text(encoding="utf-8")
    assert css.startswith(".hero { padding: 1rem; }")       # l'existant est conservé
    assert css.index("6rem 2rem") > css.index("1rem")        # le correctif vient après
    assert "critique visuelle" in css                        # bloc identifiable
    assert "Respiration insuffisante" in css                 # traçabilité du pourquoi


def test_correctifs_places_hors_layer_pour_l_emporter(proj):
    """Une règle hors couche bat toute règle en couche, quelle que soit sa
    spécificité : c'est ce qui rend la correction automatique fiable."""
    css_path = proj.output_dir / "style.css"
    css_path.write_text(
        "@layer reset, base, composants;\n"
        "@layer composants { .section .hero { padding: 1rem; } }",
        encoding="utf-8",
    )
    problemes = [{"gravite": "majeur", "zone": "hero", "constat": "trop serré",
                  "correction_css": ".hero { padding: 6rem; }"}]
    DesignerAgent(proj).appliquer_correctifs_css(problemes)

    css = css_path.read_text(encoding="utf-8")
    correctif = css[css.index("Correctifs issus"):]
    # le correctif ne doit surtout pas être enfermé dans une couche
    assert "@layer" not in correctif
    assert ".hero { padding: 6rem; }" in correctif
    assert "l'emportent sur toutes les couches" in css


def test_feuille_sans_layer_signale_la_fragilite(proj):
    css_path = proj.output_dir / "style.css"
    css_path.write_text(".hero { padding: 1rem; }", encoding="utf-8")
    problemes = [{"gravite": "majeur", "zone": "hero", "constat": "x",
                  "correction_css": ".hero { padding: 6rem; }"}]
    DesignerAgent(proj).appliquer_correctifs_css(problemes)

    css = css_path.read_text(encoding="utf-8")
    assert "Feuille sans couches" in css


def test_correctifs_nettoient_les_fences_markdown(proj):
    (proj.output_dir / "style.css").write_text("body{}", encoding="utf-8")
    problemes = [{"gravite": "majeur", "zone": "nav", "constat": "x",
                  "correction_css": "```css\n.nav { height: 80px; }\n```"}]
    DesignerAgent(proj).appliquer_correctifs_css(problemes)
    css = (proj.output_dir / "style.css").read_text(encoding="utf-8")
    assert "```" not in css
    assert ".nav { height: 80px; }" in css


def test_aucun_correctif_ne_touche_pas_le_css(proj):
    css_path = proj.output_dir / "style.css"
    css_path.write_text("body{}", encoding="utf-8")
    assert DesignerAgent(proj).appliquer_correctifs_css([]) == 0
    assert css_path.read_text(encoding="utf-8") == "body{}"


def test_correctifs_sans_css_existant_ne_plante_pas(proj):
    problemes = [{"gravite": "majeur", "zone": "hero", "constat": "x",
                  "correction_css": ".a{}"}]
    assert DesignerAgent(proj).appliquer_correctifs_css(problemes) == 0


def test_commentaire_correctif_ne_casse_pas_le_css(proj):
    """Un constat contenant */ fermerait le commentaire et casserait la feuille."""
    (proj.output_dir / "style.css").write_text("body{}", encoding="utf-8")
    problemes = [{"gravite": "majeur", "zone": "hero",
                  "constat": "texte piégeux */ body { display: none }",
                  "correction_css": ".hero{color:red}"}]
    DesignerAgent(proj).appliquer_correctifs_css(problemes)
    css = (proj.output_dir / "style.css").read_text(encoding="utf-8")
    assert "display: none" not in css.split("*/")[0]
    assert css.count("/*") == css.count("*/")


# ── L'ÉCHANTILLON DE PAGES SUR UN EXPORT NEXT ──────────────────────────

def _site_next(proj):
    """Un export statique Next : un dossier par page, trailingSlash oblige."""
    for chemin in ("index.html", "blog/index.html", "blog/premier-billet/index.html",
                   "blog/second-billet/index.html", "mentions-legales/index.html"):
        cible = proj.output_dir / chemin
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text("<html></html>", encoding="utf-8")


def test_une_page_de_contenu_next_est_photographiee(proj):
    """En V1 une page est « blog/article.html », en V2 « blog/article/index.html ».
    Sans les deux recherches, aucune page de contenu n'est vue sur un site V2."""
    from agents.visuel import VisuelAgent

    _site_next(proj)
    proj.config_path.write_text(
        '{"site": {"collections": [{"id": "blog", "titre": "Blog", '
        '"source": "blog", "url": "blog"}]}}',
        encoding="utf-8",
    )

    pages = [p.relative_to(proj.output_dir).as_posix() for p in VisuelAgent(proj)._pages_secondaires()]

    assert pages == ["blog/index.html", "blog/premier-billet/index.html"]


def test_sans_collection_declaree_on_regarde_ce_qui_existe(proj):
    """En V2 les collections sont déclarées dans site.config.ts, pas dans le
    config.json : sans ce repli, seule l'accueil serait jugée."""
    from agents.visuel import VisuelAgent

    _site_next(proj)
    proj.config_path.write_text('{"site": {}}', encoding="utf-8")

    pages = [p.relative_to(proj.output_dir).as_posix() for p in VisuelAgent(proj)._pages_secondaires()]

    assert "blog/index.html" in pages
    assert "blog/premier-billet/index.html" in pages
    # Une page d'obligation légale n'a pas de composition à juger.
    assert "mentions-legales/index.html" not in pages
