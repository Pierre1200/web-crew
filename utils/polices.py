"""
Auto-hébergement des polices Google — zéro token.

Le problème : un site qui charge ses polices depuis `fonts.googleapis.com`
fait transmettre à Google **l'adresse IP de chaque visiteur**, sans que celui-ci
l'ait choisi ni que le client en soit informé. En Europe, un jugement allemand
de 2022 a condamné un exploitant de site pour exactement cela, et a déclenché
une vague de mises en demeure. Le débat juridique n'est pas clos — mais la
parade est triviale et gagnante sur tous les tableaux.

Héberger les polices soi-même supprime d'un coup :
  - la transmission de données à un tiers non choisi,
  - une dépendance externe (si le CDN tombe, le site perd sa typographie),
  - deux connexions réseau au chargement (le site est plus rapide).

Ce module sépare volontairement l'ANALYSE (pure, testable hors ligne) du
TÉLÉCHARGEMENT (réseau) : tout ce qui décide est vérifiable par des tests.
"""
from __future__ import annotations
import re
import urllib.error
import urllib.request

# Google renvoie un CSS différent selon le navigateur annoncé. Sans un
# navigateur récent, il sert du .ttf au lieu du .woff2 (trois fois plus lourd).
_NAVIGATEUR_MODERNE = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# Sous-ensembles conservés par défaut. Google en sert une dizaine (cyrillique,
# grec, vietnamien…) dont un site français n'a aucun usage : les livrer
# alourdirait le dossier sans bénéfice.
SOUS_ENSEMBLES_PAR_DEFAUT = ("latin", "latin-ext")


class PolicesIndisponibles(RuntimeError):
    """Téléchargement impossible — message actionnable pour l'utilisateur."""


# ── ANALYSE (pure) ─────────────────────────────────────────────────────

def extraire_liens_google(html: str) -> list[str]:
    """URL des feuilles de style Google Fonts référencées dans une page."""
    liens = re.findall(
        r'<link[^>]+href="(https://fonts\.googleapis\.com/css2?\?[^"]+)"', html
    )
    # &amp; dans le HTML doit redevenir & pour former une URL valide
    return [lien.replace("&amp;", "&") for lien in liens]


def analyser_css_google(css: str,
                        sous_ensembles: tuple = SOUS_ENSEMBLES_PAR_DEFAUT) -> list[dict]:
    """Découpe le CSS de Google en blocs @font-face exploitables.

    Chaque bloc est précédé d'un commentaire donnant son sous-ensemble
    (`/* latin */`). On s'en sert pour ne garder que ce qui est utile.
    """
    blocs = []
    motif = re.compile(
        r"/\*\s*([a-z0-9-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})",
        re.IGNORECASE | re.DOTALL,
    )
    for trouve in motif.finditer(css):
        sous_ensemble, bloc = trouve.group(1).lower(), trouve.group(2)
        if sous_ensembles and sous_ensemble not in sous_ensembles:
            continue
        url = re.search(r"url\(\s*([^)\s]+)\s*\)", bloc)
        famille = re.search(r"font-family:\s*['\"]([^'\"]+)", bloc)
        graisse = re.search(r"font-weight:\s*([^;]+);", bloc)
        style = re.search(r"font-style:\s*([^;]+);", bloc)
        if not url:
            continue
        blocs.append({
            "sous_ensemble": sous_ensemble,
            "bloc": bloc,
            "url": url.group(1).strip("'\""),
            "famille": famille.group(1) if famille else "police",
            "graisse": (graisse.group(1).strip() if graisse else "400"),
            "style": (style.group(1).strip() if style else "normal"),
        })
    return blocs


def nom_fichier_police(bloc: dict, extension: str = ".woff2") -> str:
    """« Playfair Display », 700, italic, latin → playfair-display-700-italic-latin.woff2"""
    famille = re.sub(r"[^a-z0-9]+", "-", bloc["famille"].lower()).strip("-")
    style = "" if bloc["style"] == "normal" else f"-{bloc['style']}"
    return f"{famille}-{bloc['graisse']}{style}-{bloc['sous_ensemble']}{extension}"


