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

# Feuille d'exemple conforme à ce que le designer doit produire : rangée en
# couches (pour que les correctifs visuels puissent l'emporter) et respectant
# le réglage système de réduction des animations.
CSS_OK = """@layer reset, base, composants;
@layer composants {
  .hero { color: red; }
  .texte { color: blue; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none; transition: none; }
}"""
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


def test_css_sans_layer_signale_en_warning(proj):
    """Sans couches, les correctifs de la critique visuelle deviennent fragiles."""
    _site(proj, css=".hero{color:red} .texte{color:blue} "
                    "@media (prefers-reduced-motion: reduce){*{animation:none}}")
    result = ValidatorAgent(proj).run({})
    assert "cascade_sans_layer" in _types(result)
    assert result["valide"] is True  # non bloquant : le site reste livrable


def test_animations_non_neutralisables_signalees(proj):
    _site(proj, css="@layer base; @layer base { .hero{color:red} .texte{color:blue} }")
    result = ValidatorAgent(proj).run({})
    assert "motion_non_geree" in _types(result)


def test_abus_de_important_signale(proj):
    _site(proj, css=CSS_OK + "\n" + "\n".join(f".c{i}{{color:red!important}}" for i in range(9)))
    result = ValidatorAgent(proj).run({})
    assert "cascade_forcee" in _types(result)


def test_quelques_important_ne_declenchent_rien(proj):
    _site(proj, css=CSS_OK + "\n.a{color:red!important}\n.b{color:blue!important}")
    result = ValidatorAgent(proj).run({})
    assert "cascade_forcee" not in _types(result)


def _asset(proj, nom, donnees=b"\x89PNG\r\n\x1a\n" + b"\x00" * 40):
    dossier = proj.output_dir / "assets"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_bytes(donnees)


def test_image_referencee_mais_absente_est_une_erreur(proj):
    html = HTML_OK.replace("<body>", '<body><img src="assets/portrait.jpg" alt="x">')
    _site(proj, html=html)
    result = ValidatorAgent(proj).run({})
    pbs = [p for p in result["problemes"] if p["type"] == "ressource_cassee"]
    assert len(pbs) == 1
    assert "assets/portrait.jpg" in pbs[0]["message"]
    assert result["valide"] is False


def test_image_presente_et_utilisee_ne_signale_rien(proj):
    _asset(proj, "portrait.jpg")
    html = HTML_OK.replace("<body>", '<body><img src="assets/portrait.jpg" alt="x">')
    _site(proj, html=html)
    result = ValidatorAgent(proj).run({})
    assert "ressource_cassee" not in _types(result)
    assert "image_inutilisee" not in _types(result)


def test_image_client_jamais_affichee_est_signalee(proj):
    _asset(proj, "logo-client.png")
    _site(proj)
    result = ValidatorAgent(proj).run({})
    pbs = [p for p in result["problemes"] if p["type"] == "image_inutilisee"]
    assert len(pbs) == 1 and "logo-client.png" in pbs[0]["message"]
    assert result["valide"] is True  # avertissement, pas blocage


def test_placeholder_alors_que_le_client_a_fourni_ses_images(proj):
    _asset(proj, "vraie-photo.jpg")
    html = HTML_OK.replace(
        "<body>",
        '<body><img src="assets/vraie-photo.jpg" alt="a">'
        '<img src="https://picsum.photos/seed/x/800/600" alt="b">',
    )
    _site(proj, html=html)
    result = ValidatorAgent(proj).run({})
    assert "placeholder_en_production" in _types(result)


def test_placeholder_seul_ne_declenche_rien(proj):
    """Sans image fournie par le client, le remplissage reste légitime."""
    html = HTML_OK.replace(
        "<body>", '<body><img src="https://picsum.photos/seed/x/800/600" alt="b">'
    )
    _site(proj, html=html)
    result = ValidatorAgent(proj).run({})
    assert "placeholder_en_production" not in _types(result)


def test_image_de_fond_css_verifiee_aussi(proj):
    _site(proj, css=CSS_OK + '\n.hero{background-image:url("assets/fond.jpg")}')
    result = ValidatorAgent(proj).run({})
    pbs = [p for p in result["problemes"] if p["type"] == "ressource_cassee"]
    assert any("assets/fond.jpg" in p["message"] for p in pbs)


def _config_medias(proj, items):
    (proj.root / "config.json").write_text(
        json.dumps({"site": {"medias": {"items": items}}}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_media_declare_mais_absent_du_html(proj):
    _config_medias(proj, [{"titre": "L'Auberge", "url": "https://youtu.be/dQw4w9WgXcQ"}])
    _site(proj)  # HTML sans le moindre iframe
    result = ValidatorAgent(proj).run({})
    pbs = [p for p in result["problemes"] if p["type"] == "media_manquant"]
    assert len(pbs) == 1
    assert "L'Auberge" in pbs[0]["message"]
    assert result["valide"] is False
    # doit être réparable automatiquement par une régénération du HTML
    assert "media_manquant" in FIXABLE_TYPES


def test_media_present_dans_le_html_ne_signale_rien(proj):
    _config_medias(proj, [{"titre": "L'Auberge", "url": "https://youtu.be/dQw4w9WgXcQ"}])
    iframe = ('<iframe src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" '
              'title="L\'Auberge" loading="lazy" allowfullscreen></iframe>')
    _site(proj, html=HTML_OK.replace("<body>", f"<body>{iframe}"))
    result = ValidatorAgent(proj).run({})
    assert "media_manquant" not in _types(result)


def test_media_mal_configure_est_signale(proj):
    _config_medias(proj, [{"titre": "Cassée", "url": "https://exemple.fr/rien.mp4"}])
    _site(proj)
    result = ValidatorAgent(proj).run({})
    assert "media_invalide" in _types(result)


def test_tous_les_problemes_sont_structures(proj):
    _site(proj, html="<html>", css="", js="{")
    result = ValidatorAgent(proj).run({})
    for p in result["problemes"]:
        assert {"type", "niveau", "message"} <= set(p.keys())
        assert p["niveau"] in ("erreur", "warning")
