"""L'ÉTAT DU GRAPHE : ce qui circule d'un nœud à l'autre.

En LangGraph, un nœud ne reçoit pas d'arguments et ne renvoie pas d'objet : il
lit l'état et renvoie un dictionnaire PARTIEL, que le graphe fusionne. Par
défaut, une clé renvoyée écrase l'ancienne valeur.

`Annotated[float, add]` change cette règle : au lieu d'écraser, LangGraph
applique la fonction. Chaque nœud renvoie donc ce qu'IL VIENT de dépenser, et
le total se fait tout seul. C'est ce qui permet une garde de budget fiable :
personne n'a à se souvenir de lire puis réécrire le total, donc personne ne
peut l'oublier.

Analogie C : sans réducteur, `etat.cout = x` ; avec, `etat.cout += x`, mais
imposé par le type plutôt que par la discipline de celui qui écrit le nœud.
"""
from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict


class Depense(TypedDict):
    """Ce qu'un nœud a consommé. Une ligne par appel de nœud payant."""
    noeud: str
    modele: str
    tokens_entree: int
    tokens_sortie: int
    euros: float
    tarife: bool  # False si le modèle n'est pas dans utils/tarifs.py


class EtatCrew(TypedDict, total=False):
    # --- Les entrées, posées au lancement ---------------------------------
    projet: str
    plafond_euros: float
    max_corrections: int
    passes_visuelles: int
    valider_a_la_main: bool
    forcer_gabarits: bool

    # --- Ce que les nœuds produisent --------------------------------------
    plan: dict
    agents_planifies: list[str]
    direction_reutilisee: bool
    validation: dict
    critique: dict
    correctifs_appliques: int
    pages_collections: int

    # --- Les compteurs de boucle ------------------------------------------
    # Sans eux, un cycle « corriger puis revalider » tourne indéfiniment sur un
    # défaut que la réparation ne sait pas réparer.
    corrections_faites: int
    passes_faites: int

    # --- Les cumuls, tenus par les réducteurs ------------------------------
    cout_euros: Annotated[float, add]
    depenses: Annotated[list[Depense], add]
    journal: Annotated[list[str], add]

    # --- La sortie de secours ----------------------------------------------
    # Renseigné quand le graphe s'arrête autrement qu'en allant au bout :
    # « plafond », « refus_humain », « capture_indisponible ».
    arret: str


def etat_initial(
    projet: str,
    plafond_euros: float,
    max_corrections: int,
    passes_visuelles: int,
    valider_a_la_main: bool,
    forcer_gabarits: bool = False,
) -> EtatCrew:
    """L'état de départ, avec TOUS les compteurs à zéro.

    Les initialiser ici plutôt que de compter sur `.get(cle, 0)` dans chaque
    nœud : une clé absente d'un état persisté est un piège au redémarrage.
    """
    return {
        "projet": projet,
        "plafond_euros": plafond_euros,
        "max_corrections": max_corrections,
        "passes_visuelles": passes_visuelles,
        "valider_a_la_main": valider_a_la_main,
        "forcer_gabarits": forcer_gabarits,
        "corrections_faites": 0,
        "passes_faites": 0,
        "cout_euros": 0.0,
        "depenses": [],
        "journal": [],
    }
