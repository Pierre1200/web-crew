"""Tests de la porte de build. Aucun npm lancé : on teste l'ANALYSE.

Lancer vraiment lint, tsc et next build prendrait une minute par test et
demanderait un node_modules installé. Ce qui peut casser en silence, ce n'est
pas npm, c'est notre lecture de sa sortie : un jour où le format change, ces
tests le disent, et le graphe cesse de croire qu'un échec est un succès.

Les sorties ci-dessous sont RÉELLES, capturées sur le squelette délibérément
cassé de trois façons différentes.
"""
from pathlib import Path

import pytest

from utils.verifier import (
    OutilsAbsents,
    analyser_build,
    analyser_lint,
    analyser_types,
    resumer,
    verifier,
)

RACINE = Path("/projets/mon-site/site")

SORTIE_TSC = """
> squelette-front@0.1.0 typecheck
> tsc --noEmit

lib/casse.ts(1,14): error TS2322: Type 'string' is not assignable to type 'number'.
lib/data/expos.ts(12,3): error TS2551: Property 'titre' does not exist on type 'Expo'.
"""

SORTIE_ESLINT = """
> squelette-front@0.1.0 lint
> eslint

/projets/mon-site/site/composants/Casse.tsx
  5:19  error  Error: Calling setState synchronously within an effect can trigger cascading renders

  12:3  warning  Unexpected console statement  no-console

✖ 2 problems (1 error, 1 warning)
"""

SORTIE_BUILD = """
> squelette-front@0.1.0 build
> next build

  Creating an optimized production build ...
  Collecting page data using 8 workers ...
Error: export const dynamic = "force-static"/export const revalidate not configured on route "/robots.txt" with "output: export".
    at Object.<anonymous> (.next/server/app/robots.txt/route.js:6:3)

> Build error occurred
Error: Failed to collect page data for /robots.txt
    at ignore-listed frames {
  type: 'Error'
}
"""


def test_types_donnent_fichier_ligne_et_code():
    problemes = analyser_types(SORTIE_TSC)

    assert len(problemes) == 2
    premier = problemes[0]
    assert premier["type"] == "type"
    assert premier["fichier"] == "lib/casse.ts"
    assert premier["ligne"] == 1
    assert premier["regle"] == "TS2322"
    assert "not assignable" in premier["message"]


def test_lint_rend_les_chemins_relatifs_au_projet():
    """Un chemin absolu dans un prompt de réparation ne sert à rien et donne
    au modèle l'arborescence de la machine."""
    problemes = analyser_lint(SORTIE_ESLINT, RACINE)

    assert [p["fichier"] for p in problemes] == ["composants/Casse.tsx"] * 2
    assert problemes[0]["ligne"] == 5
    assert problemes[0]["niveau"] == "erreur"
    assert problemes[1]["niveau"] == "warning"
    assert problemes[1]["regle"] == "no-console"


def test_build_met_le_diagnostic_en_premiere_ligne():
    """La sortie de Next se termine par une accolade : sans ce tri, le résumé
    du terminal afficherait « } »."""
    probleme = analyser_build(SORTIE_BUILD)[0]

    assert probleme["type"] == "build"
    assert probleme["message"].splitlines()[0].startswith("Error: export const dynamic")
    # Le reste de la sortie suit, pour le réparateur.
    assert "Failed to collect page data" in probleme["message"]


def test_build_sans_message_ne_pretend_pas_avoir_compris():
    probleme = analyser_build("")[0]
    assert probleme["type"] == "build"
    assert probleme["message"]


def test_les_couleurs_du_terminal_ne_polluent_pas_le_diagnostic():
    """Les codes ANSI consommeraient des jetons dans le prompt de réparation."""
    from utils.verifier import _sans_couleurs

    assert _sans_couleurs("\x1b[1m\x1b[31mFATAL\x1b[39m\x1b[0m: erreur") == "FATAL: erreur"


def test_resume_lisible_pour_chaque_etape():
    resultat = {
        "valide": False, "etape_echouee": "typecheck",
        "problemes": analyser_types(SORTIE_TSC), "sortie": SORTIE_TSC,
    }
    texte = resumer(resultat)

    assert "typecheck" in texte
    assert "lib/casse.ts:1" in texte
    assert "[TS2322]" in texte


def test_resume_annonce_le_reste_quand_il_y_a_trop_de_problemes():
    problemes = analyser_types(SORTIE_TSC) * 6
    texte = resumer({"valide": False, "etape_echouee": "typecheck",
                     "problemes": problemes, "sortie": ""}, maximum=2)
    assert "et 10 autre(s)" in texte


def test_dossier_sans_package_json_est_refuse_tout_de_suite(tmp_path):
    """Mieux vaut une erreur claire qu'un npm qui échoue trente secondes plus
    tard avec un message d'outil."""
    with pytest.raises(OutilsAbsents):
        verifier(tmp_path)
