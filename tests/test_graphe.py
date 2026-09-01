"""Tests du graphe LangGraph. ZÉRO APPEL API.

Ce que ces tests vérifient, et pourquoi chacun compte :

- le réducteur de coût cumule vraiment, sinon la garde de budget compare à un
  total faux et ne garde rien ;
- la garde arrête le graphe AVANT le nœud payant suivant, pas après ;
- les boucles ont une sortie, dans tous les cas de figure ;
- le feu vert arrête l'exécution et un refus ne dépense rien de plus ;
- la mesure du coût est une différence, donc elle ignore ce qui a été dépensé
  avant le nœud.

Les nœuds réels appellent des agents, donc l'API : ils sont remplacés par des
doublures. Ce qu'on teste ici est le CÂBLAGE, pas les agents, qui ont leurs
propres tests.
"""
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.base_agent import BaseAgent
from graphe import graphe as module_graphe
from graphe.couts import mesurer
from graphe.etat import EtatCrew, etat_initial


# ── LA MESURE DU COÛT ──────────────────────────────────────────────────

@pytest.fixture
def compteur_vierge(monkeypatch):
    """CONSO_RUN est un attribut de CLASSE, donc partagé par tout le processus.
    Sans cette remise à zéro, un test hériterait du compteur du précédent."""
    monkeypatch.setattr(BaseAgent, "CONSO_RUN", {})
    return BaseAgent.CONSO_RUN


def _consommer(modele: str, entree: int, sortie: int):
    """Simule ce que fait _enregistrer_usage après un appel API."""
    conso = BaseAgent.CONSO_RUN.setdefault(modele, {"in": 0, "out": 0, "appels": 0})
    conso["in"] += entree
    conso["out"] += sortie
    conso["appels"] += 1


def test_mesurer_ne_compte_que_ce_qui_se_passe_dedans(compteur_vierge):
    _consommer("claude-opus-5", 500_000, 100_000)  # dépense antérieure

    with mesurer("designer") as facture:
        _consommer("claude-opus-5", 100_000, 20_000)

    assert len(facture["lignes"]) == 1
    ligne = facture["lignes"][0]
    assert ligne["tokens_entree"] == 100_000
    assert ligne["tokens_sortie"] == 20_000
    assert ligne["euros"] == pytest.approx(facture["euros"])
    assert ligne["euros"] > 0


def test_mesurer_compte_meme_si_le_noeud_echoue(compteur_vierge):
    """Un appel payé puis une exception : la dépense est réelle."""
    with pytest.raises(RuntimeError):
        with mesurer("designer") as facture:
            _consommer("claude-opus-5", 10_000, 1_000)
            raise RuntimeError("le parsing a échoué après l'appel")

    assert facture["euros"] > 0


def test_modele_non_tarife_est_signale_et_pas_invente(compteur_vierge):
    with mesurer("essai") as facture:
        _consommer("modele-inconnu", 1000, 100)

    assert facture["lignes"][0]["tarife"] is False
    assert facture["euros"] == 0.0


# ── LES ROUTES ─────────────────────────────────────────────────────────

def _etat(**surcharges) -> EtatCrew:
    etat = etat_initial(
        projet="essai", plafond_euros=5.0, max_corrections=2,
        passes_visuelles=0, valider_a_la_main=False,
    )
    etat.update(surcharges)
    return etat


def test_la_porte_laisse_passer_sous_le_plafond():
    assert module_graphe._porte("designer")(_etat(cout_euros=1.0)) == "designer"


def test_la_porte_arrete_au_plafond():
    assert module_graphe._porte("designer")(_etat(cout_euros=5.0)) == "plafond"


def test_la_porte_respecte_un_arret_deja_decide():
    assert module_graphe._porte("designer")(_etat(arret="refus_humain")) == "fin"


def test_site_valide_saute_la_reparation():
    etat = _etat(validation={"valide": True, "erreurs": []})
    assert module_graphe._apres_controle(etat) == "fin"


def test_erreur_non_reparable_ne_boucle_pas():
    """Un défaut qu'aucune méthode ne sait corriger doit sortir, pas tourner."""
    etat = _etat(validation={"valide": False, "erreurs": [{"type": "inconnu_au_bataillon"}]})
    assert module_graphe._apres_controle(etat) == "fin"


def test_erreur_reparable_declenche_une_reparation():
    etat = _etat(validation={"valide": False, "erreurs": [{"type": "js_tronque"}]})
    assert module_graphe._apres_controle(etat) == "reparation"


