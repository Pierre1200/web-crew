"""LE GRAPHE FRONT : le crew branché sur le squelette Next.

Même colonne vertébrale que `graphe/graphe.py`, mais la sortie n'est plus du
HTML écrit par un modèle : c'est un projet Next bâti par un compilateur.

    préparer → squelette → ingestion → orchestration → direction
             → ⏸ FEU VERT
             → copywriter → charte → polices → front
             → PORTE (lint, types, build) ──échec──> réparation ──┐
                  │                                              │
                  └──────────────────<───────────────────────────┘
             → publier (site/out → output)
             → critique visuelle → correctifs.css ──> PORTE (⟲)
             → fin

CE QUI CHANGE VRAIMENT, et c'est tout l'intérêt de l'étape : la porte n'est
plus le jugement d'un modèle sur une page, c'est ESLint, TypeScript et Next.
Trois outils qui ne se trompent pas sur ce qu'ils affirment, qui ne coûtent
rien, et qui désignent le fichier et la ligne. Le réparateur ne devine plus, il
lit un diagnostic.

Deuxième conséquence : la boucle visuelle repasse par la porte. Un correctif
CSS qui casserait la construction est attrapé avant d'être publié, ce que la
V1 ne pouvait pas faire puisqu'elle écrivait directement dans le livrable.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import typer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from graphe import noeuds
from graphe.couts import mesurer
from graphe.etat import EtatCrew
from graphe.graphe import _budget_atteint, _porte


# ── LES NŒUDS PROPRES AU FRONT ─────────────────────────────────────────

def squelette(etat: EtatCrew) -> dict:
    """Installe le squelette et ses dépendances. Zéro token, et long la
    première fois : `npm ci` télécharge Next et React."""
    from utils.squelette import installer, installer_dependances

    proj = noeuds._projet(etat)
    rapport = installer(proj)

    if rapport["neuf"]:
        typer.echo(f"📦 Squelette installé, {len(rapport['ecrits'])} fichier(s) → {rapport['dossier']}")
    else:
        typer.echo(f"📦 Squelette déjà en place, {len(rapport['ecrits'])} fichier(s) ajouté(s)")

    typer.echo("   → Dépendances…")
    installe = installer_dependances(proj.site_dir)
    typer.echo("   ✅ npm ci terminé" if installe else "   ✅ Dépendances déjà présentes")

    return {"journal": [f"squelette : {len(rapport['ecrits'])} fichier(s), deps {'installées' if installe else 'déjà là'}"]}


# LES AGENTS DU GRAPHE FRONT, tels que l'orchestrateur doit les connaître.
# Le designer de la V1 n'existe pas ici : la charte et le front le remplacent,
# et le référencement est assuré par le squelette lui-même (metadata,
# sitemap.ts, robots.ts). Annoncer au modèle des agents qu'on n'exécute pas,
# c'est lui faire écrire une instruction que personne ne lira.
AGENTS_FRONT = [
    {
        "nom": "copywriter", "priorite": 1,
        "role": "rédige tous les textes du site à partir des sections définies dans le brief",
        "quand": "toujours, pour un site vitrine",
    },
    {
        "nom": "front", "priorite": 2,
        "role": (
            "écrit le modèle de contenu, la couture de lecture, les composants "
            "et les pages Next à partir d'un squelette déjà validé. C'est lui "
            "qui porte la maquette : son instruction doit décrire la structure "
            "voulue, section par section"
        ),
        "quand": "toujours, pour un site vitrine",
    },
]

ORDRE_FRONT = ("copywriter", "front")


def orchestration_front(etat: EtatCrew) -> dict:
    """Le plan de travail, avec les agents que CE graphe sait exécuter."""
    return noeuds.orchestrer(etat, AGENTS_FRONT, ORDRE_FRONT)


def charte(etat: EtatCrew) -> dict:
    """La direction artistique traduite en valeurs de tokens."""
    from agents.front import CharteAgent

    with mesurer("charte") as facture:
        resultat = CharteAgent(noeuds._projet(etat)).run({"plan": etat.get("plan", {})})

    return {
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"charte : {len(resultat['tokens'])} token(s)"],
    }


def polices(etat: EtatCrew) -> dict:
    """Télécharge les polices nommées par la charte. Zéro token.

    SANS CE NŒUD, LE SITE PERD SA TYPOGRAPHIE EN SILENCE. L'enveloppe du
    squelette charge /polices/polices.css sans condition, et la charte nomme
    des familles : si personne ne produit le fichier, le navigateur reçoit un
    404 que seule la console montre, et retombe sur la police de secours. Le
    build est vert, la porte est verte, et le site n'a pas la typographie qu'on
    a payée.

    Les polices sont servies depuis le domaine du site, jamais depuis Google,
    qui recevrait sinon l'adresse IP de chaque visiteur.
    """
    from utils.polices import PolicesIndisponibles, heberger_polices_next

    proj = noeuds._projet(etat)
    try:
        rapport = heberger_polices_next(proj.site_dir)
    except PolicesIndisponibles as e:
        # On continue : tout le reste du site est bon, et la panne est
        # réseau, donc passagère. Mais on le dit fort, et ça reste dans le
        # journal du run, parce qu'une typographie muette ne se voit pas.
        typer.echo(f"\n⚠️  Polices non hébergées : {e}")
        typer.echo("   Le site utilisera les polices de secours. Relancer avec --reprendre.")
        return {"journal": ["polices : ÉCHEC, polices de secours"]}

    if rapport["familles"]:
        typer.echo(
            f"🔤 Polices hébergées : {', '.join(rapport['familles'])} "
            f"({rapport['telecharges']} fichier(s) téléchargé(s))"
        )
    else:
        typer.echo("🔤 Aucune police à héberger : la charte n'utilise que des familles système")

    return {"journal": [f"polices : {len(rapport['familles'])} famille(s)"]}


def front(etat: EtatCrew) -> dict:
    """Le modèle de contenu, la couture, les composants et les pages."""
    from agents.front import FrontAgent

    with mesurer("front") as facture:
        resultat = FrontAgent(noeuds._projet(etat)).run({"plan": etat.get("plan", {})})

    return {
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"front : {len(resultat['ecrits'])} fichier(s) écrit(s)"],
    }


def porte(etat: EtatCrew) -> dict:
    """LA PORTE DE BUILD. Déterministe, gratuite, et sans appel.

    Elle remplace le ValidatorAgent de la V1. Là où celui-ci inspectait du HTML
    à coups d'expressions régulières pour deviner si la page était complète, on
    demande ici à trois outils qui SAVENT.
    """
    from utils.verifier import resumer, verifier

    resultat = verifier(noeuds._projet(etat).site_dir)
    typer.echo("\n" + resumer(resultat))

    return {
        "resultat_porte": resultat,
        "journal": [
            "porte : les trois passent" if resultat["valide"]
            else f"porte : échec à l'étape {resultat['etape_echouee']} "
                 f"({len(resultat['problemes'])} problème(s))"
        ],
    }


def reparation_front(etat: EtatCrew) -> dict:
    """UNE tentative de correction, à partir du diagnostic de l'outil."""
    from agents.front import ReparateurAgent

    tentative = etat["corrections_faites"] + 1
    typer.echo(f"\n🔧 Réparation {tentative}/{etat['max_corrections']}…")

    with mesurer("reparation_front") as facture:
        resultat = ReparateurAgent(noeuds._projet(etat)).run(
            {"resultat_porte": etat["resultat_porte"]}
        )

    return {
        "corrections_faites": tentative,
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"réparation {tentative} : {len(resultat['ecrits'])} fichier(s)"],
    }


