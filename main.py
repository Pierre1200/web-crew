import typer
from dotenv import load_dotenv

# .env doit être chargé AVANT d'importer les agents : base_agent lit
# WEBCREW_MODEL au moment de l'import (attribut de classe). Avec load_dotenv()
# après les imports, la variable du .env était silencieusement ignorée.
load_dotenv()

from utils.project import Project
from agents.base_agent import BaseAgent
from agents.orchestrator import OrchestratorAgent
from agents.ingestion import IngestionAgent
from agents.copywriter import CopywriterAgent
from agents.designer import DesignerAgent
from agents.seo import SeoAgent

# Registre des agents disponibles pour le dispatch.
# Ajouter un nouvel agent ici suffit pour que l'orchestrateur puisse le planifier.
AGENT_REGISTRY = {
    "copywriter": CopywriterAgent,
    "designer":   DesignerAgent,
    "seo":        SeoAgent,
}

app = typer.Typer()


def _load_project(project_name: str) -> Project:
    """Charge un projet en vérifiant qu'il existe AVANT de créer quoi que ce soit.

    Sans ce garde, une faute de frappe dans --project créait des dossiers
    fantômes (setup_dirs) puis crashait en FileNotFoundError sur le brief.
    Ici : message clair, liste des projets disponibles, code de sortie 1.
    """
    proj = Project(project_name)

    if not proj.root.is_dir():
        typer.echo(f"❌ Projet '{project_name}' introuvable dans projects/")
        projets_dir = proj.root.parent
        existants = sorted(
            d.name for d in projets_dir.iterdir()
            if d.is_dir() and (d / "config.json").exists()
        ) if projets_dir.is_dir() else []
        if existants:
            typer.echo(f"   Projets disponibles : {', '.join(existants)}")
        raise typer.Exit(code=1)

    manquants = proj.fichiers_requis_manquants()
    if manquants:
        typer.echo(
            f"❌ Projet '{project_name}' incomplet — "
            f"fichier(s) manquant(s) : {', '.join(manquants)}"
        )
        raise typer.Exit(code=1)

    proj.setup_dirs()
    return proj


def _afficher_conso():
    """Affiche le total de tokens consommés pendant la commande, par modèle.

    Volontairement en tokens et pas en euros : les tarifs changent, les
    compteurs non. Le détail appel par appel reste dans logs/<agent>.log.
    """
    conso = BaseAgent.CONSO_RUN
    if not conso:
        return
    typer.echo("\n💰 Consommation du run :")
    total_in = total_out = 0
    for modele, c in sorted(conso.items()):
        typer.echo(
            f"   • {modele} : {c['appels']} appel(s), "
            f"{c['in']:,} tokens in, {c['out']:,} out".replace(",", " ")
        )
        total_in += c["in"]
        total_out += c["out"]
    typer.echo(f"   Total : {total_in:,} in, {total_out:,} out".replace(",", " "))


def _run_ingestion(proj: Project) -> dict:
    """Digère les données brutes de data/ AVANT l'orchestration.

    Écrit temp/context.json, que l'orchestrateur relit pour ancrer son plan
    dans le contenu réel du client (thèmes disponibles, manques). Si data/ est
    vide, l'agent renvoie {"vide": True} et le pipeline continue normalement.
    """
    return IngestionAgent(proj).run({})


def _run_pipeline(proj: Project, plan: dict) -> dict:
    """Dispatch les agents dans l'ordre défini par le plan de l'orchestrateur.

    Retourne un dict {nom_agent: instance} pour que l'appelant puisse
    accéder aux instances après le pipeline (ex: designer.fix() dans generate-safe).
    """
    taches = sorted(plan["taches"], key=lambda t: t["priorite"])
    instances = {}

    for tache in taches:
        agent_name = tache["agent"]
        if agent_name not in AGENT_REGISTRY:
            typer.echo(f"⚠️  Agent '{agent_name}' inconnu du registre — ignoré")
            continue
        agent = AGENT_REGISTRY[agent_name](proj)
        instances[agent_name] = agent
        agent.run({"plan": plan})

    return instances


@app.command()
def generate(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet (ex: mon-client)")
):
    """Lance le pipeline piloté par l'orchestrateur."""
    proj = _load_project(project_name)
    typer.echo(f"\n🚀 Lancement de web-crew pour : {proj.name}\n")

    _run_ingestion(proj)

    orchestrator = OrchestratorAgent(proj)
    plan = orchestrator.run({})
    typer.echo(f"📋 {len(plan['taches'])} agent(s) planifié(s) : {[t['agent'] for t in plan['taches']]}\n")

    _run_pipeline(proj, plan)

    typer.echo(f"\n✅ Pipeline complet — ouvre {proj.output_dir}/index.html")
    _afficher_conso()


