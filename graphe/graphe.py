"""L'ASSEMBLAGE DU GRAPHE.

Ce fichier ne contient aucune logique métier : uniquement les nœuds, les
arêtes, et les conditions de passage. C'est volontaire. Quand une décision de
parcours est écrite ailleurs, on ne peut plus lire le pipeline d'un seul coup
d'œil, et c'est exactement ce que la V1 ne permettait plus.

    préparer → ingestion → orchestration → direction
             → ⏸ FEU VERT (humain)
             → copywriter → designer → seo → collections → mentions
             → contrôle ──erreurs──> réparation ──┐
                  │                               │
                  └───────────<───────────────────┘
             → critique visuelle ⟲ (passes, tant que des correctifs s'appliquent)
             → fin

Deux gardes traversent tout : le plafond en euros, vérifié AVANT chaque nœud
payant, et un compteur par boucle. Une boucle sans compteur finit toujours par
tourner sur un défaut que personne ne sait réparer.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from utils.project import Project

from graphe import noeuds
from graphe.etat import EtatCrew


def _budget_atteint(etat: EtatCrew) -> bool:
    """Le plafond est-il consommé ?

    Comparaison AVANT le nœud et non après : après, la dépense est faite. On ne
    peut pas empêcher un nœud de dépasser le plafond à lui seul, on peut
    seulement refuser d'en lancer un de plus.
    """
    return etat.get("cout_euros", 0.0) >= etat.get("plafond_euros", 0.0)


def _porte(suivant: str):
    """L'arête conditionnelle standard devant un nœud payant."""

    def router(etat: EtatCrew) -> str:
        if etat.get("arret"):
            return "fin"
        if _budget_atteint(etat):
            return "plafond"
        return suivant

    return router


def _apres_controle(etat: EtatCrew) -> str:
    """Réparer, passer à la critique visuelle, ou s'arrêter.

    L'ordre des tests est celui de la V1 : on ne répare que ce qui est
    réparable, et jamais plus de `max_corrections` fois.
    """
    from agents.validator import FIXABLE_TYPES

    if etat.get("arret"):
        return "fin"

    validation = etat.get("validation") or {}
    if validation.get("valide"):
        return _vers_visuel(etat)

    fixables = [p for p in validation.get("erreurs", []) if p["type"] in FIXABLE_TYPES]
    if not fixables:
        return _vers_visuel(etat)
    if etat["corrections_faites"] >= etat["max_corrections"]:
        return _vers_visuel(etat)
    if _budget_atteint(etat):
        return "plafond"
    return "reparation"


def _vers_visuel(etat: EtatCrew) -> str:
    """Entre-t-on dans la boucle visuelle ?"""
    if etat.get("passes_visuelles", 0) <= 0:
        return "fin"
    if _budget_atteint(etat):
        return "plafond"
    return "critique_visuelle"


def _apres_critique(etat: EtatCrew) -> str:
    """Une passe de plus, ou on sort.

    Trois raisons de sortir, dans cet ordre : la capture est impossible, le
    nombre de passes demandé est atteint, ou la dernière passe n'a rien pu
    appliquer. Ce dernier cas est le plus important : rejouer une critique qui
    ne produit aucun correctif applicable, c'est payer pour relire la même page.
    """
    if etat.get("arret"):
        return "fin"
    if etat["passes_faites"] >= etat["passes_visuelles"]:
        return "fin"
    if not etat.get("correctifs_appliques"):
        return "fin"
    if _budget_atteint(etat):
        return "plafond"
    return "critique_visuelle"


def construire() -> StateGraph:
    """Le graphe, non compilé. Séparé de la compilation pour que les tests
    puissent l'inspecter sans ouvrir de base de reprise."""
    g = StateGraph(EtatCrew)

    for nom, fonction in (
        ("preparer", noeuds.preparer),
        ("ingestion", noeuds.ingestion),
        ("orchestration", noeuds.orchestration),
        ("direction", noeuds.direction),
        ("feu_vert", noeuds.feu_vert),
        ("copywriter", noeuds.copywriter),
        ("designer", noeuds.designer),
        ("seo", noeuds.seo),
        ("collections", noeuds.collections),
        ("mentions", noeuds.mentions),
        ("controle", noeuds.controle),
        ("reparation", noeuds.reparation),
        ("critique_visuelle", noeuds.critique_visuelle),
        ("plafond", noeuds.plafond),
        ("fin", noeuds.fin),
    ):
        g.add_node(nom, fonction)

    # Le cadrage : bon marché, et il doit aller jusqu'au feu vert sans
    # interruption, sinon l'humain n'a rien à regarder pour décider.
    g.add_edge(START, "preparer")
    g.add_edge("preparer", "ingestion")
    g.add_edge("ingestion", "orchestration")
    g.add_edge("orchestration", "direction")
    g.add_edge("direction", "feu_vert")

    # L'exécution : une porte devant chaque nœud payant.
    for depart, suivant in (
        ("feu_vert", "copywriter"),
        ("copywriter", "designer"),
        ("designer", "seo"),
        ("seo", "collections"),
    ):
        g.add_conditional_edges(
            depart, _porte(suivant), {suivant: suivant, "plafond": "plafond", "fin": "fin"}
        )

    # Les mentions sont gratuites : elles se font même si le budget est
    # consommé. Un site sans mentions légales est en infraction, pas
    # « incomplet ».
    g.add_edge("collections", "mentions")
    g.add_edge("mentions", "controle")

    g.add_conditional_edges(
        "controle",
        _apres_controle,
        {
            "reparation": "reparation",
            "critique_visuelle": "critique_visuelle",
            "plafond": "plafond",
            "fin": "fin",
        },
    )
    # La boucle : réparer puis revalider. C'est le contrôle qui décide d'en
    # refaire un tour, jamais la réparation elle-même.
    g.add_edge("reparation", "controle")

    g.add_conditional_edges(
        "critique_visuelle",
        _apres_critique,
        {"critique_visuelle": "critique_visuelle", "plafond": "plafond", "fin": "fin"},
    )

    g.add_edge("plafond", "fin")
    g.add_edge("fin", END)
    return g


def chemin_reprise(projet: str):
    """Où vit l'état persisté du graphe, projet par projet."""
    proj = Project(projet)
    proj.temp_dir.mkdir(parents=True, exist_ok=True)
    return proj.temp_dir / "graphe.sqlite"


@contextmanager
def crew(projet: str) -> Iterator:
    """Le graphe compilé, avec sa reprise sur disque.

    LE CHECKPOINTER EST LA RAISON D'ÊTRE DE L'ÉTAPE. Le premier run réel a raté
    deux appels sur douze : sans état persisté, il fallait tout repayer. Ici
    l'état est écrit après chaque nœud, dans un SQLite du projet. Relancer
    reprend au nœud fautif.
    """
    with SqliteSaver.from_conn_string(str(chemin_reprise(projet))) as checkpointer:
        yield construire().compile(checkpointer=checkpointer)
