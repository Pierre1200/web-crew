"""LA DOCUMENTATION LOCALE DE NEXT, extraite pour le prompt de génération.

POURQUOI CE FICHIER EXISTE. Next 16 a renommé `middleware.ts` en `proxy.ts`.
Un modèle entraîné sur la version d'avant écrit `middleware.ts` : le build
passe, TypeScript est content, ESLint aussi, et le fichier ne s'exécute jamais.
Aucune porte automatique n'attrape ça. Next le dit lui-même dans le fichier
AGENTS.md qu'il écrit à chaque `next dev` : « ce n'est pas le Next que vous
croyez connaître, lisez la doc locale avant d'écrire ».

Le modèle ne peut pas lire de fichiers : c'est donc le NŒUD qui va chercher les
faits dans `node_modules/next/dist/docs/` et les lui met sous les yeux. Zéro
jeton pour l'extraction, et les faits viennent de la version RÉELLEMENT
installée, pas d'une mémoire d'entraînement.

Le jour où Next renomme autre chose, ce module le dira tout seul.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Le frontmatter YAML en tête de chaque page de doc. On ne lit que deux clés,
# donc pas de dépendance à un analyseur YAML.
_TITRE = re.compile(r"^title:\s*(.+)$", re.MULTILINE)
_DESCRIPTION = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def racine_docs(site_dir: Path) -> Path | None:
    """Le dossier de documentation livré avec le paquet next installé."""
    docs = Path(site_dir) / "node_modules" / "next" / "dist" / "docs"
    return docs if docs.is_dir() else None


def version_next(site_dir: Path) -> str:
    """La version exacte installée, lue dans son package.json."""
    paquet = Path(site_dir) / "node_modules" / "next" / "package.json"
    try:
        return json.loads(paquet.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "inconnue"


def conventions(site_dir: Path) -> list[dict]:
    """Les conventions de nommage de fichiers, telles que la version installée
    les décrit.

    C'est LA table qui empêche le piège `middleware.ts`. Chaque entrée porte le
    nom du fichier et le résumé écrit par Next, qui signale lui-même ce qui est
    déprécié et par quoi c'est remplacé.
    """
    docs = racine_docs(site_dir)
    if not docs:
        return []

    dossier = docs / "01-app" / "03-api-reference" / "03-file-conventions"
    if not dossier.is_dir():
        return []

    entrees = []
    for page in sorted(dossier.glob("*.md")):
        if page.name == "index.md":
            continue
        texte = page.read_text(encoding="utf-8")[:1200]
        titre = _TITRE.search(texte)
        description = _DESCRIPTION.search(texte)
        entrees.append(
            {
                "fichier": titre.group(1).strip() if titre else page.stem,
                "resume": description.group(1).strip() if description else "",
            }
        )
    return entrees


def contraintes_export(site_dir: Path) -> list[str]:
    """Ce que `output: 'export'` interdit, lu dans le guide local.

    On prend la section « Unsupported Features » du guide de l'App Router et on
    en tire les puces, débarrassées des liens markdown. Le modèle reçoit donc la
    liste réelle de la version installée, et non celle dont il se souvient.
    """
    docs = racine_docs(site_dir)
    if not docs:
        return []

    guide = docs / "01-app" / "02-guides" / "static-exports.md"
    if not guide.is_file():
        return []

    texte = guide.read_text(encoding="utf-8")
    debut = texte.find("## Unsupported Features")
    if debut == -1:
        return []

    # La section s'arrête au titre suivant de même niveau.
    fin = texte.find("\n## ", debut + 1)
    section = texte[debut:fin if fin != -1 else len(texte)]

    # On ne garde que la première liste à puces : la seconde concerne le Pages
    # Router, que le squelette n'utilise pas.
    puces = []
    for ligne in section.splitlines():
        if ligne.startswith("- "):
            # « [Server Actions](/docs/...) » devient « Server Actions »
            puces.append(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", ligne[2:]).strip())
        elif puces and ligne.startswith("</"):
            break  # fin du bloc <AppOnly>
    return puces


def digest(site_dir: Path, maximum_conventions: int = 24) -> str:
    """Le bloc à injecter dans le prompt de génération.

    Compact volontairement : ce texte est payé à chaque appel. On y met les
    faits qu'un modèle ne peut pas deviner et qui cassent en silence, rien
    d'autre. Renvoie "" si la documentation locale est absente : le prompt
    fonctionne alors sans, en le sachant.
    """
    docs = racine_docs(site_dir)
    if not docs:
        return ""

    lignes = [
        f"DOCUMENTATION DE LA VERSION RÉELLEMENT INSTALLÉE (Next {version_next(site_dir)}).",
        "Ces faits viennent de node_modules/next/dist/docs/, pas d'une mémoire "
        "d'entraînement. En cas de désaccord avec ce que tu crois savoir, "
        "CE BLOC A RAISON.",
    ]

    liste = conventions(site_dir)[:maximum_conventions]
    if liste:
        lignes.append("\nNoms de fichiers réservés par cette version :")
        for entree in liste:
            resume = f", {entree['resume']}" if entree["resume"] else ""
            lignes.append(f"  • {entree['fichier']}{resume}")

    interdits = contraintes_export(site_dir)
    if interdits:
        lignes.append(
            "\nCe que `output: 'export'` INTERDIT dans cette version. Utiliser "
            "l'un de ces éléments fait échouer la construction, ou pire, produit "
            "un site qui se construit et ne fonctionne pas :"
        )
        for interdit in interdits:
            lignes.append(f"  • {interdit}")

    return "\n".join(lignes)
