import typer
from dotenv import load_dotenv

# .env doit être chargé AVANT d'importer les agents : base_agent lit
# WEBCREW_MODEL au moment de l'import (attribut de classe). Avec load_dotenv()
# après les imports, la variable du .env était silencieusement ignorée.
load_dotenv()

from utils.project import Project
from utils import snapshot
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


def _preflight(proj: Project):
    """Avertit AVANT de dépenser, si output/ contient du travail manuel perdu.

    Le cas vécu : les formulaires d'adap12 ont été branchés sur Formspree à la
    main dans output/, sans que formspree_id soit renseigné dans config.json.
    Régénérer écrase le branchement ET produit un formulaire factice — une
    régression payante. Ici on le dit avant, pas après.
    """
    index = proj.output_dir / "index.html"
    if not index.exists():
        return

    try:
        html = index.read_text(encoding="utf-8")
        config = proj.load_config()
    except (OSError, ValueError):
        return

    formspree_configure = bool(config.get("site", {}).get("formspree_id"))
    if "formspree.io" in html and not formspree_configure:
        typer.echo(
            "\n⚠️  Le site actuel branche des formulaires sur Formspree, mais "
            "'site.formspree_id' est vide dans config.json."
        )
        typer.echo(
            "   La régénération va écraser ce branchement et produire un "
            "formulaire qui n'envoie rien."
        )
        typer.echo(
            "   → Renseigne formspree_id dans config.json avant de continuer "
            "(la sauvegarde output_prev/ permettra de revenir en arrière).\n"
        )


def _sauvegarder(proj: Project):
    """Copie output/ dans output_prev/ avant d'écraser — filet anti-run raté."""
    if snapshot.sauvegarder_output(proj):
        typer.echo(f"💾 Version précédente sauvegardée → {snapshot.dossier_precedent(proj)}/")
        typer.echo("   (comparer : webcrew diff · revenir en arrière : webcrew restore)\n")


def _valider_en_fin_de_run(proj: Project):
    """Validation systématique après une génération — gratuite, donc toujours.

    Sans ça, on paie un run complet sans le moindre verdict sur ce qu'il a
    produit : il fallait penser à lancer `validate` séparément.
    """
    from agents.validator import ValidatorAgent

    typer.echo("\n🔍 Contrôle automatique du résultat (zéro token) :")
    resultat = ValidatorAgent(proj).run({})
    if not resultat["valide"]:
        typer.echo(
            f"\n   ⚠️  {len(resultat['erreurs'])} erreur(s) bloquante(s) — "
            "relance avec generate-safe pour tenter une correction automatique."
        )
    return resultat


def _critique_visuelle(proj: Project, designer, tours: int, corriger: bool = True) -> dict:
    """Boucle « photographie → juge → corrige » sur le site rendu.

    Seule la critique coûte des tokens (~0,15 $ la passe) : les correctifs CSS
    qu'elle propose sont appliqués mécaniquement, sans nouvel appel au modèle.
    Itérer est donc bon marché — c'est ce qui permet de viser un rendu quasi
    parfait sans repayer une génération complète à chaque retouche.
    """
    from agents.visuel import VisuelAgent
    from utils.capture import CaptureIndisponible

    agent = VisuelAgent(proj)
    critique = {}

    for tour in range(1, tours + 1):
        if tours > 1:
            typer.echo(f"\n── Passe visuelle {tour}/{tours} ──")
        try:
            critique = agent.run({})
        except CaptureIndisponible:
            return {}

        if not corriger:
            break

        appliques = designer.appliquer_correctifs_css(critique.get("problemes", []))
        if appliques:
            typer.echo(f"   🔧 {appliques} correctif(s) CSS appliqué(s) — zéro token")
        else:
            typer.echo("   ℹ️  Aucun correctif CSS applicable — passe suivante inutile")
            break

        if tour == tours:
            typer.echo(
                "   ℹ️  Correctifs appliqués mais non revérifiés — "
                "relance `visuel` pour juger le résultat"
            )

    return critique


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

    _preflight(proj)
    _sauvegarder(proj)
    _run_ingestion(proj)

    orchestrator = OrchestratorAgent(proj)
    plan = orchestrator.run({})
    typer.echo(f"📋 {len(plan['taches'])} agent(s) planifié(s) : {[t['agent'] for t in plan['taches']]}\n")

    _run_pipeline(proj, plan)

    typer.echo(f"\n✅ Pipeline complet — ouvre {proj.output_dir}/index.html")
    _valider_en_fin_de_run(proj)
    _afficher_conso()


@app.command()
def generate_safe(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    max_tentatives: int = typer.Option(2, help="Nombre max de corrections automatiques"),
    visuel_tours: int = typer.Option(
        0, "--visuel",
        help="Passes de critique visuelle après validation (≈0,15 $ la passe)",
    ),
):
    """Pipeline complet : génération, validation structurelle, puis critique visuelle.

    Avec --visuel N, le site est photographié et jugé par un directeur
    artistique après la validation technique, et les correctifs CSS proposés
    sont appliqués sans appel supplémentaire. C'est le chemin « front presque
    parfait dès le premier jet ».
    """
    from agents.validator import ValidatorAgent, FIXABLE_TYPES

    proj = _load_project(project_name)
    typer.echo(f"\n🚀 Génération sécurisée pour : {proj.name}\n")

    _preflight(proj)
    _sauvegarder(proj)
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

        # Un média manquant se répare en régénérant le HTML : regenerate_html
        # reçoit lui aussi le manifeste des lecteurs à intégrer.
        html_problems      = [p for p in fixables
                              if p["type"] in ("html_tronque", "html_incomplet", "media_manquant")]
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

    if visuel_tours > 0:
        _critique_visuelle(proj, designer, tours=visuel_tours)

    typer.echo(f"\n🎯 Pipeline terminé — ouvre {proj.output_dir}/")
    _afficher_conso()


