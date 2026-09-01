"""LA MESURE DU COÛT, nœud par nœud.

La V1 tient un compteur unique pour tout le run : `BaseAgent.CONSO_RUN`, un
attribut de CLASSE, donc partagé par tous les agents du processus (analogie C :
une variable statique). Il donne le total à la fin, pas le détail par étape.

Le graphe a besoin de l'inverse : combien vient de coûter CE nœud, pour que le
réducteur fasse la somme et que la garde de plafond ait quelque chose à
comparer.

On ne touche pas à la V1 pour autant. On lit le compteur avant, on le relit
après, on fait la différence. C'est exactement lire un compteur matériel de
part et d'autre d'une section de code.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Iterator

from agents.base_agent import BaseAgent
from utils.tarifs import cout_euros

from graphe.etat import Depense


def _instantane() -> dict:
    """Copie profonde du compteur : sans elle, on garderait une référence sur
    les dictionnaires que les agents vont modifier, et la différence serait
    toujours nulle."""
    return copy.deepcopy(BaseAgent.CONSO_RUN)


def _difference(avant: dict, apres: dict, noeud: str) -> list[Depense]:
    """Ce qui a été consommé entre deux instantanés, par modèle.

    Une liste et non un seul enregistrement : un nœud peut appeler deux modèles
    différents (c'est déjà le cas quand un agent surcharge MODEL).
    """
    depenses: list[Depense] = []

    for modele, conso in apres.items():
        precedent = avant.get(modele, {"in": 0, "out": 0})
        entree = conso["in"] - precedent["in"]
        sortie = conso["out"] - precedent["out"]
        if entree <= 0 and sortie <= 0:
            continue

        euros = cout_euros(modele, entree, sortie)
        depenses.append(
            Depense(
                noeud=noeud,
                modele=modele,
                tokens_entree=entree,
                tokens_sortie=sortie,
                # Un modèle absent de la table des tarifs compte pour zéro euro
                # dans la garde. On le SIGNALE plutôt que de le taire : une
                # garde qui ignore une dépense n'est plus une garde.
                euros=euros or 0.0,
                tarife=euros is not None,
            )
        )

    return depenses


@contextmanager
def mesurer(noeud: str) -> Iterator[dict]:
    """Encadre un appel d'agent et renvoie ce qu'il a coûté.

        with mesurer("designer") as facture:
            DesignerAgent(proj).run({"plan": plan})
        return {"cout_euros": facture["euros"], "depenses": facture["lignes"]}

    Le dictionnaire est rempli À LA SORTIE du bloc : il est vide tant qu'on est
    dedans, ce qui n'a pas d'importance puisqu'on le lit après.
    """
    facture: dict = {"euros": 0.0, "lignes": []}
    avant = _instantane()
    try:
        yield facture
    finally:
        # `finally` et non la sortie normale : si l'agent lève une exception
        # après avoir déjà payé un appel, la dépense est réelle et doit être
        # comptée. Une erreur ne rembourse rien.
        lignes = _difference(avant, _instantane(), noeud)
        facture["lignes"] = lignes
        facture["euros"] = sum(ligne["euros"] for ligne in lignes)


def depenses_non_tarifees(depenses: list[Depense]) -> set[str]:
    """Les modèles dont le coût n'a pas pu être calculé. Vide = tout est compté."""
    return {d["modele"] for d in depenses if not d["tarife"]}
