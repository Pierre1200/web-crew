"""Tests du graphe front. ZÉRO APPEL API, zéro npm.

Ce qui est vérifié ici tient en une phrase : **on ne publie jamais un site qui
ne passe pas la porte**. Le reste des tests décrit les chemins par lesquels on
pourrait le faire par accident.
"""
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from graphe import front as gf
from graphe.etat import etat_initial

SQUELETTE = Path(__file__).resolve().parent.parent / "squelette"


def _etat(**surcharges):
    etat = etat_initial(
        projet="essai", plafond_euros=5.0, max_corrections=3,
        passes_visuelles=0, valider_a_la_main=False,
    )
    etat.update(surcharges)
    return etat


# ── LES ROUTES ─────────────────────────────────────────────────────────

def test_porte_verte_mene_a_la_publication():
    etat = _etat(resultat_porte={"valide": True, "problemes": []})
    assert gf._apres_porte(etat) == "publier"


def test_porte_rouge_mene_a_la_reparation():
    etat = _etat(resultat_porte={"valide": False, "etape_echouee": "type",
                                 "problemes": [{"type": "type"}]})
    assert gf._apres_porte(etat) == "reparation_front"


def test_porte_rouge_apres_toutes_les_tentatives_ne_publie_pas():
    """Le point le plus important du fichier : un site qui ne compile pas n'est
    pas un livrable en retard, c'est un livrable qui n'existe pas."""
    etat = _etat(
        resultat_porte={"valide": False, "etape_echouee": "build", "problemes": [{"type": "build"}]},
        corrections_faites=3, max_corrections=3,
    )
    assert gf._apres_porte(etat) == "fin"


def test_porte_rouge_au_plafond_ne_publie_pas_non_plus():
    etat = _etat(
        resultat_porte={"valide": False, "etape_echouee": "lint", "problemes": [{"type": "lint"}]},
        cout_euros=5.0,
    )
    assert gf._apres_porte(etat) == "plafond"


def test_sans_passe_visuelle_la_publication_termine_le_run():
    assert gf._apres_publication(_etat(passes_visuelles=0)) == "fin"


def test_une_passe_visuelle_qui_ecrit_des_correctifs_repasse_par_la_porte():
    """Un correctif CSS qui casserait la construction doit être attrapé AVANT
    d'être publié. C'est ce que la V1 ne pouvait pas faire : elle écrivait
    directement dans le livrable."""
    etat = _etat(passes_visuelles=2, passes_faites=1, correctifs_appliques=3)
    assert gf._apres_critique(etat) == "porte"


def test_une_passe_visuelle_sans_correctif_termine():
    etat = _etat(passes_visuelles=3, passes_faites=1, correctifs_appliques=0)
    assert gf._apres_critique(etat) == "fin"


def test_capture_indisponible_ne_fait_pas_echouer_le_run():
    """Playwright absent n'annule pas un site déjà bâti et publié."""
    etat = _etat(arret="capture_indisponible", correctifs_appliques=2)
    assert gf._apres_critique(etat) == "fin"


# ── LA TOPOLOGIE ───────────────────────────────────────────────────────

def test_tous_les_noeuds_sont_atteignables():
    dessin = gf.construire().compile().get_graph()
    noeuds = {n for n in dessin.nodes if not n.startswith("__")}
    arrivees = {arete.target for arete in dessin.edges}

    assert noeuds - arrivees == set()
    assert "porte" in noeuds and "publier" in noeuds


def test_les_polices_sont_hebergees_avant_la_generation():
    """La charte nomme des familles ; si personne ne les télécharge, le site se
    construit, passe la porte, et perd sa typographie sans un mot."""
    dessin = gf.construire().compile().get_graph()
    aretes = {(a.source, a.target) for a in dessin.edges}
    assert ("charte", "polices") in aretes
    assert {s for s, t in aretes if t == "front"} == {"polices"}


def test_la_porte_est_le_seul_chemin_vers_la_publication():
    """S'il existait une autre arête vers `publier`, tout le reste ne servirait
    à rien : on pourrait publier sans compiler."""
    dessin = gf.construire().compile().get_graph()
    entrants = {a.source for a in dessin.edges if a.target == "publier"}
    assert entrants == {"porte"}


# ── LE PARCOURS COMPLET, AVEC DOUBLURES ────────────────────────────────

