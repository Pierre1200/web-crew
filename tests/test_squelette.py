"""Tests de l'installation du squelette et de la publication."""
import pytest

from utils import squelette as mod
from utils.squelette import (
    InstallationImpossible,
    _appartient_au_crew,
    installer,
    publier,
)


@pytest.fixture
def faux_squelette(tmp_path, monkeypatch):
    """Un squelette minuscule, aux mêmes règles que le vrai."""
    racine = tmp_path / "squelette"
    (racine / "app").mkdir(parents=True)
    (racine / "lib" / "data").mkdir(parents=True)
    (racine / "node_modules" / "next").mkdir(parents=True)

    (racine / "app" / "base.css").write_text("/* invariant */", encoding="utf-8")
    (racine / "app" / "charte.css").write_text("/* au crew */", encoding="utf-8")
    (racine / "app" / "page.tsx").write_text("// au crew", encoding="utf-8")
    (racine / "lib" / "site.ts").write_text("// invariant", encoding="utf-8")
    (racine / "lib" / "data" / "plan.ts").write_text("// au crew", encoding="utf-8")
    (racine / "node_modules" / "next" / "gros.js").write_text("x" * 100, encoding="utf-8")

    monkeypatch.setattr(mod, "RACINE_SQUELETTE", racine)
    return racine


def test_node_modules_nest_jamais_copie(proj, faux_squelette):
    """Copier node_modules ferait 200 Mo par projet, et Turbopack refuse de
    toute façon un dossier partagé par lien symbolique."""
    installer(proj)
    assert not (proj.site_dir / "node_modules").exists()


def test_installation_copie_tout_le_reste(proj, faux_squelette):
    rapport = installer(proj)

    assert rapport["neuf"] is True
    assert set(rapport["ecrits"]) == {
        "app/base.css", "app/charte.css", "app/page.tsx",
        "lib/site.ts", "lib/data/plan.ts",
    }


def test_relancer_linstallation_necrase_rien(proj, faux_squelette):
    """Relancer sur un projet en cours doit être sans danger."""
    installer(proj)
    (proj.site_dir / "app" / "page.tsx").write_text("// le travail du crew", encoding="utf-8")

    rapport = installer(proj)

    assert rapport["ecrits"] == []
    assert (proj.site_dir / "app" / "page.tsx").read_text(encoding="utf-8") == "// le travail du crew"


def test_forcer_rafraichit_le_squelette_sans_toucher_au_travail(proj, faux_squelette):
    """Le cas qui compte : on a corrigé le squelette, les projets en cours
    doivent en profiter sans perdre une ligne de leur contenu."""
    installer(proj)
    (proj.site_dir / "app" / "base.css").write_text("/* vieille version */", encoding="utf-8")
    (proj.site_dir / "app" / "charte.css").write_text("/* la charte du client */", encoding="utf-8")
    (proj.site_dir / "app" / "page.tsx").write_text("// la page du client", encoding="utf-8")

    rapport = installer(proj, forcer=True)

    assert "app/base.css" in rapport["ecrits"]
    assert (proj.site_dir / "app" / "base.css").read_text(encoding="utf-8") == "/* invariant */"
    assert (proj.site_dir / "app" / "charte.css").read_text(encoding="utf-8") == "/* la charte du client */"
    assert (proj.site_dir / "app" / "page.tsx").read_text(encoding="utf-8") == "// la page du client"


def test_les_dossiers_du_crew_sont_proteges_en_entier():
    assert _appartient_au_crew("contenu/blog/premier.json")
    assert _appartient_au_crew("lib/data/realisations.ts")
    assert not _appartient_au_crew("lib/dates.ts")


def test_publier_vide_output_avant_de_copier(proj, faux_squelette):
    """Un fichier d'un ancien run qui survit est un fantôme servi en ligne."""
    (proj.site_dir / "out").mkdir(parents=True)
    (proj.site_dir / "out" / "index.html").write_text("<html>neuf</html>", encoding="utf-8")
    proj.output_dir.mkdir(parents=True, exist_ok=True)
    (proj.output_dir / "fantome.html").write_text("vieux", encoding="utf-8")

    fichiers = publier(proj)

    assert fichiers == 1
    assert not (proj.output_dir / "fantome.html").exists()
    assert (proj.output_dir / "index.html").read_text(encoding="utf-8") == "<html>neuf</html>"


def test_publier_sans_build_le_dit(proj, faux_squelette):
    with pytest.raises(InstallationImpossible, match="npm run build"):
        publier(proj)
