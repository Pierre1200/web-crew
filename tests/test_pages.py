"""Tests du moteur multi-pages — zéro token, zéro appel API.

C'est le code qui transforme les textes du client en pages livrées. Une erreur
ici se voit directement sur le site, et l'échappement est la seule barrière
contre l'injection : la couverture doit être stricte.
"""
from datetime import date

from utils.pages import (
    collections_declarees,
    date_en_francais,
    decouper_corps,
    lire_collection,
    lire_contenu,
    marqueurs_presents,
    remplir,
    rendre_collection,
    rendre_corps,
    rendre_flux,
    slugifier,
    temps_de_lecture,
)

ARTICLE = """Titre: D'où vient le nom de l'atelier ?
Chapo: Une histoire de famille, et un mot inventé sur place.
Date: 2026-08-14
Couverture: atelier.jpg
Statut: publie

Le premier atelier a ouvert rue des Lilas,
dans un ancien entrepôt.

## Les débuts

Trois personnes, deux établis, et beaucoup de patience.

> On ne savait pas encore ce qu'on faisait, mais on le faisait bien.
"""

GABARITS = {
    "liste": "<html><body><h1>{{titre_collection}}</h1><p>{{chapeau}}</p>"
             "<ul>{{items}}</ul><a href='{{url_accueil}}'>Accueil</a></body></html>",
    "item": '<li><a href="{{url}}">{{titre}}</a><p>{{chapo}}</p>'
            "<time>{{date_fr}}</time>{{couverture}}</li>",
    "page": '<html><head><link href="{{racine}}style.css"></head><body>'
            "<h1>{{titre}}</h1>{{couverture}}<div>{{corps}}</div>"
            '<a href="{{url_liste}}">Retour</a></body></html>',
    "paragraphe": "<p>{{texte}}</p>",
    "sous_titre": "<h2>{{texte}}</h2>",
    "citation": "<blockquote>{{texte}}</blockquote>",
    "image": '<img src="{{src}}" alt="{{alt}}">',
}

COLLECTION = {"id": "blog", "titre": "Le blog", "chapeau": "Les histoires.",
              "source": "articles", "url": "blog", "flux": True}


def _ecrire(proj, nom, contenu, dossier="articles"):
    cible = proj.data_dir / dossier / nom
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")
    return cible


# ── Outils de texte ────────────────────────────────────────────────────

def test_slugifier():
    assert slugifier("D'où vient le nom de l'atelier ?") == "d-ou-vient-le-nom-de-l-atelier"
    assert slugifier("Œuvres & créations") == "oeuvres-creations"
    assert slugifier("---") == "page"


def test_date_en_francais():
    assert date_en_francais(date(2026, 8, 14)) == "14 août 2026"
    assert date_en_francais(date(2026, 1, 1)) == "1 janvier 2026"


def test_temps_de_lecture_jamais_nul():
    assert temps_de_lecture("trois mots seulement") == 1
    assert temps_de_lecture(" ".join(["mot"] * 400)) == 2


# ── Découpage du corps ─────────────────────────────────────────────────

def test_decouper_corps_reconnait_les_trois_types():
    blocs = decouper_corps("Un para.\n\n## Un titre\n\n> Une citation.")
    assert [b["type"] for b in blocs] == ["paragraphe", "sous_titre", "citation"]
    assert blocs[1]["texte"] == "Un titre"
    assert blocs[2]["texte"] == "Une citation."


def test_paragraphe_multiligne_reste_un_seul_paragraphe():
    blocs = decouper_corps("Première ligne\nsuite du paragraphe.\n\nAutre para.")
    assert len(blocs) == 2
    assert blocs[0]["texte"] == "Première ligne suite du paragraphe."


def test_fins_de_ligne_windows_supportees():
    """Un texte collé depuis Word utilise \\r\\n : sans tolérance, tout fusionne."""
    blocs = decouper_corps("Para un.\r\n\r\nPara deux.")
    assert len(blocs) == 2


# ── Lecture d'un fichier ───────────────────────────────────────────────

