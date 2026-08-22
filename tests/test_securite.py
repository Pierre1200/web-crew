"""Tests de l'agent Sécurité — zéro token, zéro appel API, zéro réseau.

Tout ce qui décide est testé hors ligne : l'inventaire des tiers, la CSP
calculée depuis le site réel, les corrections mécaniques et la recherche de
secrets. Le seul morceau qui touche au réseau (téléchargement des polices) est
séparé de son analyse, précisément pour que celle-ci reste vérifiable ici.
"""
from utils.polices import (
    analyser_css_google,
    extraire_liens_google,
    nom_fichier_police,
    reecrire_bloc,
    retirer_liens_google,
)
from utils.securite import (
    ajouter_pot_de_miel,
    auditer,
    chercher_secrets,
    construire_csp,
    durcir_liens_externes,
    inventorier_tiers,
    rendre_headers,
    rendre_htaccess,
)

PAGE = """<!DOCTYPE html><html lang="fr"><head>
<meta charset="UTF-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lato&display=swap">
<link rel="stylesheet" href="style.css">
</head><body>
<h1>Titre</h1>
<img src="https://picsum.photos/seed/a/800/600" alt="a">
<iframe src="https://www.youtube-nocookie.com/embed/abc" title="v"></iframe>
<form action="https://formspree.io/f/abcd1234" method="POST"></form>
<a href="https://instagram.com/x" target="_blank">Instagram</a>
<script src="main.js"></script>
</body></html>"""


def _site(proj, html=PAGE, css="body{}", js="const a = 1;"):
    (proj.output_dir / "index.html").write_text(html, encoding="utf-8")
    (proj.output_dir / "style.css").write_text(css, encoding="utf-8")
    (proj.output_dir / "main.js").write_text(js, encoding="utf-8")


# ── Inventaire des tiers ───────────────────────────────────────────────

def test_inventaire_recense_chaque_tiers_avec_son_role(proj):
    _site(proj)
    inventaire = inventorier_tiers(proj.output_dir)

    assert inventaire["https://fonts.googleapis.com"] == {"style"}
    assert inventaire["https://picsum.photos"] == {"image"}
    assert inventaire["https://www.youtube-nocookie.com"] == {"iframe"}
    # La destination du formulaire compte DEUX fois : envoi natif (form-action)
    # et envoi JavaScript par fetch(form.action) — une variable, donc invisible
    # à l'analyse du script.
    assert inventaire["https://formspree.io"] == {"formulaire", "connexion"}
    assert "https://instagram.com" not in inventaire   # un lien n'est pas un chargement


def test_inventaire_voit_les_url_du_css_et_les_fetch_du_js(proj):
    _site(proj,
          css='@font-face{src:url(https://cdn.exemple.fr/a.woff2)}',
          js='fetch("https://api.exemple.fr/envoi")')
    inventaire = inventorier_tiers(proj.output_dir)
    assert inventaire["https://cdn.exemple.fr"] == {"font"}
    assert inventaire["https://api.exemple.fr"] == {"connexion"}


