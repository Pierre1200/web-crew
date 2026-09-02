"""LES NŒUDS DU GRAPHE.

RÈGLE DE L'ÉTAPE 2 : un nœud ENVELOPPE un agent de la V1, il ne le réécrit
jamais. Mêmes prompts, mêmes modèles, même code. Ce qui change est autour :
l'ordre, la reprise, les gardes, la mesure du coût. Si la sortie diffère de
celle de `webcrew generate-safe`, c'est un bug de migration.

Deux conséquences pratiques :

- les fonctions utilitaires du pipeline vivent encore dans `main.py` et sont
  importées telles quelles, à l'intérieur des nœuds. L'import est local pour
  éviter le cycle (main.py importe le graphe pour sa commande) ;
- chaque nœud fabrique sa propre instance d'agent. Les agents de la V1 sont
  sans mémoire d'un appel à l'autre : tout ce dont ils ont besoin est relu sur
  disque (temp/, output/). Ce n'était pas vrai de l'objet passé de main en
  main, ça l'est du disque, et c'est ce qui rend la reprise possible.
"""
from __future__ import annotations

import typer
from langgraph.types import interrupt

from agents.copywriter import CopywriterAgent
from agents.designer import DesignerAgent
from agents.direction import DirectionAgent
from agents.orchestrator import AGENTS_V1, OrchestratorAgent
from agents.seo import SeoAgent
from utils.project import Project

from graphe.couts import mesurer
from graphe.etat import EtatCrew

# L'ordre dans lequel le graphe traverse les agents d'exécution.
#
# La V1 les trie par `priorite`, mais le prompt de l'orchestrateur FIXE ces
# priorités : copywriter 1, designer 2, seo 3. Le plan ne décide donc que de
# l'INCLUSION, jamais de l'ordre. La topologie du graphe peut être figée sans
# rien perdre, et le nœud d'orchestration vérifie que cette hypothèse tient
# encore : le jour où l'orchestrateur changerait d'avis, on le saurait au lieu
# de produire silencieusement un ordre différent.
ORDRE_AGENTS = ("copywriter", "designer", "seo")


def _projet(etat: EtatCrew) -> Project:
    """Le projet, reconstruit depuis son nom.

    L'état d'un graphe est sérialisé à chaque étape pour le checkpointer : il ne
    peut contenir que des données, jamais un objet Python vivant. On garde donc
    le nom et on refabrique l'objet, qui n'est qu'un porteur de chemins.
    """
    return Project(etat["projet"])


# ── PRÉPARATION ────────────────────────────────────────────────────────

def preparer(etat: EtatCrew) -> dict:
    """Avertissements et sauvegarde, avant la moindre dépense. Zéro token."""
    from main import _preflight, _sauvegarder

    proj = _projet(etat)
    proj.setup_dirs()
    _preflight(proj)
    _sauvegarder(proj)
    return {"journal": ["préparation : dossiers prêts, version précédente sauvegardée"]}


# ── CADRAGE ────────────────────────────────────────────────────────────

def ingestion(etat: EtatCrew) -> dict:
    """Digère data/ en temp/context.json. Payant, mais mis en cache par l'agent."""
    from main import _run_ingestion

    with mesurer("ingestion") as facture:
        resultat = _run_ingestion(_projet(etat))

    vide = bool(resultat.get("vide"))
    return {
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": ["ingestion : aucune donnée client" if vide else "ingestion : contexte écrit"],
    }


def orchestration(etat: EtatCrew) -> dict:
    """Le plan de travail de la V1 : copywriter, designer, seo."""
    return orchestrer(etat, AGENTS_V1, ORDRE_AGENTS)


def orchestrer(etat: EtatCrew, agents: list[dict], ordre: tuple[str, ...]) -> dict:
    """L'orchestration, partagée par les deux graphes.

    `agents` est ce que le modèle a le droit de planifier, `ordre` ce que le
    graphe appelant sait exécuter. Les deux doivent se correspondre : c'est
    vérifié à chaque run plutôt que supposé.
    """
    with mesurer("orchestration") as facture:
        plan = OrchestratorAgent(_projet(etat)).run({"agents_disponibles": agents})

    planifies = [t["agent"] for t in plan["taches"]]

    # L'hypothèse de topologie figée, vérifiée à chaque run (voir ORDRE_AGENTS).
    attendus = [a for a in ordre if a in planifies]
    reels = [t["agent"] for t in sorted(plan["taches"], key=lambda t: t["priorite"])
             if t["agent"] in ordre]
    if attendus != reels:
        typer.echo(
            f"   ⚠️  L'orchestrateur demande l'ordre {reels}, le graphe applique "
            f"{attendus}. Vérifier avant de comparer à la V1."
        )

    inconnus = [a for a in planifies if a not in ordre]
    if inconnus:
        typer.echo(f"   ⚠️  Agent(s) hors du graphe, ignoré(s) : {inconnus}")

    return {
        "plan": plan,
        "agents_planifies": planifies,
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"orchestration : {planifies}"],
    }