def publier(etat: EtatCrew) -> dict:
    """site/out/ devient output/, le dossier livré. Zéro token.

    C'est ce geste qui laisse `webcrew diff`, `webcrew restore` et l'audit de
    sécurité fonctionner sans modification : ils regardent output/, et output/
    contient toujours le site livrable, quel que soit le moteur qui l'a produit.
    """
    from utils.squelette import publier as publier_site

    fichiers = publier_site(noeuds._projet(etat))
    typer.echo(f"\n📤 Site publié, {fichiers} fichier(s) dans output/")
    return {"journal": [f"publication : {fichiers} fichier(s)"]}


def critique_visuelle_front(etat: EtatCrew) -> dict:
    """Photographier le site publié, le juger, écrire les correctifs.

    Le VisuelAgent de la V1 sert tel quel : il photographie output/index.html,
    qui existe toujours grâce à la publication. Seule la destination des
    correctifs change, et elle change pour le mieux : ils vont dans
    app/correctifs.css, qui repassera par la porte avant d'être publié.
    """
    from agents.front import appliquer_correctifs
    from agents.visuel import VisuelAgent
    from utils.capture import CaptureIndisponible

    proj = noeuds._projet(etat)
    passe = etat["passes_faites"] + 1

    with mesurer("critique_visuelle") as facture:
        try:
            critique = VisuelAgent(proj).run({})
        except CaptureIndisponible:
            return {
                "arret": "capture_indisponible",
                "passes_faites": passe,
                "cout_euros": facture["euros"],
                "depenses": facture["lignes"],
                "journal": ["critique visuelle : capture indisponible"],
            }

    appliques = appliquer_correctifs(proj.site_dir, critique.get("problemes", []))
    if appliques:
        typer.echo(f"   🔧 {appliques} correctif(s) écrits dans app/correctifs.css, zéro token")
        typer.echo("   → Repassage par la porte avant publication")
    else:
        typer.echo("   ℹ️  Aucun correctif applicable, passe suivante inutile")

    return {
        "critique": critique,
        "correctifs_appliques": appliques,
        "passes_faites": passe,
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"passe visuelle {passe} : {appliques} correctif(s)"],
    }


