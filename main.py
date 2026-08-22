import json

import typer
from dotenv import load_dotenv

# .env doit être chargé AVANT d'importer les agents : base_agent lit
# WEBCREW_MODEL au moment de l'import (attribut de classe). Avec load_dotenv()
# après les imports, la variable du .env était silencieusement ignorée.
load_dotenv()

from utils.project import Project
from utils import snapshot
from utils.tarifs import cout_euros, formater, formater_nombre
from agents.base_agent import BaseAgent
from agents.orchestrator import OrchestratorAgent
from agents.ingestion import IngestionAgent
from agents.direction import DirectionAgent
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
    """Affiche ce que la commande a consommé, par modèle, en tokens et en euros.

    Les tarifs et le taux de change vivent dans utils/tarifs.py : un seul
    endroit à mettre à jour. Anthropic facturant en dollars, les euros affichés
    sont une estimation. Le détail appel par appel reste dans logs/<agent>.log.
    """
    conso = BaseAgent.CONSO_RUN
    if not conso:
        return

    typer.echo("\n💰 Consommation du run :")
    total_in = total_out = 0
    total_euros = 0.0
    tout_tarife = True

    for modele, c in sorted(conso.items()):
        euros = cout_euros(modele, c["in"], c["out"])
        if euros is None:
            tout_tarife = False
        else:
            total_euros += euros
        typer.echo(
            f"   • {modele} : {c['appels']} appel(s), "
            f"{formater_nombre(c['in'])} in, {formater_nombre(c['out'])} out"
            f"  →  {formater(euros)}"
        )
        total_in += c["in"]
        total_out += c["out"]

    # Un total chiffré alors qu'un modèle n'est pas tarifé serait faux : on le
    # dit « partiel » plutôt que de laisser croire à un montant complet.
    montant = formater(total_euros) if tout_tarife or total_euros else "?"
    suffixe = "" if tout_tarife else "  (partiel)"
    typer.echo(
        f"   Total : {formater_nombre(total_in)} in, "
        f"{formater_nombre(total_out)} out  →  {montant}{suffixe}"
    )
    if not tout_tarife:
        typer.echo("   ⚠️  Un modèle n'est pas tarifé dans utils/tarifs.py")


