"""Tests de la classe Project — la pièce centrale de l'architecture plugin."""
import json


def test_chemins_derives_du_nom(proj):
    assert proj.root.name == proj.name
    assert proj.brief_path == proj.root / "brief.md"
    assert proj.config_path == proj.root / "config.json"
    assert proj.output_dir == proj.root / "output"


def test_setup_dirs_cree_tous_les_dossiers(proj):
    for d in (proj.data_dir, proj.output_dir, proj.temp_dir, proj.logs_dir):
        assert d.is_dir()


def test_fichiers_requis_manquants(proj):
    assert proj.fichiers_requis_manquants() == ["brief.md", "config.json"]

    proj.brief_path.write_text("Fais un beau site.", encoding="utf-8")
    assert proj.fichiers_requis_manquants() == ["config.json"]

    proj.config_path.write_text("{}", encoding="utf-8")
    assert proj.fichiers_requis_manquants() == []


def test_load_config_et_brief(proj):
    proj.brief_path.write_text("Le brief.", encoding="utf-8")
    proj.config_path.write_text(
        json.dumps({"client": {"nom": "Test"}}), encoding="utf-8"
    )
    assert proj.load_brief() == "Le brief."
    assert proj.load_config()["client"]["nom"] == "Test"
