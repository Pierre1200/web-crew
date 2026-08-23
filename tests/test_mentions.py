"""Tests de la page de mentions légales — zéro token, zéro API.

Le premier run réel a produit seize liens vers une page qu'aucun module ne
savait générer. Elle est obligatoire en France, et son contenu est purement
administratif : rien à faire rédiger par un modèle.
"""
import json

from utils.mentions import (
    FICHIER,
    champs_manquants,
    donnees_mentions,
    rendre_mentions,
)

CONFIG_COMPLETE = {
    "client": {"nom": "Association Exemple"},
    "site": {
        "url": "https://exemple.fr",
        "mentions": {
            "statut": "association loi 1901",
            "adresse": "1 rue des Lilas, 12000 Ville",
            "rna": "W000000000",
            "siret": "000 000 000 00000",
            "directeur_publication": "La présidente",
            "email": "contact@exemple.fr",
            "hebergeur": {"nom": "Hébergeur SAS",
                          "adresse": "2 avenue du Web, 75000 Paris",
                          "site": "https://hebergeur.fr"},
        },
    },
}


def _config(proj, config):
    (proj.root / "config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )


def test_donnees_reprises_depuis_la_config():
    donnees = donnees_mentions(CONFIG_COMPLETE)
    assert donnees["editeur"] == "Association Exemple"
    assert donnees["siret"] == "000 000 000 00000"
    assert donnees["hebergeur_nom"] == "Hébergeur SAS"


def test_nom_du_client_cherche_dans_plusieurs_cles():
    """Les config.json ne nomment pas ce champ de la même façon."""
    for cle in ("nom", "nom_asso", "nom_galerie", "porteur"):
        donnees = donnees_mentions({"client": {cle: "Mon Client"}, "site": {}})
        assert donnees["editeur"] == "Mon Client"


def test_config_complete_ne_manque_de_rien():
    assert champs_manquants(donnees_mentions(CONFIG_COMPLETE)) == []


def test_informations_absentes_sont_listees_pas_inventees():
    """Sur un document à portée juridique, un trou doit se voir."""
    donnees = donnees_mentions({"client": {}, "site": {}})
    manquants = champs_manquants(donnees)
    assert len(manquants) >= 3
    assert any("hébergeur" in m for m in manquants)
    assert donnees["editeur"] == "à compléter"


def test_siret_ou_rna_suffit():
    """Une association a un RNA, une entreprise un SIRET : l'un OU l'autre."""
    base = {"client": {"nom": "X"}, "site": {"mentions": {
        "directeur_publication": "Y", "hebergeur": {"nom": "Z", "adresse": "A"}}}}
    avec_rna = dict(base)
    avec_rna["site"]["mentions"]["rna"] = "W123"
    assert champs_manquants(donnees_mentions(avec_rna)) == []


def test_page_rendue_contient_les_rubriques_obligatoires(proj):
    _config(proj, CONFIG_COMPLETE)
    html, manquants = rendre_mentions(proj)

    assert html.startswith("<!DOCTYPE html>")
    assert "<h1>Mentions légales</h1>" in html
    assert "Éditeur du site" in html and "Hébergement" in html
    assert "Propriété intellectuelle" in html and "Données personnelles" in html
    assert "Association Exemple" in html
    assert 'href="style.css"' in html      # à la racine : pas de préfixe ../
    assert manquants == []


def test_page_reprend_l_entete_et_le_pied_de_l_accueil(proj):
    """Sans ça, la page légale a l'air d'appartenir à un autre site."""
    _config(proj, CONFIG_COMPLETE)
    (proj.output_dir / "index.html").write_text(
        "<html><body><header class='nav'>ENTETE</header>"
        "<main>x</main><footer class='pied'>PIED</footer></body></html>",
        encoding="utf-8",
    )
    html, _ = rendre_mentions(proj)
    assert "<header class='nav'>ENTETE</header>" in html
    assert "<footer class='pied'>PIED</footer>" in html


def test_page_se_genere_meme_sans_accueil(proj):
    _config(proj, CONFIG_COMPLETE)
    html, _ = rendre_mentions(proj)
    assert "<h1>Mentions légales</h1>" in html


def test_manques_signales_dans_la_page_elle_meme(proj):
    _config(proj, {"client": {}, "site": {}})
    html, manquants = rendre_mentions(proj)
    assert manquants
    assert "À compléter avant mise en ligne" in html


def test_texte_du_client_echappe(proj):
    _config(proj, {"client": {"nom": '<script>alert("x")</script>'}, "site": {}})
    html, _ = rendre_mentions(proj)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_page_non_indexee(proj):
    """Une page légale n'a rien à faire dans les résultats de recherche."""
    _config(proj, CONFIG_COMPLETE)
    html, _ = rendre_mentions(proj)
    assert 'name="robots" content="noindex' in html


def test_nom_de_fichier_attendu_par_le_designer():
    assert FICHIER == "mentions-legales.html"