# ── LES ROUTES ─────────────────────────────────────────────────────────

def _apres_porte(etat: EtatCrew) -> str:
    """Publier, réparer, ou renoncer.

    ON NE PUBLIE JAMAIS UN SITE QUI NE PASSE PAS LA PORTE. C'est la règle qui
    justifie toute l'étape : un livrable qui ne compile pas n'est pas un
    livrable en retard, c'est un livrable qui n'existe pas.
    """
    resultat = etat.get("resultat_porte") or {}
    if resultat.get("valide"):
        return "publier"
    if etat.get("arret"):
        return "fin"
    if etat["corrections_faites"] >= etat["max_corrections"]:
        typer.echo(
            f"\n⚠️  {etat['max_corrections']} tentative(s) de réparation épuisée(s). "
            "Le site n'est pas publié : output/ garde la version précédente."
        )
        return "fin"
    if _budget_atteint(etat):
        return "plafond"
    return "reparation_front"


def _apres_publication(etat: EtatCrew) -> str:
    if etat.get("arret") or etat.get("passes_visuelles", 0) <= 0:
        return "fin"
    if etat["passes_faites"] >= etat["passes_visuelles"]:
        return "fin"
    if _budget_atteint(etat):
        return "plafond"
    return "critique_visuelle"


def _apres_critique(etat: EtatCrew) -> str:
    """Une passe qui a produit des correctifs repasse par la porte."""
    if etat.get("arret"):
        return "fin"
    if not etat.get("correctifs_appliques"):
        return "fin"
    return "porte"


def construire() -> StateGraph:
    g = StateGraph(EtatCrew)

    for nom, fonction in (
        ("preparer", noeuds.preparer),
        ("squelette", squelette),
        ("ingestion", noeuds.ingestion),
        ("orchestration", orchestration_front),
        ("direction", noeuds.direction),
        ("feu_vert", noeuds.feu_vert),
        ("copywriter", noeuds.copywriter),
        ("charte", charte),
        ("polices", polices),
        ("front", front),
        ("porte", porte),
        ("reparation_front", reparation_front),
        ("publier", publier),
        ("critique_visuelle", critique_visuelle_front),
        ("plafond", noeuds.plafond),
        ("fin", noeuds.fin),
    ):
        g.add_node(nom, fonction)

    # Le squelette s'installe AVANT le cadrage : il est gratuit, et les agents
    # de génération lisent la documentation locale de Next, qui n'existe
    # qu'une fois `npm ci` passé.
    g.add_edge(START, "preparer")
    g.add_edge("preparer", "squelette")
    g.add_edge("squelette", "ingestion")
    g.add_edge("ingestion", "orchestration")
    g.add_edge("orchestration", "direction")
    g.add_edge("direction", "feu_vert")

    for depart, suivant in (
        ("feu_vert", "copywriter"),
        ("copywriter", "charte"),
        ("polices", "front"),
    ):
        g.add_conditional_edges(
            depart, _porte(suivant), {suivant: suivant, "plafond": "plafond", "fin": "fin"}
        )

    # Les polices sont gratuites et dépendent de la charte : arête simple, même
    # si le budget est consommé. Un site sans sa typographie n'est pas un site
    # moins cher, c'est un site raté.
    g.add_edge("charte", "polices")

    # La porte est gratuite : elle se franchit même si le budget est consommé.
    # Savoir si le site compile ne coûte rien, et l'ignorer coûterait cher.
    g.add_edge("front", "porte")

    g.add_conditional_edges(
        "porte",
        _apres_porte,
        {
            "publier": "publier",
            "reparation_front": "reparation_front",
            "plafond": "plafond",
            "fin": "fin",
        },
    )
    g.add_edge("reparation_front", "porte")

    g.add_conditional_edges(
        "publier",
        _apres_publication,
        {"critique_visuelle": "critique_visuelle", "plafond": "plafond", "fin": "fin"},
    )
    g.add_conditional_edges(
        "critique_visuelle", _apres_critique, {"porte": "porte", "fin": "fin"}
    )

    g.add_edge("plafond", "fin")
    g.add_edge("fin", END)
    return g


def chemin_reprise(projet: str) -> Path:
    from utils.project import Project

    proj = Project(projet)
    proj.temp_dir.mkdir(parents=True, exist_ok=True)
    return proj.temp_dir / "graphe_front.sqlite"


@contextmanager
def crew_front(projet: str) -> Iterator:
    """Le graphe front compilé, avec sa reprise sur disque.

    Base de reprise distincte de celle du graphe V1 : les deux ne partagent ni
    les mêmes nœuds ni le même état, et mélanger leurs points de reprise ne
    pourrait que produire des surprises.
    """
    with SqliteSaver.from_conn_string(str(chemin_reprise(projet))) as checkpointer:
        yield construire().compile(checkpointer=checkpointer)
