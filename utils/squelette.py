"""L'INSTALLATION DU SQUELETTE DANS UN PROJET, et la publication du site bâti.

Le crew ne construit pas une application depuis rien : il part du squelette
front validé et ne produit que les variations. Ce module fait les trois gestes
mécaniques autour de ça, tous à zéro jeton :

    installer()             squelette/ → projects/<nom>/site/
    installer_dependances() npm ci, une fois par projet
    publier()               site/out/ → projects/<nom>/output/

`publier` compte autant que le reste : `output/` reste le dossier LIVRÉ, donc
`webcrew diff`, `webcrew restore` et l'audit de sécurité continuent de
fonctionner sans qu'on y touche. C'est ce qui permet de changer de moteur de
génération sans casser les outils qui vivent autour.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

RACINE_SQUELETTE = Path(__file__).resolve().parent.parent / "squelette"

# Ce qui ne se copie jamais : lourd, engendré, ou propre à une machine.
EXCLUS = {"node_modules", ".next", "out", "tsconfig.tsbuildinfo"}

# Les fichiers que le CREW écrit. `installer(forcer=True)` rafraîchit tout le
# reste et ne touche pas à ceux-là : rafraîchir le squelette d'un projet en
# cours ne doit jamais effacer son travail.
#
# Les chemins se terminant par « / » désignent un dossier entier.
FICHIERS_DU_CREW = {
    "site.config.ts",
    "app/charte.css",
    "app/composants.css",
    "app/correctifs.css",
    "app/page.tsx",
    "lib/types.ts",
    "lib/data/",
    "contenu/",
    "public/assets/",
    "public/polices/",
}

DELAI_NPM_S = 600


class InstallationImpossible(RuntimeError):
    """Le squelette est introuvable, ou npm a échoué."""


def _appartient_au_crew(relatif: str) -> bool:
    if relatif in FICHIERS_DU_CREW:
        return True
    return any(
        relatif.startswith(prefixe) for prefixe in FICHIERS_DU_CREW if prefixe.endswith("/")
    )


def installer(project, forcer: bool = False) -> dict:
    """Copie le squelette dans le dossier `site/` du projet.

    PAR DÉFAUT, AUCUN FICHIER EXISTANT N'EST ÉCRASÉ. Relancer l'installation
    sur un projet en cours est donc sans danger : elle ne fait qu'ajouter ce
    qui manque.

    Avec `forcer=True`, les fichiers du squelette sont rafraîchis, sauf ceux de
    FICHIERS_DU_CREW. C'est ce qu'on lance après avoir corrigé le squelette
    lui-même, pour que les projets existants en profitent.
    """
    if not RACINE_SQUELETTE.is_dir():
        raise InstallationImpossible(f"Squelette introuvable : {RACINE_SQUELETTE}")

    cible = project.site_dir
    neuf = not cible.exists()
    ecrits, ignores = [], 0

    for source in sorted(RACINE_SQUELETTE.rglob("*")):
        relatif = source.relative_to(RACINE_SQUELETTE)
        if any(partie in EXCLUS for partie in relatif.parts):
            continue

        destination = cible / relatif
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        if destination.exists() and (not forcer or _appartient_au_crew(str(relatif))):
            ignores += 1
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        ecrits.append(str(relatif))

    return {"neuf": neuf, "ecrits": ecrits, "ignores": ignores, "dossier": str(cible)}


def dependances_presentes(site_dir: Path) -> bool:
    return (Path(site_dir) / "node_modules" / "next").is_dir()


def installer_dependances(site_dir: Path, forcer: bool = False) -> bool:
    """`npm ci` dans le dossier du site. Renvoie True si l'installation a tourné.

    ⚠️ NE PAS RUSER AVEC UN LIEN SYMBOLIQUE vers un node_modules partagé pour
    gagner de la place : Turbopack refuse de construire et échoue sur
    « Symlink [project]/node_modules is invalid, it points out of the
    filesystem root ». Chaque projet a sa propre installation, et c'est le prix
    d'une version de Next épinglée par projet.

    `npm ci` plutôt que `npm install` : il installe EXACTEMENT ce que dit
    package-lock.json, sans jamais le réécrire. C'est la seule façon d'avoir
    la même version de Next dans six mois qu'aujourd'hui.
    """
    site_dir = Path(site_dir)
    if dependances_presentes(site_dir) and not forcer:
        return False

    commande = ["npm", "ci"] if (site_dir / "package-lock.json").exists() else ["npm", "install"]
    try:
        resultat = subprocess.run(
            commande, cwd=site_dir, capture_output=True, text=True, timeout=DELAI_NPM_S
        )
    except FileNotFoundError as e:
        raise InstallationImpossible(
            "npm est introuvable. Node est requis pour bâtir un site V2."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise InstallationImpossible(
            f"npm n'a pas rendu la main en {DELAI_NPM_S} s."
        ) from e

    if resultat.returncode != 0:
        fin = "\n".join((resultat.stderr or resultat.stdout).splitlines()[-20:])
        raise InstallationImpossible(f"{' '.join(commande)} a échoué :\n{fin}")

    return True


def publier(project) -> int:
    """Recopie le site bâti (site/out/) dans output/, le dossier livré.

    On VIDE output/ d'abord : un fichier d'un ancien run qui survit à une
    régénération est un fantôme, servi en ligne sans que rien ne le rattache au
    site actuel. La sauvegarde output_prev/ existe pour revenir en arrière.
    """
    sortie = project.site_dir / "out"
    if not sortie.is_dir():
        raise InstallationImpossible(
            f"{sortie} n'existe pas : `npm run build` n'a pas produit d'export."
        )

    if project.output_dir.exists():
        shutil.rmtree(project.output_dir)
    shutil.copytree(sortie, project.output_dir)

    return sum(1 for chemin in project.output_dir.rglob("*") if chemin.is_file())
