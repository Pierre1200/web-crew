"""Tests des agents front : le transport des fichiers, les garde-fous, les tokens.

Aucun appel API. Ce qui est testé ici est tout ce qui se passe AUTOUR de
l'appel, c'est-à-dire tout ce qui peut abîmer un projet même quand le modèle
répond bien.
"""
import pytest

from agents.front import (
    FichierRefuse,
    appliquer_correctifs,
    appliquer_tokens,
    chemin_sur,
    decouper_fichiers,
    ecrire_fichiers,
    valeur_sure,
)


# ── LE TRANSPORT ───────────────────────────────────────────────────────

def test_les_fichiers_voyagent_hors_json():
    """Un TSX entier échappé dans du JSON, c'est ce qui a lâché deux fois sur
    douze au premier run réel. Ici, rien à échapper."""
    reponse = """Voici les fichiers.

=== FICHIER: lib/types.ts ===
export type Realisation = {
  slug: string;   // avec des "guillemets", des \\ et des {accolades}
};
=== FIN ===

=== FICHIER: app/page.tsx ===
export default function Accueil() { return <h1>Bonjour</h1>; }
=== FIN ===
"""
    fichiers = decouper_fichiers(reponse)

    assert set(fichiers) == {"lib/types.ts", "app/page.tsx"}
    assert 'des "guillemets"' in fichiers["lib/types.ts"]
    assert fichiers["app/page.tsx"].endswith("\n")


def test_un_fichier_tronque_est_ignore_et_non_ecrit_a_moitie():
    """Écrire un fichier coupé serait pire que ne rien écrire : le build
    échouerait sur une erreur de syntaxe au lieu de dire ce qui manque."""
    reponse = """=== FICHIER: lib/complet.ts ===
export const a = 1;
=== FIN ===

=== FICHIER: lib/coupe.ts ===
export const b = 2
"""
    fichiers = decouper_fichiers(reponse)

    assert "lib/complet.ts" in fichiers
    assert "lib/coupe.ts" not in fichiers


def test_reponse_sans_marqueur_ne_donne_aucun_fichier():
    assert decouper_fichiers("Bien sûr ! Voici le code :\n\nconst x = 1;") == {}


# ── LES GARDE-FOUS ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "chemin",
    [
        "../../etc/passwd",       # sortir du projet
        "lib/../../ailleurs.ts",  # y sortir par le milieu
        "/etc/passwd",            # chemin absolu
        "next.config.ts",         # hors du périmètre du crew
        "package.json",
        "app/base.css",           # fichier du squelette
        "composants/Enveloppe.tsx",
        "lib/contenu.ts",
    ],
)
def test_ecritures_hors_perimetre_refusees(chemin):
    """Le squelette est ce qui rend le résultat prévisible. Un modèle qui
    réécrit next.config.ts ou base.css le défait."""
    with pytest.raises(FichierRefuse):
        chemin_sur(chemin)


@pytest.mark.parametrize(
    "chemin",
    ["site.config.ts", "lib/types.ts", "lib/data/realisations.ts",
     "contenu/blog/premier.json", "composants/Carte.tsx", "app/blog/page.tsx",
     "app/composants.css", "./lib/types.ts"],
)
def test_ecritures_du_perimetre_acceptees(chemin):
    assert chemin_sur(chemin)


def test_un_refus_narrete_pas_les_autres_ecritures(tmp_path):
    """Une seule mauvaise ligne ne doit pas faire perdre tout un appel payé."""
    ecrits, refuses = ecrire_fichiers(
        tmp_path,
        {
            "lib/types.ts": "export type A = { id: string };\n",
            "next.config.ts": "// tentative\n",
        },
    )

    assert ecrits == ["lib/types.ts"]
    assert len(refuses) == 1
    assert not (tmp_path / "next.config.ts").exists()
    assert (tmp_path / "lib" / "types.ts").exists()


# ── LES TOKENS DE CHARTE ───────────────────────────────────────────────

CHARTE = """:root {
  --fond: #ffffff;
  --encre: #1f1d1b;
  --police-titre: Georgia, serif;
}
"""


def test_les_valeurs_remplacent_sans_toucher_a_la_structure():
    """Le modèle ne peut pas casser une feuille qu'il n'écrit pas."""
    nouvelle, ignores = appliquer_tokens(
        CHARTE, {"fond": "#f6efe4", "police-titre": '"Fraunces", serif'}
    )

    assert "--fond: #f6efe4;" in nouvelle
    assert '--police-titre: "Fraunces", serif;' in nouvelle
    assert "--encre: #1f1d1b;" in nouvelle  # non touché
    assert ignores == []


def test_une_valeur_qui_ferme_la_regle_est_refusee():
    """Sans ce contrôle, une valeur pourrait ajouter des règles arbitraires."""
    _, ignores = appliquer_tokens(CHARTE, {"fond": "red; } body { display: none"})
    assert len(ignores) == 1
    assert "refusée" in ignores[0]


def test_une_valeur_qui_appelle_un_tiers_est_refusee():
    """`url(...)` ferait sortir une requête vers un domaine étranger depuis la
    feuille de style, sans que rien ne le montre dans le HTML."""
    assert not valeur_sure("url(https://tiers.example/pixel.png)")
    assert not valeur_sure("@import 'https://tiers.example/x.css'")
    assert valeur_sure("#b5613f")
    assert valeur_sure("clamp(1rem, 2vw, 1.5rem)")


def test_un_token_invente_est_signale_et_sans_effet():
    nouvelle, ignores = appliquer_tokens(CHARTE, {"couleur-magique": "#123456"})
    assert nouvelle == CHARTE
    assert "absent de la charte" in ignores[0]


# ── LES CORRECTIFS VISUELS ─────────────────────────────────────────────

def test_les_correctifs_sempilent_dans_le_fichier_prevu(tmp_path):
    (tmp_path / "app").mkdir()
    correctifs = tmp_path / "app" / "correctifs.css"
    correctifs.write_text("/* en-tête */\n", encoding="utf-8")

    nombre = appliquer_correctifs(
        tmp_path,
        [
            {"zone": "hero", "gravite": "majeur", "constat": "titre trop bas",
             "correction_css": ".hero { padding-top: 2rem; }"},
            {"zone": "pied", "constat": "sans correctif", "correction_css": ""},
        ],
    )

    contenu = correctifs.read_text(encoding="utf-8")
    assert nombre == 1
    assert ".hero { padding-top: 2rem; }" in contenu
    assert contenu.startswith("/* en-tête */")


def test_un_constat_ne_peut_pas_fermer_son_commentaire(tmp_path):
    """« */ » dans un constat ferait passer la suite du texte pour du CSS."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "correctifs.css").write_text("", encoding="utf-8")

    appliquer_correctifs(
        tmp_path,
        [{"zone": "z", "constat": "fin */ body { display: none } /*",
          "correction_css": ".a { color: red; }"}],
    )

    lignes = (tmp_path / "app" / "correctifs.css").read_text(encoding="utf-8").splitlines()
    constat = next(l for l in lignes if "display: none" in l)

    # Le texte est conservé, mais il reste À L'INTÉRIEUR du commentaire : la
    # ligne s'ouvre et se ferme une seule fois. Un « /* » orphelin au milieu
    # est inoffensif, les commentaires CSS ne s'imbriquent pas.
    assert constat.startswith("/*") and constat.endswith("*/")
    assert "*/" not in constat[2:-2]