def test_lire_contenu_complet(proj):
    contenu = lire_contenu(_ecrire(proj, "atelier.txt", ARTICLE))
    assert contenu["titre"] == "D'où vient le nom de l'atelier ?"
    assert contenu["chapo"].startswith("Une histoire de famille")
    assert contenu["date"] == "2026-08-14"
    assert contenu["date_fr"] == "14 août 2026"
    assert contenu["couverture"] == "atelier.jpg"
    assert contenu["statut"] == "publie"
    assert contenu["slug"] == "atelier"
    assert [b["type"] for b in contenu["blocs"]] == [
        "paragraphe", "sous_titre", "paragraphe", "citation"
    ]
    # le paragraphe écrit sur deux lignes n'a pas été coupé en deux
    assert contenu["blocs"][0]["texte"].endswith("dans un ancien entrepôt.")


def test_fichier_sans_entete_reste_exploitable(proj):
    """Le client n'est pas développeur : un oubli ne doit pas tout casser."""
    contenu = lire_contenu(_ecrire(proj, "note-simple.txt", "Juste du texte.\n"))
    assert contenu["titre"] == "note simple"       # déduit du nom de fichier
    assert contenu["statut"] == "publie"           # publié par défaut
    assert len(contenu["blocs"]) == 1


def test_date_au_format_francais_acceptee(proj):
    contenu = lire_contenu(_ecrire(proj, "a.txt", "Titre: X\nDate: 14/08/2026\n\nTexte."))
    assert contenu["date"] == "2026-08-14"


def test_cles_d_entete_insensibles_a_la_casse_et_aux_accents(proj):
    contenu = lire_contenu(_ecrire(proj, "a.txt", "TITRE: Mon titre\nChapô: Mon chapo\n\nTexte."))
    assert contenu["titre"] == "Mon titre"
    assert contenu["chapo"] == "Mon chapo"


def test_brouillons_exclus_et_tri_antichronologique(proj):
    _ecrire(proj, "vieux.txt", "Titre: Vieux\nDate: 2026-01-01\n\nTexte.")
    _ecrire(proj, "recent.txt", "Titre: Récent\nDate: 2026-08-01\n\nTexte.")
    _ecrire(proj, "cache.txt", "Titre: Caché\nStatut: brouillon\n\nTexte.")

    contenus = lire_collection(proj, COLLECTION)
    assert [c["titre"] for c in contenus] == ["Récent", "Vieux"]


def test_collection_absente_ne_plante_pas(proj):
    assert lire_collection(proj, COLLECTION) == []


# ── Déclaration des collections ────────────────────────────────────────

def test_collections_declarees_valeurs_par_defaut():
    collections = collections_declarees({"site": {"collections": [{"id": "Blog"}]}})
    assert collections[0]["id"] == "blog"
    assert collections[0]["source"] == "blog"
    assert collections[0]["flux"] is True


def test_collection_sans_id_ignoree():
    assert collections_declarees({"site": {"collections": [{"titre": "X"}]}}) == []


# ── Remplissage et échappement ─────────────────────────────────────────

def test_remplir_echappe_le_texte_du_client():
    """La barrière anti-injection : le texte du client ne devient jamais du balisage."""
    rendu = remplir("<h1>{{titre}}</h1>", {"titre": '<script>alert("x")</script>'})
    assert "<script>" not in rendu
    assert "&lt;script&gt;" in rendu


def test_remplir_n_echappe_pas_le_html_construit_par_nous():
    rendu = remplir("<div>{{corps}}</div>", {"corps": "<p>Bonjour</p>"})
    assert rendu == "<div><p>Bonjour</p></div>"


def test_marqueur_inconnu_devient_vide():
    assert remplir("<p>{{inexistant}}</p>", {}) == "<p></p>"


def test_marqueurs_presents():
    assert marqueurs_presents("{{a}} et {{ b }}") == {"a", "b"}


def test_rendre_corps_utilise_les_gabarits_de_blocs():
    blocs = [{"type": "paragraphe", "texte": "Un"}, {"type": "citation", "texte": "Deux"}]
    assert rendre_corps(blocs, GABARITS) == "<p>Un</p>\n<blockquote>Deux</blockquote>"


# ── Rendu complet d'une collection ─────────────────────────────────────