def test_plafond_de_tentatives_arrete_la_boucle_de_reparation():
    etat = _etat(
        validation={"valide": False, "erreurs": [{"type": "js_tronque"}]},
        corrections_faites=2, max_corrections=2,
    )
    assert module_graphe._apres_controle(etat) == "fin"


def test_boucle_visuelle_sarrete_quand_aucun_correctif_ne_sapplique():
    """Rejouer une critique qui ne produit rien, c'est payer pour relire."""
    etat = _etat(passes_visuelles=3, passes_faites=1, correctifs_appliques=0)
    assert module_graphe._apres_critique(etat) == "fin"


def test_boucle_visuelle_continue_tant_quil_reste_des_passes():
    etat = _etat(passes_visuelles=3, passes_faites=1, correctifs_appliques=4)
    assert module_graphe._apres_critique(etat) == "critique_visuelle"


def test_boucle_visuelle_respecte_le_nombre_de_passes_demande():
    etat = _etat(passes_visuelles=2, passes_faites=2, correctifs_appliques=4)
    assert module_graphe._apres_critique(etat) == "fin"


# ── LA TOPOLOGIE ───────────────────────────────────────────────────────

def test_tous_les_noeuds_sont_cables():
    """Un nœud déclaré mais jamais atteint est du code mort payé à l'écriture."""
    compile_ = module_graphe.construire().compile()
    dessin = compile_.get_graph()
    noeuds = {n for n in dessin.nodes if not n.startswith("__")}
    attendus = {
        "preparer", "ingestion", "orchestration", "direction", "feu_vert",
        "copywriter", "designer", "seo", "collections", "mentions",
        "controle", "reparation", "critique_visuelle", "plafond", "fin",
    }
    assert noeuds == attendus

    arrivees = {arete.target for arete in dessin.edges}
    jamais_atteints = noeuds - arrivees
    assert jamais_atteints == set(), f"nœuds inatteignables : {jamais_atteints}"


# ── LE PARCOURS COMPLET, AVEC DES DOUBLURES ────────────────────────────

def _graphe_double(monkeypatch, couts: dict, validation: dict, critique_correctifs=0):
    """Le vrai graphe, dont chaque nœud payant est remplacé par une doublure
    qui déclare un coût. Le câblage testé est donc bien celui de production."""
    from graphe import noeuds

    def facture(nom):
        def doublure(etat):
            return {"cout_euros": couts.get(nom, 0.0), "journal": [nom]}
        return doublure

    for nom in ("ingestion", "copywriter", "designer", "seo", "collections"):
        monkeypatch.setattr(noeuds, nom, facture(nom))

    monkeypatch.setattr(noeuds, "preparer", lambda e: {"journal": ["preparer"]})
    monkeypatch.setattr(noeuds, "mentions", lambda e: {"journal": ["mentions"]})
    monkeypatch.setattr(
        noeuds, "orchestration",
        lambda e: {
            "plan": {"taches": []},
            "agents_planifies": ["copywriter", "designer", "seo"],
            "cout_euros": couts.get("orchestration", 0.0),
            "journal": ["orchestration"],
        },
    )
    monkeypatch.setattr(
        noeuds, "direction",
        lambda e: {"cout_euros": couts.get("direction", 0.0), "journal": ["direction"]},
    )
    monkeypatch.setattr(
        noeuds, "controle",
        lambda e: {"validation": validation, "journal": ["controle"]},
    )
    monkeypatch.setattr(
        noeuds, "critique_visuelle",
        lambda e: {
            "correctifs_appliques": critique_correctifs,
            "passes_faites": e["passes_faites"] + 1,
            "cout_euros": couts.get("critique_visuelle", 0.0),
            "journal": ["critique_visuelle"],
        },
    )
    return module_graphe.construire().compile(checkpointer=InMemorySaver())


def test_parcours_nominal_va_jusquau_bout_et_additionne(monkeypatch):
    app = _graphe_double(
        monkeypatch,
        couts={"ingestion": 0.2, "orchestration": 0.1, "direction": 0.1,
               "copywriter": 0.5, "designer": 1.5, "seo": 0.15, "collections": 0.3},
        validation={"valide": True, "erreurs": []},
    )
    etat = app.invoke(
        etat_initial("essai", plafond_euros=10.0, max_corrections=2,
                     passes_visuelles=0, valider_a_la_main=False),
        {"configurable": {"thread_id": "nominal"}},
    )

    assert etat["cout_euros"] == pytest.approx(2.85)
    assert "designer" in etat["journal"] and "fin" in etat["journal"]
    assert "arret" not in etat


