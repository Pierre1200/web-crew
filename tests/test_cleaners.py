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
