"""Tests du validateur — c'est lui qui surveille les autres agents,
il doit donc être lui-même le code le plus fiable du projet.

Grâce au client API paresseux, aucun ANTHROPIC_API_KEY n'est requis ici.
"""
import json

from agents.validator import ValidatorAgent, FIXABLE_TYPES

HTML_OK = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lato&display=swap">
<link rel="stylesheet" href="style.css">
</head>
<body>
<h1 class="hero">Bienvenue</h1>
<p class="visible texte">Contenu</p>
<script src="main.js"></script>
</body>
</html>
"""

CSS_OK = ".hero { color: red; } .texte { color: blue; }"
JS_OK = "function f() { return 1; }"


def _site(proj, html=HTML_OK, css=CSS_OK, js=JS_OK, textes=None):
    """Écrit un site complet dans le projet de test."""
    if html is not None:
        (proj.output_dir / "index.html").write_text(html, encoding="utf-8")
    if css is not None:
        (proj.output_dir / "style.css").write_text(css, encoding="utf-8")
    if js is not None:
        (proj.output_dir / "main.js").write_text(js, encoding="utf-8")
    if textes is None:
        textes = {"hero": {"accroche": "Bienvenue"}}
    (proj.temp_dir / "textes.json").write_text(
        json.dumps(textes, ensure_ascii=False), encoding="utf-8"
    )


def _types(result):
    return {p["type"] for p in result["problemes"]}


def test_site_complet_est_valide(proj):
    _site(proj)
    result = ValidatorAgent(proj).run({})
    assert result["valide"] is True
    assert result["problemes"] == []


def test_html_tronque_detecte(proj):
    _site(proj, html=HTML_OK.replace("</html>", ""))
    result = ValidatorAgent(proj).run({})
    assert result["valide"] is False
    assert "html_tronque" in _types(result)


def test_classe_absente_du_css(proj):
    _site(proj, html=HTML_OK.replace('class="visible texte"', 'class="visible btn-mystere"'))
    result = ValidatorAgent(proj).run({})
    pbs = [p for p in result["problemes"] if p["type"] == "classe_absente"]
    assert len(pbs) == 1
    assert pbs[0]["classe"] == "btn-mystere"
    assert pbs[0]["niveau"] == "erreur"


def test_classe_dynamique_js_ignoree(proj):
    # "visible" est ajoutée par le JS au runtime : pas un problème
    _site(proj)
    result = ValidatorAgent(proj).run({})
    assert "classe_absente" not in _types(result)


def test_js_tronque_detecte(proj):
    _site(proj, js="function f() { if (true) {")
    result = ValidatorAgent(proj).run({})
    assert "js_tronque" in _types(result)
    assert "js_tronque" in FIXABLE_TYPES


def test_css_tronque_detecte(proj):
    _site(proj, css=".hero { color: red; .texte { color: blue; }")
    result = ValidatorAgent(proj).run({})
    assert "css_tronque" in _types(result)


def test_liens_fichiers_manquants(proj):
    html = HTML_OK.replace('<link rel="stylesheet" href="style.css">', "") \
                  .replace('<script src="main.js"></script>', "")
    _site(proj, html=html)
    result = ValidatorAgent(proj).run({})
    assert {"lien_css_manquant", "lien_js_manquant"} <= _types(result)


def test_fichier_manquant(proj):
    _site(proj)
    (proj.output_dir / "index.html").unlink()
    result = ValidatorAgent(proj).run({})
    assert result["valide"] is False
    assert "fichier_manquant" in _types(result)


def test_warning_n_invalide_pas_le_site(proj):
    # Sans <h1> : warning h1_manquant, mais le site reste valide
    _site(proj, html=HTML_OK.replace("<h1", "<p").replace("</h1>", "</p>"))
    result = ValidatorAgent(proj).run({})
    assert "h1_manquant" in _types(result)
    assert result["valide"] is True


def test_section_vide_signale_en_warning(proj):
    _site(proj, textes={"hero": {"accroche": "ok"}, "a_propos": ""})
    result = ValidatorAgent(proj).run({})
    pbs = [p for p in result["problemes"] if p["type"] == "section_vide"]
    assert len(pbs) == 1
    assert pbs[0]["niveau"] == "warning"
    # warning "section possiblement manquante" attendu aussi, mais valide reste vrai
    assert result["valide"] is True


def test_formulaire_sans_action_signale_en_warning(proj):
    html = HTML_OK.replace(
        "<body>", '<body><form id="contactForm" novalidate></form>'
    )
    _site(proj, html=html)
    result = ValidatorAgent(proj).run({})
    pbs = [p for p in result["problemes"] if p["type"] == "formulaire_sans_action"]
    assert len(pbs) == 1
    assert pbs[0]["niveau"] == "warning"
    assert result["valide"] is True  # factice = à signaler, pas bloquant


def test_formulaire_avec_action_ok(proj):
    html = HTML_OK.replace(
        "<body>",
        '<body><form id="f" action="https://formspree.io/f/abcd1234" method="POST"></form>',
    )
    _site(proj, html=html)
    result = ValidatorAgent(proj).run({})
    assert "formulaire_sans_action" not in _types(result)


def test_tous_les_problemes_sont_structures(proj):
    _site(proj, html="<html>", css="", js="{")
    result = ValidatorAgent(proj).run({})
    for p in result["problemes"]:
        assert {"type", "niveau", "message"} <= set(p.keys())
        assert p["niveau"] in ("erreur", "warning")
