import json
import typer
from pathlib import Path
from dotenv import load_dotenv
from agents.orchestrator import OrchestratorAgent
from agents.copywriter import CopywriterAgent
from agents.designer import DesignerAgent

load_dotenv()

def _get_project_id() -> str:
    """Lit project_id depuis le brief — source de vérité unique du nom de projet."""
    with open("workspace/input/brief.json", "r", encoding="utf-8") as f:
        brief = json.load(f)
    return brief["output"]["project_id"]

app = typer.Typer()

@app.command()
def generate():
    """Lance l'équipe d'agents."""
    project_id = _get_project_id()
    typer.echo(f"\n🚀 Lancement de web-crew pour : {project_id}\n")

    # Agent 1 — Orchestrateur
    orchestrator = OrchestratorAgent()
    plan = orchestrator.run({})
    typer.echo(f"📋 {len(plan['taches'])} tâches planifiées\n")

    # Agent 2 — Copywriter
    copywriter = CopywriterAgent()
    textes = copywriter.run({"plan": plan})
    typer.echo(f"✍️  {len(textes)} sections rédigées\n")

    # Agent 3 — Designer
    designer = DesignerAgent()
    result = designer.run({"plan": plan, "textes": textes})
    typer.echo(f"🎨 Fichiers générés : {result['fichiers']}\n")

    typer.echo(f"✅ Pipeline complet — ouvre workspace/output/{project_id}/index.html")

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

@app.command()
def validate():
    """Lance le validateur sur le site généré."""
    typer.echo("\n🔍 Validation du site...\n")
    from agents.validator import ValidatorAgent
    validator = ValidatorAgent()
    result = validator.run({})
    if result["valide"]:
        typer.echo("\n✅ Site validé !")
    else:
        typer.echo(f"\n⚠️  {len(result['problemes'])} point(s) à corriger")

@app.command()
def generate_safe(
    max_tentatives: int = typer.Option(2, help="Nombre max de corrections")
):
    """Génère le site avec boucle de validation/correction automatique."""
    from agents.orchestrator import OrchestratorAgent
    from agents.copywriter import CopywriterAgent
    from agents.designer import DesignerAgent
    from agents.validator import ValidatorAgent

    project_id = _get_project_id()
    typer.echo(f"\n🚀 Génération sécurisée pour : {project_id}\n")

    # 1. Orchestrateur + Copywriter (une seule fois)
    orchestrator = OrchestratorAgent()
    plan = orchestrator.run({})

    copywriter = CopywriterAgent()
    copywriter.run({"plan": plan})

    # 2. Designer (première génération)
    designer = DesignerAgent()
    designer.run({"plan": plan})

    # 3. Boucle validation / correction
    validator = ValidatorAgent()
    output_dir = Path("workspace/output") / project_id

    tentative = 0
    while tentative < max_tentatives:
        typer.echo(f"\n🔍 Validation (tentative {tentative + 1}/{max_tentatives})...")
        result = validator.run({})

        # Condition de sortie : tout est bon
        if result["valide"]:
            typer.echo("\n✅ Site validé, aucune correction nécessaire !")
            break

        # Sinon, on corrige
        typer.echo(f"\n🔧 Correction de {len(result['problemes'])} problème(s)...")
        css = (output_dir / "style.css").read_text(encoding="utf-8")
        html = (output_dir / "index.html").read_text(encoding="utf-8")

        nouvelles_regles = designer.fix(result["problemes"], css, html)
        if nouvelles_regles:
            # On AJOUTE les nouvelles règles à la fin (mode append)
            css_complet = css + "\n\n/* === Règles ajoutées par correction auto === */\n" + nouvelles_regles
            (output_dir / "style.css").write_text(css_complet, encoding="utf-8")
            typer.echo("   ✅ Nouvelles règles CSS ajoutées")

        tentative += 1
    else:
        # Le 'else' d'un while s'exécute si on sort SANS break
        typer.echo(f"\n⚠️  Limite de {max_tentatives} tentatives atteinte.")
        typer.echo("   Certains problèmes peuvent subsister — vérifie manuellement.")

    typer.echo(f"\n🎯 Pipeline terminé — ouvre workspace/output/{project_id}/")

if __name__ == "__main__":
    app()