def direction(etat: EtatCrew) -> dict:
    """La direction artistique, ou sa réutilisation si elle tient encore.

    La règle de réutilisation est celle de la V1, mot pour mot : les décisions
    valent tant qu'elles sont plus récentes que le brief ET la configuration.
    """
    from main import _direction_reutilisable

    proj = _projet(etat)

    if _direction_reutilisable(proj):
        typer.echo(
            "🎨 Direction artistique : décisions existantes plus récentes que le "
            "brief — réutilisées (0 token)\n"
        )
        return {
            "direction_reutilisee": True,
            "journal": ["direction : réutilisée, zéro token"],
        }

    with mesurer("direction") as facture:
        DirectionAgent(proj).run({})

    return {
        "direction_reutilisee": False,
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": ["direction : nouvelles décisions"],
    }


def feu_vert(etat: EtatCrew) -> dict:
    """L'ARRÊT AVANT DE DÉPENSER VRAIMENT.

    Tout ce qui précède coûte quelques centimes ; tout ce qui suit coûte des
    euros. C'est le seul moment où un humain peut dire « ce n'est pas ce que
    j'avais en tête » sans que ce soit déjà payé. En V1, douze appels partaient
    avant qu'on ne découvre le désaccord.

    `interrupt()` lève une exception que le graphe intercepte : l'état est
    enregistré par le checkpointer, l'exécution s'arrête, et un second appel
    avec `Command(resume=...)` reprend EXACTEMENT ici. Rien n'est rejoué.
    """
    if not etat.get("valider_a_la_main", True):
        return {"journal": ["feu vert : validation humaine désactivée"]}

    plan = etat.get("plan", {})
    reponse = interrupt(
        {
            "question": "Le cadrage est-il conforme au brief ?",
            "projet": etat["projet"],
            "agents": etat.get("agents_planifies", []),
            "style_guide": plan.get("style_guide", {}),
            "direction_reutilisee": etat.get("direction_reutilisee", False),
            "depense_a_ce_stade_euros": round(etat.get("cout_euros", 0.0), 4),
        }
    )

    # Tout ce qui n'est pas un accord franc est un refus : sur une décision qui
    # engage des euros, le silence ne vaut pas oui.
    accord = str(reponse).strip().lower() in {"oui", "o", "yes", "y", "true"}
    if not accord:
        return {"arret": "refus_humain", "journal": ["feu vert : refusé, rien de plus n'a été dépensé"]}

    return {"journal": ["feu vert : accordé"]}


# ── EXÉCUTION ──────────────────────────────────────────────────────────

def _noeud_agent(nom: str, classe):
    """Fabrique le nœud d'un agent d'exécution.

    Les trois se ressemblent au point que les écrire à la main serait trois
    occasions de diverger : même mesure, même saut si le plan ne les demande
    pas, même journal.
    """

    def noeud(etat: EtatCrew) -> dict:
        if nom not in etat.get("agents_planifies", []):
            return {"journal": [f"{nom} : non planifié, sauté"]}

        with mesurer(nom) as facture:
            classe(_projet(etat)).run({"plan": etat["plan"]})

        return {
            "cout_euros": facture["euros"],
            "depenses": facture["lignes"],
            "journal": [f"{nom} : fait"],
        }

    noeud.__name__ = nom
    return noeud


copywriter = _noeud_agent("copywriter", CopywriterAgent)
designer = _noeud_agent("designer", DesignerAgent)
seo = _noeud_agent("seo", SeoAgent)


def collections(etat: EtatCrew) -> dict:
    """Les pages de collection : un gabarit payé par collection, puis du Python.

    Le coût est indépendant du nombre de contenus. Cinquante articles coûtent
    un appel, pas cinquante.
    """
    from main import _generer_collections

    with mesurer("collections") as facture:
        pages = _generer_collections(
            _projet(etat), DesignerAgent(_projet(etat)),
            forcer_gabarits=etat.get("forcer_gabarits", False),
        )

    return {
        "pages_collections": pages,
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"collections : {pages} page(s)"],
    }


def mentions(etat: EtatCrew) -> dict:
    """Les mentions légales. Zéro token : ce sont des faits administratifs."""
    from main import _generer_mentions

    _generer_mentions(_projet(etat))
    return {"journal": ["mentions légales : écrites"]}


# ── LA PORTE DE CONTRÔLE ET SA BOUCLE ──────────────────────────────────

def controle(etat: EtatCrew) -> dict:
    """La validation structurelle. Gratuite, donc systématique.

    C'est la porte déterministe du graphe : elle ne demande son avis à aucun
    modèle. En V2 front, elle sera doublée par `npm run verifier`, qui est un
    compilateur et non un jugement.
    """
    from agents.validator import ValidatorAgent

    resultat = ValidatorAgent(_projet(etat)).run({})
    etiquette = "conforme" if resultat["valide"] else f"{len(resultat['erreurs'])} erreur(s)"
    return {"validation": resultat, "journal": [f"contrôle : {etiquette}"]}


