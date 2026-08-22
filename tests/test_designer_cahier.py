"""Tests du cahier des charges transmis au designer — sans aucun appel API.

C'est le chaînon qui manquait : la maquette décrite dans brief.md doit
atteindre le designer. Ces tests verrouillent ce branchement pour qu'une
refactorisation ne le débranche pas à nouveau en silence.
"""
import json

from agents.designer import DesignerAgent

PLAN = {
    "projet": "test",
    "style_guide": {"couleurs": {}, "fonts": {}},
    "taches": [
        {"agent": "copywriter", "priorite": 1, "instruction": "Rédige les textes"},
        {"agent": "designer", "priorite": 2,
         "instruction": "Page unique centrée, plein écran, sans scroll."},
    ],
}


def _config(proj, site: dict):
    (proj.root / "config.json").write_text(
        json.dumps({"site": site}, ensure_ascii=False), encoding="utf-8"
    )


def test_cahier_reprend_instruction_sections_et_note(proj):
    _config(proj, {
        "sections": [
            "Hero — deux colonnes : portrait à gauche + accroche à droite",
            "Footer — pleine largeur",
        ],
        "_note_sections": "Corps en deux colonnes, gauche étroite.",
    })
    cahier = DesignerAgent(proj).cahier_des_charges(PLAN)

    # L'instruction destinée au designer, pas celle du copywriter
    assert "Page unique centrée" in cahier
    assert "Rédige les textes" not in cahier
    # Les libellés riches des sections, dans l'ordre et numérotés
    assert "1. Hero — deux colonnes" in cahier
    assert "2. Footer — pleine largeur" in cahier
    # La contrainte globale de mise en page
    assert "gauche étroite" in cahier
    # La règle de préséance sur les conventions par défaut
    assert "fait autorité" in cahier


def test_cahier_ramasse_toutes_les_notes_y_compris_sous_style(proj):
    """Toute clé _note… est une consigne : elle doit remonter au designer."""
    _config(proj, {
        "sections": ["Contact — lien mailto"],
        "_note_sections": "Page unique sans scroll.",
        "style": {
            "_note_formulaire": "PAS de formulaire de contact, un simple lien mailto.",
            "ambiance": "éditorial patiné",
        },
    })
    cahier = DesignerAgent(proj).cahier_des_charges(PLAN)
    assert "Page unique sans scroll." in cahier
    assert "PAS de formulaire de contact" in cahier
    # une valeur ordinaire de style n'est pas une consigne, elle ne remonte pas ici
    assert "éditorial patiné" not in cahier


def test_cahier_vide_si_projet_ne_decrit_rien(proj):
    _config(proj, {})
    plan_sans_designer = {"taches": [{"agent": "copywriter", "instruction": "x"}]}
    assert DesignerAgent(proj).cahier_des_charges(plan_sans_designer) == ""


def test_cahier_tolere_un_plan_incomplet(proj):
    """Un plan sans clé 'taches' ne doit pas faire planter le designer."""
    _config(proj, {"sections": ["Hero"]})
    cahier = DesignerAgent(proj).cahier_des_charges({})
    assert "1. Hero" in cahier