def _preflight(proj: Project):
    """Avertit AVANT de dépenser, si output/ contient du travail manuel perdu.

    Le cas vécu : des formulaires branchés sur Formspree à la main dans
    output/, sans que formspree_id soit renseigné dans config.json.
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


def _cadrer(proj: Project) -> dict:
    """Orchestrateur puis direction artistique — le cadrage, avant l'exécution.

    Deux étapes bon marché (~0,20 $ à elles deux) qui déterminent tout ce que
    coûteront ensuite le copywriter et le designer. Les séparer de la
    génération permet aussi de les rejouer seules après une retouche du brief.
    """
    orchestrator = OrchestratorAgent(proj)
    plan = orchestrator.run({})
    typer.echo(
        f"📋 {len(plan['taches'])} agent(s) planifié(s) : "
        f"{[t['agent'] for t in plan['taches']]}\n"
    )

    DirectionAgent(proj).run({})
    typer.echo("")
    return plan


def _generer_collections(proj: Project, designer, forcer_gabarits: bool = False) -> int:
    """Génère les pages de toutes les collections déclarées.

    Le coût est indépendant du nombre de contenus : les gabarits sont produits
    une fois par collection, mis en cache dans temp/, puis remplis par Python.
    Corriger une faute de frappe dans un article et régénérer ne coûte donc
    RIEN — c'est ce qui rend un blog viable sur un site généré.
    """
    from utils.pages import (
        collections_declarees, lire_collection, rendre_collection, rendre_flux,
    )

    collections = collections_declarees(proj.load_config())
    if not collections:
        return 0

    site_url = (proj.load_config().get("site", {}) or {}).get("url", "")
    total_pages = 0

    for collection in collections:
        contenus = lire_collection(proj, collection)
        dossier_source = proj.data_dir / collection["source"]

        if not contenus:
            typer.echo(
                f"   ⚠️  Collection « {collection['titre']} » vide — "
                f"dépose des fichiers .txt dans {dossier_source}/"
            )
            continue

        typer.echo(
            f"\n📄 Collection « {collection['titre']} » : {len(contenus)} contenu(s)"
        )

        cache = proj.temp_dir / f"gabarits_{collection['id']}.json"
        if cache.exists() and not forcer_gabarits:
            gabarits = json.loads(cache.read_text(encoding="utf-8"))
            typer.echo("   → Gabarits réutilisés depuis le cache (zéro token)")
        else:
            gabarits = designer.generer_gabarits(collection, contenus)
            cache.write_text(
                json.dumps(gabarits, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        fichiers = rendre_collection(collection, contenus, gabarits)
        if collection["flux"]:
            fichiers.append(
                (f"{collection['url']}/feed.xml", rendre_flux(collection, contenus, site_url))
            )

        for chemin_relatif, contenu_html in fichiers:
            cible = proj.output_dir / chemin_relatif
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_text(contenu_html, encoding="utf-8")

        typer.echo(f"   ✅ {len(fichiers)} fichier(s) → {proj.output_dir}/{collection['url']}/")
        total_pages += len(contenus)

    # Le sitemap est produit par l'agent SEO, qui passe AVANT les collections :
    # on le rejoue pour que les nouvelles pages y figurent (zéro token).
    if total_pages and (proj.output_dir / "sitemap.xml").exists():
        from agents.seo import generer_sitemap
        typer.echo(f"   🗺  sitemap.xml mis à jour ({generer_sitemap(proj)} pages)")

    return total_pages


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

    plan = _cadrer(proj)
    instances = _run_pipeline(proj, plan)

    designer = instances.get("designer") or DesignerAgent(proj)
    _generer_collections(proj, designer)

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

    plan = _cadrer(proj)
    instances = _run_pipeline(proj, plan)

    # Le designer est nécessaire pour la méthode fix() — on le récupère depuis les instances
    designer = instances.get("designer") or DesignerAgent(proj)
    _generer_collections(proj, designer)
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
        typer.echo("🎯 Rafraîchissement du cadrage (plan + direction artistique)...\n")
        _cadrer(proj)
    else:
        typer.echo(
            "ℹ️  Plan et direction artistique existants réutilisés. Si tu viens "
            "de modifier brief.md ou config.json, relance avec --replan.\n"
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
def pages(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    regenerer_gabarits: bool = typer.Option(
        False, "--gabarits",
        help="Redessine les gabarits (sinon ils sont réutilisés depuis le cache)",
    ),
):
    """Génère les pages des collections (blog, réalisations…).

    Sans --gabarits, l'opération est **gratuite** : les gabarits déjà dessinés
    sont réutilisés et Python se contente de les remplir. C'est la commande à
    relancer après avoir écrit ou corrigé un texte dans data/.
    """
    proj = _load_project(project_name)
    typer.echo(f"\n📄 Pages de {proj.name}...")

    _sauvegarder(proj)
    total = _generer_collections(proj, DesignerAgent(proj), regenerer_gabarits)

    if total == 0:
        typer.echo(
            "\nℹ️  Aucune collection déclarée. Ajoute dans config.json :\n"
            '   "site": {"collections": [{"id": "blog", "titre": "Le blog", '
            '"source": "articles"}]}\n'
            "   puis dépose tes textes dans data/articles/."
        )
    else:
        typer.echo(f"\n✅ {total} page(s) de contenu générée(s)")
        _valider_en_fin_de_run(proj)
    _afficher_conso()


@app.command()
def direction(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    archetype: str = typer.Option(
        "", "--archetype",
        help="Force un archétype de mise en page au lieu de laisser l'agent choisir",
    ),
):
    """Arrête la direction artistique du projet (~0,15 $).

    L'itération la moins chère du pipeline : changer d'archétype puis relancer
    `design-only` coûte une fraction d'une génération complète. Sans argument,
    liste les archétypes disponibles en fin d'exécution.
    """
    from agents.direction import DirectionAgent, ARCHETYPES

    if archetype and archetype not in ARCHETYPES:
        typer.echo(f"❌ Archétype inconnu : {archetype!r}")
        typer.echo("   Archétypes disponibles :")
        for nom, desc in ARCHETYPES.items():
            typer.echo(f"     • {nom} — {desc}")
        raise typer.Exit(code=1)

    proj = _load_project(project_name)
    typer.echo(f"\n🎨 Direction artistique de {proj.name}...\n")

    resultat = DirectionAgent(proj).run({})

    if archetype and resultat.get("archetype") != archetype:
        # On impose le choix de Pierre sans repayer un appel : le reste de la
        # direction (palette, rythme, typographie) reste cohérent et utilisable.
        resultat["archetype"] = archetype
        DirectionAgent(proj).write_json("temp/direction.json", resultat)
        typer.echo(f"   ↪ Archétype forcé sur : {archetype}")

    typer.echo("\n   Appliquer cette direction : webcrew design-only -p "
               f"{proj.name}")
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
def securiser(
    project_name: str = typer.Option(..., "--project", "-p", help="Nom du projet"),
    durcir: bool = typer.Option(
        False, "--durcir",
        help="Applique les corrections : polices auto-hébergées, en-têtes, pièges à robots",
    ),
    injection: bool = typer.Option(
        False, "--injection",
        help="Analyse les documents de data/ à la recherche d'instructions cachées (1 appel)",
    ),
    sans_polices: bool = typer.Option(
        False, "--sans-polices",
        help="Ne rapatrie pas les polices Google (le durcissement a besoin du réseau)",
    ),
    observation: bool = typer.Option(
        False, "--observation",
        help="Pose la CSP en mode observation : elle signale sans rien bloquer",
    ),
):
    """Audite et durcit le site avant livraison — écrit output/SECURITE.md.

    Sans option, l'audit est **gratuit** : inventaire des services extérieurs
    contactés, constats de sécurité, recherche de secrets, et rapport livrable.

    `--durcir` corrige (zéro token, mais accède une fois au réseau pour
    rapatrier les polices). À lancer quand le rendu te convient, pas à chaque
    essai : le durcissement modifie le site généré.

    `--injection` ajoute le seul appel au modèle : la relecture des documents
    du client à la recherche de consignes destinées à détourner un automate.
    """
    from agents.securite import SecuriteAgent

    proj = _load_project(project_name)
    typer.echo(f"\n🔒 Sécurité de {proj.name}...\n")

    if durcir:
        _sauvegarder(proj)

    SecuriteAgent(proj).run({
        "durcir": durcir,
        "polices": not sans_polices,
        "injection": injection,
        "report_only": observation,
    })

    if durcir:
        typer.echo("\n   Comparer : webcrew diff · revenir en arrière : webcrew restore")
        typer.echo("   ⚠️  Vérifie la console du navigateur après mise en ligne : "
                   "une CSP trop stricte se voit là.")
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
