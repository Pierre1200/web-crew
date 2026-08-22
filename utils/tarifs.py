"""
Tarifs des modèles et conversion en euros.

Anthropic facture en DOLLARS. Les montants en euros affichés par le crew sont
donc des estimations : le montant réellement débité dépend du taux appliqué le
jour de la facturation, et des éventuels frais de conversion de la carte.

Deux choses à tenir à jour ici, et nulle part ailleurs :
  - TARIFS, si Anthropic change ses prix ou si un modèle est ajouté
  - TAUX_EURO, de temps en temps

Un modèle absent de TARIFS n'est pas une erreur : le compteur affiche alors les
tokens sans montant, plutôt que d'inventer un prix faux.
"""
from __future__ import annotations

# Prix en dollars par MILLION de tokens : (entrée, sortie).
# Relevés le 22 août 2026 sur la grille publique d'Anthropic.
TARIFS = {
    "claude-opus-5":    (5.0, 25.0),
    "claude-sonnet-5":  (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Combien vaut un dollar en euros. À réajuster de temps en temps : une variation
# de quelques centimes ne change rien à une facture de 3 €, mais autant que le
# chiffre affiché reste crédible.
TAUX_EURO = 0.92

# Symbole affiché, pour n'avoir qu'un endroit à changer si tu préfères le dollar.
DEVISE = "€"


def cout_dollars(modele: str, tokens_entree: int, tokens_sortie: int) -> float | None:
    """Coût d'un appel en dollars, ou None si le modèle n'est pas tarifé."""
    tarif = TARIFS.get(modele)
    if tarif is None:
        return None
    prix_entree, prix_sortie = tarif
    return tokens_entree / 1e6 * prix_entree + tokens_sortie / 1e6 * prix_sortie


def cout_euros(modele: str, tokens_entree: int, tokens_sortie: int) -> float | None:
    """Coût estimé en euros, ou None si le modèle n'est pas tarifé."""
    dollars = cout_dollars(modele, tokens_entree, tokens_sortie)
    return None if dollars is None else dollars * TAUX_EURO


# Espace fine insécable (U+202F) : le séparateur de milliers en français.
# Nommée explicitement, sinon on ne la distingue pas d'une espace ordinaire
# en lisant le code, ni en écrivant un test.
SEPARATEUR_MILLIERS = " "


def formater_nombre(valeur: int) -> str:
    """52000 → « 52 000 ».

    Formater le nombre à part évite le piège du remplacement global des
    virgules, qui avalait aussi celles de la phrase autour.
    """
    return f"{valeur:,}".replace(",", SEPARATEUR_MILLIERS)


def formater(montant: float | None) -> str:
    """Montant lisible. Les très petites sommes ne s'affichent pas à 0,00.

    Voir « 0,00 € » après un appel qu'on vient de payer donne l'impression que
    le compteur est cassé : en dessous du centime, on l'écrit autrement.
    """
    if montant is None:
        return "?"
    if montant < 0.01:
        return f"< 0,01 {DEVISE}"
    return f"{montant:.2f}".replace(".", ",") + f" {DEVISE}"
