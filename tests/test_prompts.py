"""Tests des prompts des agents front.

Aucun appel API : on vérifie ce que les prompts CONTIENNENT une fois rendus.

Ça paraît trivial, ça ne l'est pas. Un prompt est une f-string de deux mille
mots : `{...}` écrit sans doubler les accolades s'y transforme en `Ellipsis`,
une variable vide efface une section entière, et rien ne le signale. Le défaut
ne se voit qu'en lisant la sortie, c'est-à-dire jamais, jusqu'au jour où le
modèle répond de travers pour une raison qu'on cherche ailleurs.
"""
from pathlib import Path

import pytest

from agents.front import CharteAgent, FrontAgent, ReparateurAgent
from utils.project import Project

SQUELETTE = Path(__file__).resolve().parent.parent / "squelette"


@pytest.fixture
def agents_front(proj):
    """Des agents dont le site pointe sur le vrai squelette.

    Les prompts se construisent à partir du squelette installé : inventaire des
    exports, classes de base.css, documentation locale de Next. Sur un dossier
    vide, ils se rendraient sans erreur et sans contenu, et le test ne
    vérifierait rien.
    """
    agents = []
    for classe in (CharteAgent, FrontAgent, ReparateurAgent):
        agent = classe(proj)
        agent.project.site_dir = SQUELETTE
        agents.append(agent)
    return agents


@pytest.fixture
def prompt_front(agents_front):
    return agents_front[1]._prompt_systeme()


# ── LES ACCIDENTS DE FORMATAGE ─────────────────────────────────────────

@pytest.mark.parametrize("artefact", ["Ellipsis", "dict_keys", "<built-in", "object at 0x", "{}"])
def test_aucun_artefact_de_formatage(agents_front, artefact):
    """Ce qui arrive quand une accolade n'est pas doublée dans une f-string."""
    for agent in agents_front:
        assert artefact not in agent._prompt_systeme(), f"{agent.name} : {artefact}"


def test_aucune_section_vide(agents_front):
    """Une variable vide efface sa section sans rien dire. Deux sauts de ligne
    suivis d'un titre en capitales puis d'une ligne vide en est le symptôme."""
    for agent in agents_front:
        rendu = agent._prompt_systeme()
        assert "\n\n\n" not in rendu, f"{agent.name} : trou dans le prompt"
        assert len(rendu) > 1500, f"{agent.name} : prompt suspectement court"


# ── CE QUE CHAQUE PROMPT DOIT DIRE ─────────────────────────────────────

def test_le_front_decrit_le_format_de_reponse(prompt_front):
    """Les fichiers voyagent entre marqueurs, jamais dans du JSON."""
    assert "=== FICHIER:" in prompt_front
    assert "=== FIN ===" in prompt_front
    assert "N'abrège JAMAIS" in prompt_front


def test_le_front_connait_ce_qui_existe_deja(prompt_front):
    """Sans l'inventaire, le modèle réécrit un second cadre en pointillés et un
    en-tête que l'enveloppe pose déjà."""
    for existant in ("Cadre", "EnteteSection", "Etat", "adressesDuSite", "lireCollection"):
        assert existant in prompt_front, existant
    assert "Une page ne les réécrit jamais" in prompt_front


def test_le_front_connait_les_classes_deja_habillees(prompt_front):
    """Sinon il réécrit un .btn qui existe, ou invente une classe sans style."""
    for classe in ("conteneur", "titre-page", "cadre--4x3", "btn--plein"):
        assert classe in prompt_front, classe


def test_le_front_nomme_les_fichiers_interdits(prompt_front):
    for interdit in ("base.css", "charte.css", "layout.tsx", "next.config.ts"):
        assert interdit in prompt_front, interdit


def test_le_front_impose_lordre_decriture(prompt_front):
    """Le contrat avant les données, les données avant la lecture, la lecture
    avant les pages : produire l'inverse, c'est produire trois versions d'un
    même contrat."""
    rendu = prompt_front
    assert rendu.index("lib/types.ts") < rendu.index("lib/data/*.ts")
    assert rendu.index("lib/data/*.ts") < rendu.index("app/**/page.tsx")


def test_le_front_porte_les_regles_de_maison(prompt_front):
    assert "tiret cadratin" in prompt_front
    assert "`null`" in prompt_front


def test_la_charte_ne_produit_que_des_valeurs(agents_front):
    rendu = agents_front[0]._prompt_systeme()

    assert "TU NE PRODUIS PAS DE CSS" in rendu
    assert "4,5:1" in rendu           # les contrastes sont chiffrés
    assert "url(" in rendu            # et les valeurs dangereuses nommées


def test_le_reparateur_interdit_les_fausses_reparations(agents_front):
    """Faire passer la porte en cassant le site est le pire résultat possible :
    tout est vert et le livrable est mort."""
    rendu = agents_front[2]._prompt_systeme()

    for interdit in ("eslint-disable", "`any`", "supprimer l'appel"):
        assert interdit in rendu.lower() or interdit in rendu, interdit


def test_le_reparateur_connait_les_pannes_deja_rencontrees(agents_front):
    """Les quatre erreurs listées ont toutes été rencontrées pour de vrai en
    écrivant le squelette. C'est de la mémoire du projet, pas de la théorie."""
    rendu = agents_front[2]._prompt_systeme()

    assert "force-static" in rendu
    assert "useSyncExternalStore" in rendu


# ── LA DOCUMENTATION LOCALE ────────────────────────────────────────────

@pytest.mark.skipif(
    not (SQUELETTE / "node_modules" / "next").is_dir(),
    reason="dépendances du squelette non installées",
)
def test_les_prompts_portent_la_documentation_de_la_version_installee(agents_front):
    """La parade au piège middleware.ts contre proxy.ts. Elle ne sert que si
    elle est effectivement dans le prompt."""
    for agent in (agents_front[1], agents_front[2]):
        rendu = agent._prompt_systeme()
        assert "CE BLOC A RAISON" in rendu
        assert "proxy.js" in rendu