@app.command()
def design_only(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    replan: bool = typer.Option(
        False, "--replan",
        help="Relance l'orchestrateur avant le designer — INDISPENSABLE après avoir modifié brief.md",
    ),
):
    """Relance uniquement le designer (textes déjà générés).

    ⚠️ Le plan porte le cahier des charges depuis qu'il pilote la maquette :
    après une modification de brief.md ou config.json, relancer le designer
    seul régénère l'ANCIENNE maquette — un run payé pour rien. --replan
    rafraîchit le plan pour quelques centimes avant de dessiner.
    """
    proj = _load_project(project_name)

    _preflight(proj)
    _sauvegarder(proj)

    if replan:
        typer.echo("🎯 Rafraîchissement du plan (orchestrateur seul)...\n")
        OrchestratorAgent(proj).run({})
    else:
        typer.echo(
            "ℹ️  Plan existant réutilisé. Si tu viens de modifier brief.md ou "
            "config.json, relance avec --replan.\n"
        )

    typer.echo("🎨 Relance du designer...\n")
    result = DesignerAgent(proj).run({})
    typer.echo(f"✅ Fichiers : {result['fichiers']}")
    _valider_en_fin_de_run(proj)
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
def diff(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Compare le site actuel à la version d'avant le dernier run (zéro token)."""
    proj = _load_project(project_name)
    resultat = snapshot.comparer(proj)

    if not resultat["disponible"]:
        typer.echo(
            f"ℹ️  Aucune sauvegarde pour {proj.name} — "
            "elle sera créée au prochain generate/design-only."
        )
        return

    typer.echo(f"\n📊 {proj.name} : version actuelle vs {snapshot.DOSSIER_PREV}/\n")

    for nom in resultat["ajoutes"]:
        typer.echo(f"   + {nom} (nouveau)")
    for nom in resultat["supprimes"]:
        typer.echo(f"   - {nom} (disparu)")
    for m in resultat["modifies"]:
        if m["lignes_avant"] is None:
            typer.echo(f"   ~ {m['fichier']} (contenu modifié)")
        else:
            delta = m["lignes_apres"] - m["lignes_avant"]
            signe = f"+{delta}" if delta > 0 else str(delta)
            typer.echo(
                f"   ~ {m['fichier']} : {m['lignes_avant']} → "
                f"{m['lignes_apres']} lignes ({signe})"
            )
    if resultat["identiques"]:
        typer.echo(f"   = {len(resultat['identiques'])} fichier(s) inchangé(s)")

    if not (resultat["ajoutes"] or resultat["supprimes"] or resultat["modifies"]):
        typer.echo("   Aucun changement — le run n'a rien modifié.")
    else:
        typer.echo("\n   Revenir à la version précédente : webcrew restore")


@app.command()
def restore(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Annule le dernier run en restaurant la version sauvegardée (zéro token)."""
    proj = _load_project(project_name)

    if not snapshot.dossier_precedent(proj).is_dir():
        typer.echo(f"❌ Aucune sauvegarde à restaurer pour {proj.name}")
        raise typer.Exit(code=1)

    if not typer.confirm(
        f"Remplacer output/ par la version sauvegardée de {proj.name} ?", default=False
    ):
        typer.echo("Annulé — rien n'a été modifié.")
        return

    snapshot.restaurer_output(proj)
    typer.echo(f"✅ Version précédente restaurée dans {proj.output_dir}/")


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
def critique(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet")
):
    """Contrôle le FOND des textes générés (inventions, sections creuses) — 1 appel."""
    from agents.critique import CritiqueAgent
    proj = _load_project(project_name)
    typer.echo(f"\n🧐 Critique de {proj.name}...\n")
    CritiqueAgent(proj).run({})
    _afficher_conso()


@app.command()
def visuel(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    tours: int = typer.Option(1, "--tours", help="Nombre de passes critique → correction"),
    corriger: bool = typer.Option(
        False, "--corriger", help="Applique les correctifs CSS proposés (zéro token)"
    ),
):
    """Photographie le site et le critique comme un directeur artistique.

    Le validateur prouve que le HTML est valide ; celui-ci dit s'il est BEAU
    et s'il respecte la maquette. Une passe ≈ 0,15 $. Avec --corriger, les
    règles CSS proposées sont appliquées sans aucun appel supplémentaire.
    """
    proj = _load_project(project_name)
    typer.echo(f"\n👁  Critique visuelle de {proj.name}...\n")

    if corriger:
        _sauvegarder(proj)

    _critique_visuelle(proj, DesignerAgent(proj), tours=tours, corriger=corriger)

    if corriger:
        typer.echo("\n   Comparer avec l'avant : webcrew diff · revenir : webcrew restore")

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
