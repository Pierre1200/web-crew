"""
Filet de sécurité autour de output/ — zéro token, pur Python.

Principe fondateur : **output/ est JETABLE**. Chaque génération l'écrase.
Tout ce qui est corrigé à la main dedans meurt au run suivant : la valeur
doit remonter dans brief.md ou config.json, sinon elle n'existe pas.

Mais une génération coûte de l'argent, et rien ne garantit que la nouvelle
version vaut mieux que l'ancienne. D'où ce module : avant d'écraser, on
copie output/ dans output_prev/. On peut alors comparer les deux versions
et revenir en arrière si le run payé a produit un rendu moins bon.
"""
from __future__ import annotations
import shutil
from pathlib import Path

# Nom du dossier de sauvegarde, à côté de output/
DOSSIER_PREV = "output_prev"

# Fichiers dont on compare le contenu ligne à ligne dans le diff
_EXTENSIONS_TEXTE = {".html", ".css", ".js", ".xml", ".txt", ".json", ".svg"}


def dossier_precedent(project) -> Path:
    """Chemin du dossier de sauvegarde du projet."""
    return project.root / DOSSIER_PREV


def sauvegarder_output(project) -> bool:
    """Copie output/ vers output_prev/ avant une régénération.

    Retourne True si une sauvegarde a été faite, False s'il n'y avait rien
    à sauvegarder (premier run). Écrase la sauvegarde précédente : on ne
    garde qu'un seul niveau d'annulation, suffisant pour comparer un run
    au précédent sans transformer le projet en dépôt d'archives.
    """
    source = project.output_dir
    if not source.is_dir() or not any(source.iterdir()):
        return False

    cible = dossier_precedent(project)
    if cible.exists():
        shutil.rmtree(cible)
    shutil.copytree(source, cible)
    return True


def restaurer_output(project) -> bool:
    """Remet output_prev/ à la place de output/ — annule le dernier run.

    Retourne False s'il n'y a aucune sauvegarde à restaurer.
    """
    source = dossier_precedent(project)
    if not source.is_dir():
        return False

    cible = project.output_dir
    if cible.exists():
        shutil.rmtree(cible)
    shutil.copytree(source, cible)
    return True


def _fichiers_relatifs(dossier: Path) -> set[str]:
    """Chemins relatifs de tous les fichiers d'un dossier, récursivement."""
    if not dossier.is_dir():
        return set()
    return {
        str(f.relative_to(dossier))
        for f in dossier.rglob("*")
        if f.is_file()
    }


def _compter_lignes(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return 0


def comparer(project) -> dict:
    """Compare output/ (actuel) et output_prev/ (sauvegarde).

    Retourne {"disponible": bool, "ajoutes": [...], "supprimes": [...],
              "modifies": [{"fichier", "lignes_avant", "lignes_apres"}],
              "identiques": [...]}.

    Volontairement un résumé par fichier, pas un diff ligne à ligne : le but
    est de répondre à « qu'est-ce que mon run a changé ? » en un coup d'œil.
    """
    actuel = project.output_dir
    precedent = dossier_precedent(project)

    if not precedent.is_dir():
        return {"disponible": False, "ajoutes": [], "supprimes": [],
                "modifies": [], "identiques": []}

    fichiers_actuels = _fichiers_relatifs(actuel)
    fichiers_precedents = _fichiers_relatifs(precedent)

    ajoutes = sorted(fichiers_actuels - fichiers_precedents)
    supprimes = sorted(fichiers_precedents - fichiers_actuels)

    modifies, identiques = [], []
    for nom in sorted(fichiers_actuels & fichiers_precedents):
        f_actuel, f_precedent = actuel / nom, precedent / nom
        if f_actuel.read_bytes() == f_precedent.read_bytes():
            identiques.append(nom)
            continue
        if Path(nom).suffix.lower() in _EXTENSIONS_TEXTE:
            modifies.append({
                "fichier": nom,
                "lignes_avant": _compter_lignes(f_precedent),
                "lignes_apres": _compter_lignes(f_actuel),
            })
        else:
            modifies.append({"fichier": nom, "lignes_avant": None, "lignes_apres": None})

    return {
        "disponible": True,
        "ajoutes": ajoutes,
        "supprimes": supprimes,
        "modifies": modifies,
        "identiques": identiques,
    }
