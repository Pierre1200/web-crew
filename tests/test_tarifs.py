"""Tests des tarifs et de la conversion en euros.

Un compteur de coût faux est pire que pas de compteur : on prend des décisions
de budget dessus. Chaque calcul est donc vérifié à la main.
"""
from utils import tarifs
from utils.tarifs import (
    SEPARATEUR_MILLIERS,
    TARIFS,
    cout_dollars,
    cout_euros,
    formater,
    formater_nombre,
)


def test_cout_dollars_calcul_verifiable():
    # 1 M de tokens d'entrée à 5 $, 1 M de sortie à 25 $
    assert cout_dollars("claude-opus-5", 1_000_000, 1_000_000) == 30.0
    # 100 000 in (0,50 $) + 20 000 out (0,50 $)
    assert cout_dollars("claude-opus-5", 100_000, 20_000) == 1.0


def test_chaque_modele_tarife_donne_un_montant():
    for modele in TARIFS:
        assert cout_dollars(modele, 1000, 1000) > 0


def test_modele_inconnu_ne_donne_pas_de_prix_invente():
    """Mieux vaut « ? » qu'un montant faux."""
    assert cout_dollars("modele-qui-nexiste-pas", 1000, 1000) is None
    assert cout_euros("modele-qui-nexiste-pas", 1000, 1000) is None


def test_conversion_en_euros_applique_le_taux(monkeypatch):
    monkeypatch.setattr(tarifs, "TAUX_EURO", 0.5)
    assert cout_euros("claude-opus-5", 1_000_000, 1_000_000) == 15.0


def test_formatage_a_la_francaise():
    assert formater(1.5) == "1,50 €"
    assert formater(0.0) == "< 0,01 €"
    assert formater(None) == "?"


def test_montant_infime_ne_s_affiche_pas_a_zero():
    """« 0,00 € » après un appel qu'on vient de payer ferait croire à une panne."""
    assert formater(0.004) == "< 0,01 €"
    assert formater(0.01) == "0,01 €"


def test_formater_nombre_separe_les_milliers():
    """Séparateur français : espace fine insécable, pas la virgule anglaise."""
    e = SEPARATEUR_MILLIERS
    assert formater_nombre(52_000) == f"52{e}000"
    assert formater_nombre(999) == "999"
    assert formater_nombre(1_234_567) == f"1{e}234{e}567"
    assert "," not in formater_nombre(52_000)


def test_ordre_de_grandeur_d_un_run_complet():
    """Garde-fou : si un tarif est saisi de travers, l'ordre de grandeur saute."""
    cout = (
        cout_euros("claude-opus-5", 23_000, 61_000)
        + cout_euros("claude-sonnet-5", 24_000, 11_000)
        + cout_euros("claude-haiku-4-5", 5_000, 1_000)
    )
    assert 1.0 < cout < 4.0