@app.command()
def generate_safe(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    max_tentatives: int = typer.Option(2, help="Nombre max de corrections automatiques")
):
    """Pipeline piloté par l'orchestrateur + boucle de validation/correction."""
    from agents.validator import ValidatorAgent, FIXABLE_TYPES

    proj = _load_project(project_name)
    typer.echo(f"\n🚀 Génération sécurisée pour : {proj.name}\n")

    _run_ingestion(proj)

    orchestrator = OrchestratorAgent(proj)
    plan = orchestrator.run({})
    typer.echo(f"📋 {len(plan['taches'])} agent(s) planifié(s) : {[t['agent'] for t in plan['taches']]}\n")

    instances = _run_pipeline(proj, plan)

    # Le designer est nécessaire pour la méthode fix() — on le récupère depuis les instances
    designer = instances.get("designer") or DesignerAgent(proj)
    validator = ValidatorAgent(proj)
    output_dir = proj.output_dir

    tentative = 0
    while tentative < max_tentatives:
        typer.echo(f"\n🔍 Validation (tentative {tentative + 1}/{max_tentatives})...")
        result = validator.run({})

        if result["valide"]:
            typer.echo("\n✅ Site validé, aucune erreur bloquante !")
            if result["warnings"]:
                typer.echo(f"   ({len(result['warnings'])} warning(s) à vérifier à l'œil — voir ci-dessus)")
            break

        # Aiguillage sur le TYPE structuré, plus jamais sur le texte du message.
        erreurs  = result["erreurs"]
        fixables = [p for p in erreurs if p["type"] in FIXABLE_TYPES]

        if not fixables:
            typer.echo(f"\n⚠️  {len(erreurs)} erreur(s) non corrigeable(s) automatiquement :")
            for p in erreurs:
                typer.echo(f"   ❌ {p['message']}")
            typer.echo("   → correction manuelle requise (ou relance design-only)")
            break

        typer.echo(f"\n🔧 Correction de {len(fixables)} problème(s)...")

        html_problems      = [p for p in fixables if p["type"] in ("html_tronque", "html_incomplet")]
        js_problems        = [p for p in fixables if p["type"] == "js_tronque"]
        classes_manquantes = [p["classe"] for p in fixables if p["type"] == "classe_absente"]

        if html_problems:
            typer.echo("   → HTML tronqué détecté — régénération...")
            if designer.regenerate_html():
                typer.echo("   ✅ index.html régénéré")
            else:
                typer.echo("   ❌ Régénération HTML échouée")

        if js_problems:
            typer.echo("   → JS tronqué détecté — régénération...")
            if designer.regenerate_js():
                typer.echo("   ✅ main.js régénéré")
            else:
                typer.echo("   ❌ Régénération JS échouée")

        if classes_manquantes:
            css_path  = output_dir / "style.css"
            html_path = output_dir / "index.html"
            if css_path.exists() and html_path.exists():
                css  = css_path.read_text(encoding="utf-8")
                html = html_path.read_text(encoding="utf-8")
                nouvelles_regles = designer.fix(classes_manquantes, css, html)
                if nouvelles_regles:
                    css_complet = css + "\n\n/* === Règles ajoutées par correction auto === */\n" + nouvelles_regles
                    css_path.write_text(css_complet, encoding="utf-8")
                    typer.echo("   ✅ Nouvelles règles CSS ajoutées")

        tentative += 1
    else:
        typer.echo(f"\n⚠️  Limite de {max_tentatives} tentatives atteinte.")
        typer.echo("   Certains problèmes peuvent subsister — vérifie manuellement.")

    typer.echo(f"\n🎯 Pipeline terminé — ouvre {proj.output_dir}/")
    _afficher_conso()


@app.command()
def design_only(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Relance uniquement le designer (textes déjà générés)."""
    proj = _load_project(project_name)
    typer.echo("\n🎨 Relance du designer uniquement...\n")
    designer = DesignerAgent(proj)
    result = designer.run({})
    typer.echo(f"✅ Fichiers : {result['fichiers']}")
    _afficher_conso()


@app.command()
def validate(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Lance le validateur sur le site généré (zéro token)."""
    from agents.validator import ValidatorAgent
    proj = _load_project(project_name)
    typer.echo(f"\n🔍 Validation de {proj.name}...\n")
    validator = ValidatorAgent(proj)
    result = validator.run({})
    if result["valide"]:
        typer.echo("\n✅ Site validé !")
    else:
        typer.echo(
            f"\n⚠️  {len(result['erreurs'])} erreur(s) bloquante(s), "
            f"{len(result['warnings'])} warning(s)"
        )


@app.command()
def seo_only(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Génère les métadonnées SEO et les injecte dans le HTML."""
    proj = _load_project(project_name)
    typer.echo(f"\n🔍 Génération SEO pour {proj.name}...\n")
    seo = SeoAgent(proj)
    meta = seo.run({})
    typer.echo(f"\n✅ Title : {meta.get('title', 'N/A')}")
    _afficher_conso()


@app.command()
def list_agents():
    """Affiche les agents disponibles dans le registre."""
    typer.echo("Agents dans le registre :")
    for name in AGENT_REGISTRY:
        typer.echo(f"  • {name}")

@app.command()
def ingest(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    force: bool = typer.Option(False, "--force", help="Ignore le cache et relance l'analyse IA"),
):
    """Lance l'agent Ingestion sur les données du projet."""
    proj = _load_project(project_name)
    IngestionAgent(proj).run({"force": force})
    _afficher_conso()

if __name__ == "__main__":
    app()
