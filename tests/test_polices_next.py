"""Tests de l'hébergement des polices pour le squelette Next.

Aucun accès réseau : on teste ce qui DÉCIDE (quelles familles, quelle adresse,
quelle feuille), pas le téléchargement. La réponse de Google ci-dessous est un
extrait réel de sa feuille de style.
"""
from utils.polices import (
    assembler_polices_css,
    analyser_css_google,
    familles_de_la_charte,
    heberger_polices_next,
    url_google,
)

CSS_GOOGLE = """/* latin-ext */
@font-face {
  font-family: 'Fraunces';
  font-style: normal;
  font-weight: 300 900;
  src: url(https://fonts.gstatic.com/s/fraunces/v1/abc.woff2) format('woff2');
  unicode-range: U+0100-02BA;
}
/* latin */
@font-face {
  font-family: 'Fraunces';
  font-style: normal;
  font-weight: 300 900;
  src: url(https://fonts.gstatic.com/s/fraunces/v1/def.woff2) format('woff2');
  unicode-range: U+0000-00FF;
}
/* cyrillic */
@font-face {
  font-family: 'Fraunces';
  font-style: normal;
  font-weight: 300 900;
  src: url(https://fonts.gstatic.com/s/fraunces/v1/ghi.woff2) format('woff2');
  unicode-range: U+0301;
}
"""


def _charte(tmp_path, contenu: str):
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "charte.css").write_text(contenu, encoding="utf-8")
    return tmp_path


def test_les_familles_viennent_de_la_charte_pas_du_plan(tmp_path):
    """C'est la charte qui décide ce que le CSS demandera vraiment. Se fier au
    plan, c'est risquer de livrer des fichiers que personne n'utilise."""
    site = _charte(tmp_path, """:root {
  --police-titre: "Fraunces", Georgia, serif;
  --police-texte: 'Source Sans 3', system-ui, sans-serif;
}""")

    assert familles_de_la_charte(site) == ["Fraunces", "Source Sans 3"]


def test_les_familles_systeme_ne_sont_pas_telechargees(tmp_path):
    """Georgia et system-ui sont déjà sur la machine du visiteur."""
    site = _charte(tmp_path, """:root {
  --police-titre: Georgia, "Times New Roman", serif;
  --police-texte: system-ui, sans-serif;
}""")

    assert familles_de_la_charte(site) == []


def test_sans_charte_aucune_famille(tmp_path):
    assert familles_de_la_charte(tmp_path) == []


def test_ladresse_google_demande_une_plage_de_graisses():
    """Une police variable arrive en un fichier quelle que soit la plage :
    demander large ne coûte rien et évite un titre en 800 qui n'existe pas."""
    url = url_google(["Fraunces", "Source Sans 3"])

    assert "family=Fraunces:wght@300..900" in url
    assert "family=Source+Sans+3:wght@300..900" in url
    assert url.endswith("&display=swap")


def test_seuls_les_sous_ensembles_utiles_sont_retenus():
    """Le cyrillique alourdit le dossier sans aucun usage sur un site français."""
    blocs = analyser_css_google(CSS_GOOGLE)

    assert {b["sous_ensemble"] for b in blocs} == {"latin", "latin-ext"}


def test_la_feuille_pointe_vers_les_fichiers_locaux():
    feuille, fichiers = assembler_polices_css(analyser_css_google(CSS_GOOGLE))

    assert "fonts.gstatic.com" not in feuille
    assert "url('/polices/fraunces-300 900-latin.woff2')" in feuille or all(
        f"/polices/{nom}" in feuille for nom in fichiers
    )
    assert "font-display: swap" in feuille


def test_polices_css_est_toujours_ecrit_meme_sans_police(tmp_path):
    """L'enveloppe du squelette charge /polices/polices.css sans condition :
    un fichier absent donnerait un 404 sur chaque page, visible seulement dans
    la console du navigateur."""
    site = _charte(tmp_path, ":root { --police-titre: Georgia, serif; }")

    rapport = heberger_polices_next(site)

    assert rapport["familles"] == []
    assert (site / "public" / "polices" / "polices.css").is_file()
