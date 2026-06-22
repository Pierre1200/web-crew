import typer
from dotenv import load_dotenv
from utils.project import Project
from agents.orchestrator import OrchestratorAgent
from agents.copywriter import CopywriterAgent
from agents.designer import DesignerAgent
from agents.seo import SeoAgent

load_dotenv()

# Registre des agents disponibles pour le dispatch.
# Ajouter un nouvel agent ici suffit pour que l'orchestrateur puisse le planifier.
AGENT_REGISTRY = {
    "copywriter": CopywriterAgent,
    "designer":   DesignerAgent,
    "seo":        SeoAgent,
}

app = typer.Typer()


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
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet (ex: projet-exemple)")
):
    """Lance le pipeline piloté par l'orchestrateur."""
    proj = Project(project_name)
    proj.setup_dirs()
    typer.echo(f"\n🚀 Lancement de web-crew pour : {proj.name}\n")

    orchestrator = OrchestratorAgent(proj)
    plan = orchestrator.run({})
    typer.echo(f"📋 {len(plan['taches'])} agent(s) planifié(s) : {[t['agent'] for t in plan['taches']]}\n")

    _run_pipeline(proj, plan)

    typer.echo(f"\n✅ Pipeline complet — ouvre {proj.output_dir}/index.html")


@app.command()
def generate_safe(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    max_tentatives: int = typer.Option(2, help="Nombre max de corrections automatiques")
):
    """Pipeline piloté par l'orchestrateur + boucle de validation/correction."""
    from agents.validator import ValidatorAgent

    proj = Project(project_name)
    proj.setup_dirs()
    typer.echo(f"\n🚀 Génération sécurisée pour : {proj.name}\n")

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
            typer.echo("\n✅ Site validé, aucune correction nécessaire !")
            break

        typer.echo(f"\n🔧 Correction de {len(result['problemes'])} problème(s)...")

        html_problems = [p for p in result["problemes"] if "tronqué" in p or "incomplet" in p]
        css_problems  = [p for p in result["problemes"] if "absente du CSS" in p]

        if html_problems:
            typer.echo("   → HTML tronqué détecté — régénération...")
            ok = designer.regenerate_html()
            if ok:
                typer.echo("   ✅ index.html régénéré")
            else:
                typer.echo("   ❌ Régénération HTML échouée")

        if css_problems:
            css = (output_dir / "style.css").read_text(encoding="utf-8")
            html = (output_dir / "index.html").read_text(encoding="utf-8")
            nouvelles_regles = designer.fix(css_problems, css, html)
            if nouvelles_regles:
                css_complet = css + "\n\n/* === Règles ajoutées par correction auto === */\n" + nouvelles_regles
                (output_dir / "style.css").write_text(css_complet, encoding="utf-8")
                typer.echo("   ✅ Nouvelles règles CSS ajoutées")

        tentative += 1
    else:
        typer.echo(f"\n⚠️  Limite de {max_tentatives} tentatives atteinte.")
        typer.echo("   Certains problèmes peuvent subsister — vérifie manuellement.")

    typer.echo(f"\n🎯 Pipeline terminé — ouvre {proj.output_dir}/")


@app.command()
def design_only(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Relance uniquement le designer (textes déjà générés)."""
    proj = Project(project_name)
    typer.echo("\n🎨 Relance du designer uniquement...\n")
    designer = DesignerAgent(proj)
    result = designer.run({})
    typer.echo(f"✅ Fichiers : {result['fichiers']}")


@app.command()
def validate(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Lance le validateur sur le site généré (zéro token)."""
    from agents.validator import ValidatorAgent
    proj = Project(project_name)
    typer.echo(f"\n🔍 Validation de {proj.name}...\n")
    validator = ValidatorAgent(proj)
    result = validator.run({})
    if result["valide"]:
        typer.echo("\n✅ Site validé !")
    else:
        typer.echo(f"\n⚠️  {len(result['problemes'])} point(s) à corriger")


@app.command()
def seo_only(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Génère les métadonnées SEO et les injecte dans le HTML."""
    proj = Project(project_name)
    typer.echo(f"\n🔍 Génération SEO pour {proj.name}...\n")
    seo = SeoAgent(proj)
    meta = seo.run({})
    typer.echo(f"\n✅ Title : {meta.get('title', 'N/A')}")


@app.command()
def list_agents():
    """Affiche les agents disponibles dans le registre."""
    typer.echo("Agents dans le registre :")
    for name in AGENT_REGISTRY:
        typer.echo(f"  • {name}")


if __name__ == "__main__":
    app()