def test_rendre_collection_produit_les_pages_et_la_liste(proj):
    _ecrire(proj, "atelier.txt", ARTICLE)
    _ecrire(proj, "adresses.txt", "Titre: Les adresses\nDate: 2026-07-01\n\nTexte simple.")
    contenus = lire_collection(proj, COLLECTION)

    fichiers = dict(rendre_collection(COLLECTION, contenus, GABARITS))

    assert set(fichiers) == {"blog/atelier.html", "blog/adresses.html", "blog/index.html"}

    page = fichiers["blog/atelier.html"]
    assert "<h1>D&#x27;où vient le nom de l&#x27;atelier ?</h1>" in page
    assert "<h2>Les débuts</h2>" in page
    assert "<blockquote>" in page
    assert 'href="../style.css"' in page          # préfixe de sous-dossier
    assert '<img src="../assets/atelier.jpg"' in page
    assert 'href="index.html"' in page            # retour direct vers la liste

    liste = fichiers["blog/index.html"]
    assert liste.count("<li>") == 2
    assert 'href="atelier.html"' in liste          # lien relatif dans le dossier
    assert "Le blog" in liste


def test_contenu_sans_couverture_n_a_pas_d_image(proj):
    _ecrire(proj, "a.txt", "Titre: Sans image\n\nTexte.")
    contenus = lire_collection(proj, COLLECTION)
    page = dict(rendre_collection(COLLECTION, contenus, GABARITS))["blog/a.html"]
    assert "<img" not in page


def test_collection_a_un_seul_contenu_reste_valide(proj):
    _ecrire(proj, "seul.txt", "Titre: Seul\n\nTexte.")
    contenus = lire_collection(proj, COLLECTION)
    fichiers = dict(rendre_collection(COLLECTION, contenus, GABARITS))
    assert fichiers["blog/index.html"].count("<li>") == 1


# ── Flux RSS ───────────────────────────────────────────────────────────

def test_flux_rss_valide_et_echappe(proj):
    _ecrire(proj, "a.txt", 'Titre: Titre & <danger>\nDate: 2026-08-14\n\nTexte.')
    contenus = lire_collection(proj, COLLECTION)
    flux = rendre_flux(COLLECTION, contenus, "https://exemple.fr")

    assert flux.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<danger>" not in flux and "&lt;danger&gt;" in flux
    assert "<link>https://exemple.fr/blog/a.html</link>" in flux
    assert flux.count("<item>") == 1


def test_flux_sans_domaine_reste_relatif(proj):
    _ecrire(proj, "a.txt", "Titre: A\n\nTexte.")
    flux = rendre_flux(COLLECTION, lire_collection(proj, COLLECTION), "")
    assert "<link>blog/a.html</link>" in flux


# ── Marqueurs HTML dans un attribut ────────────────────────────────────
#
# Bug du premier run réel : le designer a écrit src="{{couverture}}", croyant
# à une URL. Le marqueur est remplacé par un <figure> entier, donc du balisage
# s'est retrouvé imbriqué dans un attribut et treize pages sont parties sans
# la moindre image.

def test_couverture_dans_un_src_est_refusee():
    from utils.pages import marqueur_html_dans_attribut
    gabarit = '<img class="o__img" src="{{couverture}}" alt="{{titre}}">'
    assert marqueur_html_dans_attribut(gabarit) == "couverture"


def test_couverture_bien_placee_est_acceptee():
    from utils.pages import marqueur_html_dans_attribut
    assert marqueur_html_dans_attribut('<div class="media">{{couverture}}</div>') is None


def test_corps_et_items_aussi_surveilles():
    from utils.pages import marqueur_html_dans_attribut
    assert marqueur_html_dans_attribut('<div data-x="{{corps}}">') == "corps"
    assert marqueur_html_dans_attribut('<ul data-y="{{items}}">') == "items"


def test_marqueurs_de_texte_autorises_dans_les_attributs():
    """{{src}}, {{titre}} et {{url}} sont du texte : leur place EST l'attribut."""
    from utils.pages import marqueur_html_dans_attribut
    assert marqueur_html_dans_attribut('<img src="{{src}}" alt="{{titre}}">') is None
    assert marqueur_html_dans_attribut('<a href="{{url}}">{{titre}}</a>') is None
