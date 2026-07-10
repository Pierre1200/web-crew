"""
Fixtures pytest partagées par tous les tests.

Placé à la racine du dépôt : pytest ajoute automatiquement ce dossier au
sys.path, ce qui permet aux tests d'importer agents/ et utils/ sans config.
"""
import uuid
import pytest

import utils.project as project_mod


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """Projet jetable dans un dossier temporaire.

    On détourne _PROJECTS_DIR vers tmp_path (fourni par pytest, nettoyé
    automatiquement) : les tests ne touchent JAMAIS aux vrais projets clients.
    Le nom est unique par test pour éviter que le logger (singleton par nom)
    d'un test précédent pointe vers un dossier temporaire déjà supprimé.
    """
    monkeypatch.setattr(project_mod, "_PROJECTS_DIR", tmp_path)
    p = project_mod.Project(f"test-{uuid.uuid4().hex[:8]}")
    p.setup_dirs()
    return p
