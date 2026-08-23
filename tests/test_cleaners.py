"""Tests des utilitaires de nettoyage — fonctions pures, zéro token."""
import pytest

from utils.cleaners import (
    compact_json,
    strip_markdown_fences,
    parse_json_safe,
    extract_css_classes,
    clean_code_output,
)


# ── strip_markdown_fences ──────────────────────────────────────────

def test_fences_texte_nu_inchange():
    assert strip_markdown_fences('{"a": 1}') == '{"a": 1}'

def test_fences_avec_langage():
    assert strip_markdown_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

def test_fences_sans_langage():
    assert strip_markdown_fences('```\ndu code\n```') == 'du code'


# ── parse_json_safe ────────────────────────────────────────────────

def test_parse_json_valide():
    assert parse_json_safe('{"cle": "valeur"}') == {"cle": "valeur"}

def test_parse_json_avec_fences():
    assert parse_json_safe('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}

def test_parse_json_tronque_leve_valueerror():
    with pytest.raises(ValueError, match="JSON invalide"):
        parse_json_safe('{"cle": "valeur tronqu')


# ── extract_css_classes ────────────────────────────────────────────

def test_extract_classes_dedoublonne_et_trie():
    css = ".btn { } .card:hover { } .btn { color: red; }"
    assert extract_css_classes(css) == ["btn", "card"]

def test_extract_classes_bem():
    css = ".nav__link { } .btn--primary { }"
    assert extract_css_classes(css) == ["btn--primary", "nav__link"]

def test_extract_classes_ignore_valeurs_decimales():
    # ".5rem" ne doit pas devenir une classe (commence par un chiffre)
    css = ".hero { padding: .5rem; }"
    assert extract_css_classes(css) == ["hero"]


# ── compact_json / clean_code_output ───────────────────────────────

def test_compact_json_sans_espaces():
    assert compact_json({"a": 1, "b": [2, 3]}) == '{"a":1,"b":[2,3]}'

def test_compact_json_preserve_accents():
    assert compact_json({"ville": "Rodez, Aveyron é"}) == '{"ville":"Rodez, Aveyron é"}'

def test_clean_code_output_vide_leve_erreur():
    with pytest.raises(ValueError, match="vide"):
        clean_code_output("```\n\n```")


# ── Diagnostic des JSON invalides ──────────────────────────────────────
#
# Le message disait « probablement tronqué » quelle que soit la cause, et se
# trompait une fois sur deux lors du premier run réel. Ces trois cas sont ceux
# rencontrés en vrai.

def test_diagnostic_fermeture_oubliee_en_cours_de_route():
    """Contenu complet, une accolade manquante : surtout PAS « tronqué »."""
    casse = '{"a": {"b": 1,\n"c": 2,\n"d": 3\n}'
    with pytest.raises(ValueError) as erreur:
        parse_json_safe(casse)
    message = str(erreur.value)
    assert "jamais refermé" in message
    assert "il manque « } »" in message
    assert "pas une troncature" in message


def test_diagnostic_vraie_troncature_dans_une_chaine():
    casse = '{"score": 5, "correction_css": ".hero { padding'
    with pytest.raises(ValueError) as erreur:
        parse_json_safe(casse)
    message = str(erreur.value)
    assert "milieu d'une chaîne" in message
    assert "max_tokens" in message


def test_diagnostic_json_complet_mais_mal_forme():
    with pytest.raises(ValueError) as erreur:
        parse_json_safe('{"a": 1,}')
    message = str(erreur.value)
    assert "n'est pas tronqué" in message
    assert "virgule" in message


def test_diagnostic_ignore_les_accolades_dans_les_chaines():
    """Une accolade entre guillemets n'ouvre pas un conteneur.

    Un correctif CSS dans une réponse en contient toujours : sans cette
    distinction, le diagnostic annoncerait des conteneurs ouverts à tort.
    """
    from utils.cleaners import diagnostiquer_json
    assert "jamais refermé" not in diagnostiquer_json('{"css": "a { b: c }"}')


def test_diagnostic_gere_les_guillemets_echappes():
    from utils.cleaners import diagnostiquer_json
    assert "milieu d'une chaîne" not in diagnostiquer_json('{"t": "il a dit \\"oui\\""}')


def test_message_indique_la_position_du_parseur():
    with pytest.raises(ValueError, match="ligne"):
        parse_json_safe('{"a": 1,}')
