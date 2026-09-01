"""LA PORTE DE BUILD, la validation déterministe de la V2.

En V1, la seule porte automatique était le jugement d'un modèle sur une page.
Ici on a un compilateur. C'est une différence de nature, pas de degré : ESLint
et TypeScript ne se trompent pas sur ce qu'ils affirment, ils ne coûtent rien,
et ils répondent en quelques secondes.

Trois étapes, dans cet ordre, et on s'arrête à la première qui échoue :

    lint      → les fautes de style et les règles React qui cassent au runtime
    typecheck → les erreurs de type, donc les contrats rompus
    build     → tout le reste, y compris ce que l'export statique refuse

L'ordre compte : `next build` est de loin le plus lent, inutile de le lancer
sur du code que `tsc` refuse déjà.

Chaque problème est un dict structuré, du même format que ceux de
ValidatorAgent, pour que la boucle de réparation aiguille sur le TYPE et jamais
sur le texte du message :

    {"type": "lint"|"type"|"build", "niveau": "erreur"|"warning",
     "fichier": str, "ligne": int|None, "message": str, "regle": str}
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Au-delà, c'est que quelque chose est bloqué (un serveur lancé, une invite
# interactive). Mieux vaut échouer avec un message qu'attendre indéfiniment.
DELAI_MAX_S = 900


class OutilsAbsents(RuntimeError):
    """npm n'est pas installé, ou le dossier n'est pas un projet Node."""


def _lancer(commande: list[str], dossier: Path) -> tuple[int, str]:
    """Lance une commande et renvoie (code de sortie, sortie complète).

    On fusionne stdout et stderr : ESLint écrit sur la sortie standard, tsc
    aussi, mais Next mélange les deux. Les séparer obligerait à savoir lequel
    parle avant de savoir ce qu'il dit.
    """
    try:
        resultat = subprocess.run(
            commande,
            cwd=dossier,
            capture_output=True,
            text=True,
            timeout=DELAI_MAX_S,
        )
    except FileNotFoundError as e:
        raise OutilsAbsents(
            f"Commande introuvable : {commande[0]}. Node et npm sont requis "
            "pour la porte de build."
        ) from e
    except subprocess.TimeoutExpired:
        return 1, f"⏱ Commande interrompue après {DELAI_MAX_S} s : {' '.join(commande)}"

    return resultat.returncode, _sans_couleurs((resultat.stdout or "") + (resultat.stderr or ""))


# Les couleurs du terminal, écrites dans la sortie par Next et par ESLint.
# Elles n'ont aucun sens dans un fichier de log, et encore moins dans un prompt
# de réparation où elles ne feraient que consommer des jetons.
_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _sans_couleurs(texte: str) -> str:
    return _ANSI.sub("", texte)


def _pb(type_: str, message: str, fichier: str = "", ligne: int | None = None,
        regle: str = "", niveau: str = "erreur") -> dict:
    return {
        "type": type_, "niveau": niveau, "message": message.strip(),
        "fichier": fichier, "ligne": ligne, "regle": regle,
    }


# ── ANALYSE DES SORTIES ────────────────────────────────────────────────

# ESLint, format « stylish » : un chemin absolu seul sur sa ligne, puis les
# problèmes indentés « ligne:colonne  niveau  message  règle ».
_ESLINT_FICHIER = re.compile(r"^(/.+\.(?:tsx?|jsx?|mjs|css))$")
_ESLINT_PROBLEME = re.compile(r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.*?)\s*$")

# tsc : « lib/fichier.ts(12,5): error TS2322: message »
_TSC = re.compile(r"^(.+?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.*)$")


def analyser_lint(sortie: str, racine: Path) -> list[dict]:
    """Les problèmes signalés par ESLint.

    Le message peut tenir sur plusieurs lignes (certaines règles React
    expliquent longuement) : on ne garde que la première, qui est le
    diagnostic. Le reste est de la pédagogie, utile à l'écran, bruyante dans
    un prompt de réparation.
    """
    problemes: list[dict] = []
    fichier = ""

    for ligne in sortie.splitlines():
        trouve_fichier = _ESLINT_FICHIER.match(ligne)
        if trouve_fichier:
            chemin = Path(trouve_fichier.group(1))
            try:
                fichier = str(chemin.relative_to(racine))
            except ValueError:
                fichier = str(chemin)
            continue

        trouve = _ESLINT_PROBLEME.match(ligne)
        if trouve and fichier:
            numero, _colonne, niveau, reste = trouve.groups()
            # La règle est le dernier mot, séparé du message par des espaces
            # multiples. Une règle contient toujours un tiret ou une barre.
            morceaux = re.split(r"\s{2,}", reste.strip())
            message = morceaux[0]
            regle = morceaux[-1] if len(morceaux) > 1 else ""
            problemes.append(
                _pb("lint", message, fichier, int(numero), regle,
                    niveau="erreur" if niveau == "error" else "warning")
            )

    return problemes


def analyser_types(sortie: str) -> list[dict]:
    """Les erreurs de TypeScript. Les chemins sont déjà relatifs au projet."""
    problemes = []
    for ligne in sortie.splitlines():
        trouve = _TSC.match(ligne.strip())
        if trouve:
            fichier, numero, _colonne, code, message = trouve.groups()
            problemes.append(_pb("type", message, fichier, int(numero), code))
    return problemes


def analyser_build(sortie: str) -> list[dict]:
    """L'échec de `next build`.

    Next n'a pas de format d'erreur stable : selon le cas il imprime une trace,
    un encadré, ou une ligne. On ne cherche donc pas à l'analyser finement.

    Le message est construit en deux parties : d'abord LA ligne de diagnostic,
    pour que le terminal en dise quelque chose d'utile ; ensuite la fin brute
    de la sortie, parce qu'un modèle lit un message d'erreur complet bien mieux
    qu'un résumé qui aurait perdu la moitié du contexte.
    """
    lignes = [l for l in sortie.splitlines() if l.strip()]
    extrait = "\n".join(lignes[-40:])

    # La première ligne « Error: … » est la cause ; celles d'après sont
    # l'emballage de Next (« Failed to collect page data for … »).
    diagnostic = next(
        (l.strip() for l in lignes if "Error:" in l),
        # Repli : la dernière ligne qui dit quelque chose, en ignorant les
        # accolades et crochets de fin de trace.
        next((l.strip() for l in reversed(lignes) if len(l.strip()) > 3), "next build a échoué"),
    )

    fichier = ""
    for ligne in lignes:
        trouve = re.search(r"\.?/((?:app|lib|composants)/[\w\-./\[\]]+\.\w+)", ligne)
        if trouve:
            fichier = trouve.group(1)
            break

    return [_pb("build", f"{diagnostic}\n\n{extrait}", fichier)]


# ── LA PORTE ───────────────────────────────────────────────────────────

ETAPES = (
    ("lint", ["npm", "run", "lint"]),
    ("typecheck", ["npm", "run", "typecheck"]),
    ("build", ["npm", "run", "build"]),
)


def verifier(dossier: Path, etapes: tuple[str, ...] = ("lint", "typecheck", "build")) -> dict:
    """Passe le site au compilateur. Zéro token.

    Renvoie :
        {"valide": bool, "etape_echouee": str|None,
         "problemes": [...], "sortie": str}

    On s'arrête à la première étape qui échoue : corriger une erreur de type
    change souvent le résultat du build, et présenter vingt erreurs dont dix
    sont des conséquences des dix autres est le meilleur moyen de faire
    corriger les mauvaises.
    """
    dossier = Path(dossier)
    if not (dossier / "package.json").exists():
        raise OutilsAbsents(f"{dossier} ne contient pas de package.json.")

    analyseurs = {
        "lint": lambda sortie: analyser_lint(sortie, dossier),
        "typecheck": analyser_types,
        "build": analyser_build,
    }

    for nom, commande in ETAPES:
        if nom not in etapes:
            continue

        code, sortie = _lancer(commande, dossier)
        if code == 0:
            continue

        problemes = analyseurs[nom](sortie)
        if not problemes:
            # Un code de sortie non nul sans problème analysable : on ne
            # prétend pas que tout va bien. Le texte brut vaut mieux que rien.
            problemes = [_pb(
                "build" if nom == "build" else nom,
                "\n".join(sortie.splitlines()[-40:]) or f"{nom} a échoué (code {code})",
            )]

        return {
            "valide": False,
            "etape_echouee": nom,
            "problemes": problemes,
            "sortie": sortie,
        }

    return {"valide": True, "etape_echouee": None, "problemes": [], "sortie": ""}


def resumer(resultat: dict, maximum: int = 8) -> str:
    """Le rapport lisible d'un passage à la porte, pour le terminal."""
    if resultat["valide"]:
        return "✅ lint, types et build : les trois passent."

    lignes = [f"❌ Échec à l'étape « {resultat['etape_echouee']} » :"]
    for probleme in resultat["problemes"][:maximum]:
        ou = probleme["fichier"] or "?"
        if probleme["ligne"]:
            ou += f":{probleme['ligne']}"
        regle = f"  [{probleme['regle']}]" if probleme["regle"] else ""
        # La première ligne d'un message est TOUJOURS le diagnostic, quelle
        # que soit l'étape : c'est analyser_build qui s'en assure.
        diagnostic = (probleme["message"].splitlines() or [""])[0]
        lignes.append(f"   {ou}  {diagnostic.strip()}{regle}")

    reste = len(resultat["problemes"]) - maximum
    if reste > 0:
        lignes.append(f"   … et {reste} autre(s)")
    return "\n".join(lignes)
