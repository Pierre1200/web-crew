"""Tests du découpage de la réponse multi-sections du designer,
et du bornage de volume de l'ingestion — sans aucun appel API.
"""
from agents.designer import DesignerAgent
from agents.ingestion import IngestionAgent, MAX_TEXTE_CHARS

REPONSE_COMPLETE = """===HTML===
<!DOCTYPE html><html><body></body></html>
===CSS===
.hero { color: red; }
===JS===
console.log("ok");
"""


def test_parse_reponse_complete(proj):
    designer = DesignerAgent(proj)
    html, css, js = designer._parse_site_response(REPONSE_COMPLETE)
    assert html.startswith("<!DOCTYPE html>")
    assert css == ".hero { color: red; }"
    assert js == 'console.log("ok");'


def test_parse_separateur_manquant_donne_vide(proj):
    designer = DesignerAgent(proj)
    # Pas de séparateur CSS : css vide, et le JS reste extrait correctement
    reponse = "===HTML===\n<!DOCTYPE html></html>\n===JS===\nlet a = 1;"
    html, css, js = designer._parse_site_response(reponse)
    assert html  # le HTML va jusqu'au séparateur suivant trouvé
    assert css == ""
    assert js == "let a = 1;"


def test_parse_fences_markdown_nettoyees(proj):
    designer = DesignerAgent(proj)
    reponse = "===HTML===\n```html\n<!DOCTYPE html></html>\n```\n===CSS===\n.a{}\n===JS===\n;"
    html, _, _ = designer._parse_site_response(reponse)
    assert html.startswith("<!DOCTYPE html>")
    assert "```" not in html


def test_borner_textes_sous_le_budget_inchange(proj):
    agent = IngestionAgent(proj)
    textes = {"doc.txt": "court contenu"}
    assert agent._borner_textes(textes) == textes


def test_borner_textes_tronque_au_dela_du_budget(proj):
    agent = IngestionAgent(proj)
    textes = {
        "gros.txt": "x" * (MAX_TEXTE_CHARS - 1),
        "moyen.txt": "y" * 100,
        "dernier.txt": "z" * 10,
    }
    bornes = agent._borner_textes(textes)
    assert bornes["gros.txt"] == textes["gros.txt"]          # entier (rentre)
    assert bornes["moyen.txt"].endswith("[…tronqué…]")        # coupé au budget
    assert "omis" in bornes["dernier.txt"]                    # plus de budget