def reparation(etat: EtatCrew) -> dict:
    """UNE tentative de correction. La boucle est le graphe, pas un `while`.

    Le corps reprend celui de `generate-safe` : même aiguillage sur le TYPE
    structuré du problème, jamais sur le texte du message, et mêmes méthodes
    d'agent. Ce qui change, c'est que chaque tentative est un pas du graphe,
    donc un point de reprise et une dépense mesurée à part.
    """
    from agents.validator import FIXABLE_TYPES
    from utils.cleaners import extract_css_classes

    proj = _projet(etat)
    erreurs = etat["validation"]["erreurs"]
    fixables = [p for p in erreurs if p["type"] in FIXABLE_TYPES]

    html_problems = [p for p in fixables
                     if p["type"] in ("html_tronque", "html_incomplet", "media_manquant")]
    js_problems = [p for p in fixables if p["type"] == "js_tronque"]
    classes_manquantes = [p["classe"] for p in fixables if p["type"] == "classe_absente"]

    faits = []
    with mesurer("reparation") as facture:
        designer_agent = DesignerAgent(proj)

        if html_problems:
            typer.echo("   → HTML tronqué détecté — régénération...")
            faits.append("html" if designer_agent.regenerate_html() else "html (échec)")

        if js_problems:
            typer.echo("   → JS tronqué détecté — régénération...")
            faits.append("js" if designer_agent.regenerate_js() else "js (échec)")

        if classes_manquantes:
            css_path = proj.output_dir / "style.css"
            html_path = proj.output_dir / "index.html"
            if css_path.exists() and html_path.exists():
                css = css_path.read_text(encoding="utf-8")
                nouvelles = designer_agent.fix(
                    classes_manquantes, css, html_path.read_text(encoding="utf-8")
                )
                if nouvelles:
                    css_path.write_text(
                        css + "\n\n/* === Règles ajoutées par correction auto === */\n" + nouvelles,
                        encoding="utf-8",
                    )
                    faits.append(f"{len(extract_css_classes(nouvelles))} règle(s) CSS")

    return {
        "corrections_faites": etat["corrections_faites"] + 1,
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"réparation {etat['corrections_faites'] + 1} : {', '.join(faits) or 'rien'}"],
    }


# ── LA BOUCLE VISUELLE ─────────────────────────────────────────────────

def critique_visuelle(etat: EtatCrew) -> dict:
    """UNE passe : photographier, juger, appliquer les correctifs CSS.

    Seule la critique coûte des jetons ; les correctifs sont appliqués
    mécaniquement, sans nouvel appel. Itérer est donc bon marché, et c'est
    pour ça que c'est une boucle et non une passe unique.
    """
    from agents.visuel import VisuelAgent
    from utils.capture import CaptureIndisponible

    proj = _projet(etat)
    passe = etat["passes_faites"] + 1

    with mesurer("critique_visuelle") as facture:
        try:
            critique = VisuelAgent(proj).run({})
        except CaptureIndisponible:
            # Playwright absent n'est pas un échec du run : tout le reste a été
            # produit. On sort de la boucle en le disant.
            return {
                "arret": "capture_indisponible",
                "passes_faites": passe,
                "cout_euros": facture["euros"],
                "depenses": facture["lignes"],
                "journal": ["critique visuelle : capture indisponible"],
            }

        appliques = DesignerAgent(proj).appliquer_correctifs_css(
            critique.get("problemes", [])
        )

    if appliques:
        typer.echo(f"   🔧 {appliques} correctif(s) CSS appliqué(s) — zéro token")
    else:
        typer.echo("   ℹ️  Aucun correctif CSS applicable — passe suivante inutile")

    return {
        "critique": critique,
        "correctifs_appliques": appliques,
        "passes_faites": passe,
        "cout_euros": facture["euros"],
        "depenses": facture["lignes"],
        "journal": [f"passe visuelle {passe} : {appliques} correctif(s)"],
    }


# ── SORTIES ────────────────────────────────────────────────────────────

def plafond(etat: EtatCrew) -> dict:
    """Le budget est atteint. On s'arrête net, sans rien engager de plus."""
    typer.echo(
        f"\n🛑 Plafond atteint : {etat['cout_euros']:.2f} € sur "
        f"{etat['plafond_euros']:.2f} € autorisés. Le graphe s'arrête ici."
    )
    typer.echo("   L'état est enregistré : relever le plafond et relancer reprend la suite.")
    return {"arret": "plafond"}


def fin(etat: EtatCrew) -> dict:
    """Le récapitulatif. Aucun effet, seulement de la lisibilité."""
    return {"journal": ["fin"]}
