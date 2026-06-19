import typer
from dotenv import load_dotenv
from agents.orchestrator import OrchestratorAgent
from agents.copywriter import CopywriterAgent
from agents.designer import DesignerAgent

load_dotenv()
app = typer.Typer()

@app.command()
def generate(
    project: str = typer.Option("projet-exemple", help="Nom du projet")
):
    """Lance l'équipe d'agents."""
    typer.echo(f"\n🚀 Lancement de web-crew pour : {project}\n")

    # Agent 1 — Orchestrateur
    orchestrator = OrchestratorAgent()
    plan = orchestrator.run({"project": project})
    typer.echo(f"📋 {len(plan['taches'])} tâches planifiées\n")

    # Agent 2 — Copywriter
    copywriter = CopywriterAgent()
    textes = copywriter.run({"plan": plan})
    typer.echo(f"✍️  {len(textes)} sections rédigées\n")

    # Agent 3 — Designer
    designer = DesignerAgent()
    result = designer.run({"plan": plan, "textes": textes})
    typer.echo(f"🎨 Fichiers générés : {result['fichiers']}\n")

    typer.echo("✅ Pipeline complet — ouvre workspace/output/projet-exemple/index.html")

@app.command()
def list_agents():
    """Affiche les agents disponibles."""
    agents = ["orchestrateur", "copywriter", "designer", "seo"]
    typer.echo("Agents disponibles :")
    for agent in agents:
        typer.echo(f"  • {agent}")

@app.command()
def design_only():
    """Relance uniquement le designer (textes déjà générés)."""
    typer.echo("\n🎨 Relance du designer uniquement...\n")
    from agents.designer import DesignerAgent
    designer = DesignerAgent()
    result = designer.run({})
    typer.echo(f"✅ Fichiers : {result['fichiers']}")

if __name__ == "__main__":
    app()