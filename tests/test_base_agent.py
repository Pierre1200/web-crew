"""Tests des mécanismes transverses de BaseAgent (sans aucun appel API)."""
import pytest

from agents.base_agent import BaseAgent
from agents.validator import ValidatorAgent


def test_parse_json_response_valide(proj):
    agent = ValidatorAgent(proj)
    assert agent.parse_json_response('{"ok": true}') == {"ok": True}


def test_parse_json_response_sauvegarde_la_reponse_brute(proj):
    """Une réponse imparsable doit finir dans logs/ AVANT que l'erreur remonte."""
    agent = ValidatorAgent(proj)
    reponse_cassee = '{"taches": [{"agent": "copywr'  # JSON tronqué typique

    with pytest.raises(ValueError):
        agent.parse_json_response(reponse_cassee)

    dump = proj.logs_dir / "validator_reponse_invalide.txt"
    assert dump.exists()
    assert dump.read_text(encoding="utf-8") == reponse_cassee


class _UsageFactice:
    """Simule l'objet usage de l'API (input_tokens / output_tokens)."""
    def __init__(self, tokens_in, tokens_out):
        self.input_tokens = tokens_in
        self.output_tokens = tokens_out


@pytest.fixture(autouse=True)
def _conso_propre():
    """Le compteur d'équipe est un attribut de classe : on le vide entre tests."""
    BaseAgent.CONSO_RUN.clear()
    yield
    BaseAgent.CONSO_RUN.clear()


def test_enregistrer_usage_cumule_par_modele(proj):
    agent = ValidatorAgent(proj)
    agent._enregistrer_usage(_UsageFactice(100, 50))
    agent._enregistrer_usage(_UsageFactice(10, 5))

    conso = BaseAgent.CONSO_RUN[agent.MODEL]
    assert conso == {"in": 110, "out": 55, "appels": 2}