def _graphe_double(monkeypatch, resultats_porte, couts=None):
    """Le vrai graphe, dont les nœuds payants et les nœuds npm sont doublés.

    `resultats_porte` est une liste : un élément par passage à la porte, ce qui
    permet de décrire « échoue, échoue, puis passe ».
    """
    from graphe import noeuds

    couts = couts or {}
    passages = iter(resultats_porte)
    publications = []

    def facture(nom):
        return lambda etat: {"cout_euros": couts.get(nom, 0.0), "journal": [nom]}

    for nom in ("ingestion", "copywriter"):
        monkeypatch.setattr(noeuds, nom, facture(nom))
    monkeypatch.setattr(noeuds, "preparer", lambda e: {"journal": ["preparer"]})
    monkeypatch.setattr(
        noeuds, "orchestration",
        lambda e: {"plan": {"taches": []}, "agents_planifies": ["copywriter"],
                   "cout_euros": couts.get("orchestration", 0.0), "journal": ["orchestration"]},
    )
    monkeypatch.setattr(noeuds, "direction", facture("direction"))

    monkeypatch.setattr(gf, "squelette", lambda e: {"journal": ["squelette"]})
    monkeypatch.setattr(gf, "polices", lambda e: {"journal": ["polices"]})
    monkeypatch.setattr(gf, "charte", facture("charte"))
    monkeypatch.setattr(gf, "front", facture("front"))
    monkeypatch.setattr(
        gf, "porte",
        lambda e: {"resultat_porte": next(passages), "journal": ["porte"]},
    )
    monkeypatch.setattr(
        gf, "reparation_front",
        lambda e: {"corrections_faites": e["corrections_faites"] + 1,
                   "cout_euros": couts.get("reparation_front", 0.0),
                   "journal": ["reparation"]},
    )

    def publier(etat):
        publications.append(True)
        return {"journal": ["publier"]}

    monkeypatch.setattr(gf, "publier", publier)

    return gf.construire().compile(checkpointer=InMemorySaver()), publications


VERT = {"valide": True, "problemes": []}
ROUGE = {"valide": False, "etape_echouee": "type", "problemes": [{"type": "type"}]}


def test_parcours_nominal_publie_une_fois(monkeypatch):
    app, publications = _graphe_double(monkeypatch, [VERT], couts={"front": 2.0})
    etat = app.invoke(_etat(plafond_euros=10.0), {"configurable": {"thread_id": "front-ok"}})

    assert publications == [True]
    assert etat["cout_euros"] == pytest.approx(2.0)


def test_deux_echecs_puis_une_reussite_publient_bien(monkeypatch):
    app, publications = _graphe_double(monkeypatch, [ROUGE, ROUGE, VERT])
    etat = app.invoke(_etat(plafond_euros=10.0), {"configurable": {"thread_id": "front-repare"}})

    assert etat["corrections_faites"] == 2
    assert publications == [True]


def test_echecs_repetes_nepuisent_pas_le_budget_et_ne_publient_rien(monkeypatch):
    """La boucle s'arrête au nombre de tentatives, sans jamais publier."""
    app, publications = _graphe_double(monkeypatch, [ROUGE] * 10)
    etat = app.invoke(
        _etat(plafond_euros=10.0, max_corrections=2),
        {"configurable": {"thread_id": "front-echec"}},
    )

    assert etat["corrections_faites"] == 2
    assert publications == []


# ── LA DOCUMENTATION LOCALE DE NEXT ────────────────────────────────────

@pytest.mark.skipif(
    not (SQUELETTE / "node_modules" / "next").is_dir(),
    reason="dépendances du squelette non installées",
)
class TestDocsLocales:
    """Ces tests lisent la documentation livrée avec le paquet next installé.

    Ils sont la parade au piège décrit dans DEMARRAGE-V2.md : un modèle
    entraîné sur Next 15 écrit `middleware.ts`, le build passe, et le fichier
    ne s'exécute jamais. Aucune porte automatique n'attrape ça, d'où le fait
    de mettre le fait sous les yeux du modèle plutôt que de l'espérer.
    """

    def test_la_convention_renommee_est_annoncee_comme_telle(self):
        from utils.docs_next import conventions

        table = {c["fichier"]: c["resume"] for c in conventions(SQUELETTE)}
        assert "middleware.js" in table
        assert "deprecated" in table["middleware.js"].lower()
        assert "proxy" in table["middleware.js"].lower()

    def test_les_interdits_de_lexport_statique_sont_extraits(self):
        from utils.docs_next import contraintes_export

        interdits = " · ".join(contraintes_export(SQUELETTE))
        assert "Server Actions" in interdits
        assert "Headers" in interdits

    def test_le_bloc_de_prompt_reste_court(self):
        """Il est payé à chaque appel : on y met les faits qui cassent en
        silence, rien d'autre."""
        from utils.docs_next import digest

        bloc = digest(SQUELETTE)
        assert "A RAISON" in bloc
        assert len(bloc) < 6000

    def test_sans_documentation_locale_le_bloc_est_vide(self, tmp_path):
        from utils.docs_next import digest

        assert digest(tmp_path) == ""
