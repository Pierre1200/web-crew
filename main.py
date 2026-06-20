import typer
from dotenv import load_dotenv
from utils.project import Project
from agents.orchestrator import OrchestratorAgent
from agents.copywriter import CopywriterAgent
from agents.designer import DesignerAgent

load_dotenv()

app = typer.Typer()


@app.command()
def generate(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet (ex: projet-exemple)")
):
    """Lance le pipeline complet : orchestrateur → copywriter → designer."""
    proj = Project(project_name)
    proj.setup_dirs()
    typer.echo(f"\n🚀 Lancement de web-crew pour : {proj.name}\n")

    orchestrator = OrchestratorAgent(proj)
    plan = orchestrator.run({})
    typer.echo(f"📋 {len(plan['taches'])} tâches planifiées\n")

    copywriter = CopywriterAgent(proj)
    textes = copywriter.run({"plan": plan})
    typer.echo(f"✍️  {len(textes)} sections rédigées\n")

    designer = DesignerAgent(proj)
    result = designer.run({"plan": plan, "textes": textes})
    typer.echo(f"🎨 Fichiers générés : {result['fichiers']}\n")

    typer.echo(f"✅ Pipeline complet — ouvre {proj.output_dir}/index.html")


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
def generate_safe(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    max_tentatives: int = typer.Option(2, help="Nombre max de corrections automatiques")
):
    """Génère le site avec boucle de validation/correction automatique."""
    from agents.validator import ValidatorAgent

    proj = Project(project_name)
    proj.setup_dirs()
    typer.echo(f"\n🚀 Génération sécurisée pour : {proj.name}\n")

    orchestrator = OrchestratorAgent(proj)
    plan = orchestrator.run({})

    copywriter = CopywriterAgent(proj)
    copywriter.run({"plan": plan})

    designer = DesignerAgent(proj)
    designer.run({"plan": plan})

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
        css = (output_dir / "style.css").read_text(encoding="utf-8")
        html = (output_dir / "index.html").read_text(encoding="utf-8")

        nouvelles_regles = designer.fix(result["problemes"], css, html)
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
def seo_only(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Génère les métadonnées SEO et les injecte dans le HTML."""
    from agents.seo import SeoAgent
    proj = Project(project_name)
    typer.echo(f"\n🔍 Génération SEO pour {proj.name}...\n")
    seo = SeoAgent(proj)
    meta = seo.run({})
    typer.echo(f"\n✅ Title : {meta.get('title', 'N/A')}")


@app.command()
def list_agents():
    """Affiche les agents disponibles."""
    agents = ["orchestrateur", "copywriter", "designer", "validator", "seo"]
    typer.echo("Agents disponibles :")
    for agent in agents:
        typer.echo(f"  • {agent}")


if __name__ == "__main__":
    app()
