"""Tests du filet de sécurité autour de output/ — zéro token, zéro API.

Ce module protège des runs payants : s'il se trompe, on perd un site généré.
Il mérite donc une couverture stricte.
"""
from utils import snapshot


def _ecrire(proj, nom: str, contenu: str):
    chemin = proj.output_dir / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


def test_sans_output_rien_a_sauvegarder(proj):
    assert snapshot.sauvegarder_output(proj) is False
    assert not snapshot.dossier_precedent(proj).exists()


def test_sauvegarde_puis_restauration(proj):
    _ecrire(proj, "index.html", "<html>version 1</html>")
    assert snapshot.sauvegarder_output(proj) is True

    # le run suivant écrase output/
    _ecrire(proj, "index.html", "<html>version 2 ratée</html>")
    assert (proj.output_dir / "index.html").read_text() == "<html>version 2 ratée</html>"

    assert snapshot.restaurer_output(proj) is True
    assert (proj.output_dir / "index.html").read_text() == "<html>version 1</html>"


def test_sauvegarde_conserve_les_sous_dossiers(proj):
    _ecrire(proj, "assets/logo.svg", "<svg/>")
    snapshot.sauvegarder_output(proj)
    assert (snapshot.dossier_precedent(proj) / "assets" / "logo.svg").exists()


def test_sauvegarde_ecrase_la_precedente(proj):
    _ecrire(proj, "index.html", "v1")
    snapshot.sauvegarder_output(proj)
    _ecrire(proj, "index.html", "v2")
    snapshot.sauvegarder_output(proj)
    assert (snapshot.dossier_precedent(proj) / "index.html").read_text() == "v2"


def test_restauration_supprime_les_fichiers_apparus_depuis(proj):
    _ecrire(proj, "index.html", "v1")
    snapshot.sauvegarder_output(proj)
    _ecrire(proj, "intrus.html", "fichier du run raté")

    snapshot.restaurer_output(proj)
    assert not (proj.output_dir / "intrus.html").exists()


def test_restauration_sans_sauvegarde(proj):
    assert snapshot.restaurer_output(proj) is False


def test_comparer_sans_sauvegarde(proj):
    resultat = snapshot.comparer(proj)
    assert resultat["disponible"] is False


def test_comparer_detecte_ajout_suppression_modification(proj):
    _ecrire(proj, "index.html", "ligne\n" * 10)
    _ecrire(proj, "style.css", ".a{}")
    _ecrire(proj, "vieux.txt", "à supprimer")
    snapshot.sauvegarder_output(proj)

    # le nouveau run : index grossit, style inchangé, vieux disparaît, main.js apparaît
    _ecrire(proj, "index.html", "ligne\n" * 25)
    (proj.output_dir / "vieux.txt").unlink()
    _ecrire(proj, "main.js", "console.log(1)")

    resultat = snapshot.comparer(proj)
    assert resultat["disponible"] is True
    assert resultat["ajoutes"] == ["main.js"]
    assert resultat["supprimes"] == ["vieux.txt"]
    assert resultat["identiques"] == ["style.css"]

    modif = {m["fichier"]: m for m in resultat["modifies"]}
    assert modif["index.html"]["lignes_avant"] == 10
    assert modif["index.html"]["lignes_apres"] == 25


def test_comparer_run_sans_effet(proj):
    _ecrire(proj, "index.html", "identique")
    snapshot.sauvegarder_output(proj)
    resultat = snapshot.comparer(proj)
    assert resultat["modifies"] == []
    assert resultat["identiques"] == ["index.html"]
