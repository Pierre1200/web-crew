"""Tests de l'agent Critique — uniquement les gardes, aucun appel API."""
import pytest

from agents.critique import CritiqueAgent


def test_critique_sans_textes_erreur_claire(proj):
    """Sans textes.json, le critique doit expliquer quoi faire, pas crasher."""
    (proj.root / "config.json").write_text('{"site": {"sections": []}}', encoding="utf-8")
    agent = CritiqueAgent(proj)
    with pytest.raises(FileNotFoundError, match="generate"):
        agent.run({})