def test_hote_de_polices_classe_en_font_meme_via_preconnect(proj):
    """Sans ça, font-src n'autoriserait pas gstatic et les polices seraient bloquées."""
    _site(proj, html='<html><head>'
                     '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                     '</head><body><h1>x</h1></body></html>')
    inventaire = inventorier_tiers(proj.output_dir)
    assert inventaire["https://fonts.gstatic.com"] == {"font"}
    assert "font-src 'self' https://fonts.gstatic.com" in construire_csp(inventaire)


def test_site_autonome_n_a_aucun_tiers(proj):
    _site(proj, html="<html><body><h1>x</h1></body></html>")
    assert inventorier_tiers(proj.output_dir) == {}


# ── Politique de sécurité du contenu ───────────────────────────────────

def test_csp_deduite_du_site_reel(proj):
    _site(proj)
    csp = construire_csp(inventorier_tiers(proj.output_dir))

    assert "default-src 'self'" in csp
    assert "style-src 'self' https://fonts.googleapis.com" in csp
    assert "img-src 'self' data: https://picsum.photos" in csp
    assert "frame-src 'self' https://www.youtube-nocookie.com" in csp
    assert "form-action 'self' https://formspree.io" in csp
    # sans quoi le fetch du formulaire serait bloqué et l'envoi échouerait
    assert "connect-src 'self' https://formspree.io" in csp
    # verrous systématiques
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp


def test_csp_sans_unsafe_inline_par_defaut(proj):
    _site(proj)
    assert "'unsafe-inline'" not in construire_csp(inventorier_tiers(proj.output_dir))


def test_csp_tolere_les_styles_inline_seulement_si_necessaire():
    csp = construire_csp({}, styles_inline=True)
    assert "style-src 'self' 'unsafe-inline'" in csp


def test_fichiers_d_en_tetes(proj):
    csp = "default-src 'self'"
    headers, htaccess = rendre_headers(csp), rendre_htaccess(csp)

    assert "Content-Security-Policy: default-src 'self'" in headers
    assert "/*" in headers                                    # portée Netlify
    assert "X-Content-Type-Options: nosniff" in headers
    assert 'Header always set Content-Security-Policy' in htaccess
    assert "<IfModule mod_headers.c>" in htaccess


def test_mode_observation_ne_bloque_rien():
    headers = rendre_headers("default-src 'self'", report_only=True)
    assert "Content-Security-Policy-Report-Only:" in headers


# ── Audit ──────────────────────────────────────────────────────────────

def test_lien_sans_noopener_signale(proj):
    _site(proj)
    types = {c["type"] for c in auditer(proj.output_dir)}
    assert "lien_sans_noopener" in types
    assert "iframe_sans_referrerpolicy" in types
    assert "formulaire_sans_piege" in types


def test_contenu_mixte_est_une_erreur(proj):
    _site(proj, html='<html><body><img src="http://exemple.fr/a.jpg" alt="a"></body></html>')
    constats = [c for c in auditer(proj.output_dir) if c["type"] == "contenu_mixte"]
    assert len(constats) == 1 and constats[0]["niveau"] == "erreur"


def test_js_dangereux_signale(proj):
    _site(proj, js='el.innerHTML = valeurDuVisiteur;')
    constats = [c for c in auditer(proj.output_dir) if c["type"] == "js_dangereux"]
    assert len(constats) == 1 and constats[0]["niveau"] == "erreur"


def test_email_en_clair_signale(proj):
    _site(proj, html='<html><body><a href="mailto:contact@exemple.fr">Écrire</a></body></html>')
    assert any(c["type"] == "email_en_clair" for c in auditer(proj.output_dir))


# ── Recherche de secrets ───────────────────────────────────────────────

def test_cle_api_detectee_sans_etre_recopiee(proj):
    (proj.output_dir / "config.js").write_text(
        'const cle = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";', encoding="utf-8"
    )
    trouvailles = chercher_secrets(proj.output_dir)
    assert len(trouvailles) >= 1
    # le rapport ne doit jamais contenir le secret en entier
    assert all(len(t["extrait"]) <= 13 for t in trouvailles)


def test_site_propre_sans_secret(proj):
    _site(proj)
    assert chercher_secrets(proj.output_dir) == []


# ── Durcissement ───────────────────────────────────────────────────────

def test_noopener_ajoute_sans_ecraser_un_rel_existant():
    html, n = durcir_liens_externes(
        '<a href="https://x.fr" target="_blank" rel="nofollow">x</a>'
    )
    assert n == 1
    assert 'rel="nofollow noopener noreferrer"' in html


def test_noopener_ajoute_quand_rel_absent():
    html, n = durcir_liens_externes('<a href="https://x.fr" target="_blank">x</a>')
    assert n == 1 and 'rel="noopener noreferrer"' in html


def test_durcissement_des_liens_idempotent():
    html, _ = durcir_liens_externes('<a href="https://x.fr" target="_blank">x</a>')
    html2, n2 = durcir_liens_externes(html)
    assert n2 == 0 and html2 == html


def test_pot_de_miel_ajoute_a_chaque_formulaire():
    html, n = ajouter_pot_de_miel("<form></form><form></form>")
    assert n == 2 and html.count('name="_gotcha"') == 2
    assert 'aria-hidden="true"' in html          # invisible aussi pour les lecteurs d'écran


def test_pot_de_miel_idempotent():
    html, _ = ajouter_pot_de_miel("<form></form>")
    _, n = ajouter_pot_de_miel(html)
    assert n == 0


def test_pot_de_miel_sans_style_inline():
    """Un style inline serait bloqué par la CSP qu'on pose juste après."""
    html, _ = ajouter_pot_de_miel("<form></form>")
    assert "style=" not in html


# ── Polices (analyse hors ligne) ───────────────────────────────────────

CSS_GOOGLE = """/* cyrillic */
@font-face {
  font-family: 'Lato';
  font-style: normal;
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/lato/v1/cyrillic.woff2) format('woff2');
  unicode-range: U+0301;
}
/* latin */
@font-face {
  font-family: 'Lato';
  font-style: normal;
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/lato/v1/latin.woff2) format('woff2');
  unicode-range: U+0000-00FF;
}
"""


def test_extraire_liens_google_decode_les_entites():
    html = ('<link href="https://fonts.googleapis.com/css2?family=Lato'
            '&amp;family=Inter&amp;display=swap" rel="stylesheet">')
    assert extraire_liens_google(html) == [
        "https://fonts.googleapis.com/css2?family=Lato&family=Inter&display=swap"
    ]


def test_analyser_css_filtre_les_sous_ensembles_inutiles():
    """Un site français n'a aucun usage du cyrillique : le livrer alourdit pour rien."""
    blocs = analyser_css_google(CSS_GOOGLE)
    assert len(blocs) == 1
    assert blocs[0]["sous_ensemble"] == "latin"
    assert blocs[0]["famille"] == "Lato"
    assert blocs[0]["graisse"] == "400"


def test_analyser_css_peut_tout_garder():
    assert len(analyser_css_google(CSS_GOOGLE, sous_ensembles=())) == 2


def test_nom_de_fichier_police_lisible():
    bloc = {"famille": "Playfair Display", "graisse": "700",
            "style": "italic", "sous_ensemble": "latin"}
    assert nom_fichier_police(bloc) == "playfair-display-700-italic-latin.woff2"


def test_reecriture_pointe_en_local_et_ajoute_font_display():
    bloc = analyser_css_google(CSS_GOOGLE)[0]
    reecrit = reecrire_bloc(bloc, "assets/fonts/lato-400-latin.woff2")
    assert "url('assets/fonts/lato-400-latin.woff2')" in reecrit
    assert "fonts.gstatic.com" not in reecrit
    assert "font-display: swap" in reecrit


def test_retrait_des_liens_google():
    html = ('<head>\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lato">\n'
            '<link rel="stylesheet" href="style.css">\n</head>')
    nouveau, retires = retirer_liens_google(html)
    assert retires == 2
    assert "fonts.googleapis.com" not in nouveau and "fonts.gstatic.com" not in nouveau
    assert 'href="style.css"' in nouveau          # la feuille locale est conservée