def reecrire_bloc(bloc: dict, chemin_local: str) -> str:
    """Remplace l'URL distante par le chemin local, et ajoute font-display: swap.

    `swap` affiche immédiatement le texte dans une police de repli plutôt que
    de le laisser invisible le temps du chargement.
    """
    nouveau = re.sub(r"url\(\s*[^)]+\)", f"url('{chemin_local}')", bloc["bloc"])
    if "font-display" not in nouveau:
        nouveau = nouveau.replace("@font-face {", "@font-face {\n  font-display: swap;", 1)
    return nouveau


def retirer_liens_google(html: str) -> tuple[str, int]:
    """Retire les <link> vers Google Fonts, préconnexions comprises."""
    retires = 0

    def compter(_):
        nonlocal retires
        retires += 1
        return ""

    html = re.sub(
        r'[ \t]*<link[^>]+href="https://fonts\.(?:googleapis|gstatic)\.com[^"]*"[^>]*>\n?',
        compter, html,
    )
    return html, retires


# ── TÉLÉCHARGEMENT (réseau) ────────────────────────────────────────────

def _telecharger(url: str) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": _NAVIGATEUR_MODERNE})
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            return reponse.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PolicesIndisponibles(
            f"Téléchargement impossible ({url}) : {e}\n"
            "   Vérifie ta connexion — le durcissement des polices a besoin "
            "d'accéder une seule fois à Google pour rapatrier les fichiers."
        ) from e


def heberger_polices(project, sous_ensembles: tuple = SOUS_ENSEMBLES_PAR_DEFAUT) -> dict:
    """Rapatrie les polices Google et bascule le site sur des fichiers locaux.

    Retourne un compte rendu {polices, fichiers, pages_modifiees, familles}.
    Opération idempotente : relancée sur un site déjà auto-hébergé, elle ne
    trouve plus aucun lien Google et ne fait rien.
    """
    output = project.output_dir
    pages = sorted(output.rglob("*.html"))

    liens = []
    for page in pages:
        liens += extraire_liens_google(page.read_text(encoding="utf-8", errors="ignore"))
    liens = sorted(set(liens))

    if not liens:
        return {"polices": 0, "fichiers": [], "pages_modifiees": 0, "familles": []}

    dossier = output / "assets" / "fonts"
    dossier.mkdir(parents=True, exist_ok=True)

    blocs_locaux, fichiers, familles = [], [], set()
    for lien in liens:
        css_google = _telecharger(lien).decode("utf-8", errors="ignore")
        for bloc in analyser_css_google(css_google, sous_ensembles):
            nom = nom_fichier_police(bloc)
            cible = dossier / nom
            if not cible.exists():
                cible.write_bytes(_telecharger(bloc["url"]))
            fichiers.append(nom)
            familles.add(bloc["famille"])
            # Chemin relatif depuis style.css, qui vit à la racine de output/
            blocs_locaux.append(reecrire_bloc(bloc, f"assets/fonts/{nom}"))

    if not blocs_locaux:
        raise PolicesIndisponibles(
            "Aucune police exploitable trouvée dans la réponse de Google — "
            "le format de sa feuille de style a peut-être changé."
        )

    # 1. les @font-face locaux, en TÊTE de style.css (avant tout usage)
    css_path = output / "style.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    if "web-crew:polices" not in css:
        entete = (
            "/* === web-crew:polices — polices auto-hébergées ===\n"
            "   Rapatriées depuis Google Fonts : plus aucune donnée de visiteur\n"
            "   n'est transmise à un tiers, et le site ne dépend plus d'un CDN. */\n"
            + "\n".join(blocs_locaux)
            + "\n/* === fin polices auto-hébergées === */\n\n"
        )
        css_path.write_text(entete + css, encoding="utf-8")

    # 2. retirer les <link> vers Google de toutes les pages
    pages_modifiees = 0
    for page in pages:
        html = page.read_text(encoding="utf-8", errors="ignore")
        nouveau, retires = retirer_liens_google(html)
        if retires:
            page.write_text(nouveau, encoding="utf-8")
            pages_modifiees += 1

    return {
        "polices": len(blocs_locaux),
        "fichiers": sorted(set(fichiers)),
        "pages_modifiees": pages_modifiees,
        "familles": sorted(familles),
    }