def test_le_plafond_coupe_avant_le_designer(monkeypatch):
    """Le nœud le plus cher ne doit jamais être lancé si le budget est fini."""
    app = _graphe_double(
        monkeypatch,
        couts={"ingestion": 0.5, "orchestration": 0.3, "direction": 0.3,
               "copywriter": 0.4, "designer": 1.5},
        validation={"valide": True, "erreurs": []},
    )
    etat = app.invoke(
        etat_initial("essai", plafond_euros=1.5, max_corrections=2,
                     passes_visuelles=0, valider_a_la_main=False),
        {"configurable": {"thread_id": "plafond"}},
    )

    assert etat["arret"] == "plafond"
    assert "designer" not in etat["journal"]
    assert etat["cout_euros"] == pytest.approx(1.5)


def test_le_feu_vert_arrete_le_graphe_et_un_refus_ne_depense_rien(monkeypatch):
    couts = {"ingestion": 0.2, "orchestration": 0.1, "direction": 0.1,
             "copywriter": 0.5, "designer": 1.5}
    app = _graphe_double(monkeypatch, couts=couts, validation={"valide": True, "erreurs": []})
    config = {"configurable": {"thread_id": "feu-vert"}}

    etat = app.invoke(
        etat_initial("essai", plafond_euros=10.0, max_corrections=2,
                     passes_visuelles=0, valider_a_la_main=True),
        config,
    )
    # Le graphe s'est arrêté au feu vert, après le cadrage seulement.
    assert "__interrupt__" in etat
    assert etat["cout_euros"] == pytest.approx(0.4)

    etat = app.invoke(Command(resume="non"), config)
    assert etat["arret"] == "refus_humain"
    assert etat["cout_euros"] == pytest.approx(0.4)
    assert "designer" not in etat["journal"]


def test_le_feu_vert_accorde_laisse_le_run_se_terminer(monkeypatch):
    app = _graphe_double(
        monkeypatch,
        couts={"ingestion": 0.2, "designer": 1.5},
        validation={"valide": True, "erreurs": []},
    )
    config = {"configurable": {"thread_id": "feu-vert-oui"}}

    app.invoke(
        etat_initial("essai", plafond_euros=10.0, max_corrections=2,
                     passes_visuelles=0, valider_a_la_main=True),
        config,
    )
    etat = app.invoke(Command(resume="oui"), config)

    assert etat.get("arret") is None
    assert "designer" in etat["journal"]


def test_la_boucle_de_reparation_sarrete_au_nombre_de_tentatives(monkeypatch):
    """Le contrôle échoue toujours : sans compteur, ce test ne finirait jamais."""
    from graphe import noeuds

    # La doublure de réparation est posée AVANT la construction : `construire()`
    # capture les fonctions au moment où il câble le graphe.
    monkeypatch.setattr(
        noeuds, "reparation",
        lambda e: {"corrections_faites": e["corrections_faites"] + 1,
                   "journal": ["reparation"]},
    )
    app = _graphe_double(
        monkeypatch, couts={},
        validation={"valide": False, "erreurs": [{"type": "js_tronque"}]},
    )

    etat = app.invoke(
        etat_initial("essai", plafond_euros=10.0, max_corrections=2,
                     passes_visuelles=0, valider_a_la_main=False),
        {"configurable": {"thread_id": "reparation"}},
    )

    assert etat["corrections_faites"] == 2
    assert etat["journal"].count("reparation") == 2


# ── LE CONTRAT DE L'ÉTAT ───────────────────────────────────────────────

def test_toute_cle_ecrite_par_un_noeud_est_declaree():
    """LangGraph JETTE EN SILENCE une clé absente du schéma.

    Le nœud croit avoir écrit, le suivant lit une clé absente, et l'aiguillage
    part du mauvais côté sans qu'aucune erreur ne soit levée. C'est arrivé avec
    `resultat_porte` : le graphe front bouclait en réparation sans jamais
    publier. Ce test relit les nœuds et compare.
    """
    import ast
    from pathlib import Path

    declarees = set(EtatCrew.__annotations__)
    racine = Path(__file__).resolve().parent.parent
    manquantes = {}

    for fichier in ("graphe/noeuds.py", "graphe/front.py"):
        arbre = ast.parse((racine / fichier).read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Return) and isinstance(noeud.value, ast.Dict)):
                continue
            for cle in noeud.value.keys:
                if isinstance(cle, ast.Constant) and isinstance(cle.value, str):
                    if cle.value not in declarees:
                        manquantes.setdefault(fichier, set()).add(cle.value)

    assert manquantes == {}, f"clés non déclarées dans EtatCrew : {manquantes}"
