"""
Pages multiples — collections de contenus rédigés par le client.

Zéro token : tout ce fichier est de la mécanique pure. C'est le pilier de
l'architecture multi-pages — le modèle produit UN gabarit par collection, et
Python le remplit pour chaque contenu. Cinquante articles coûtent donc un appel
IA, pas cinquante, et sont visuellement identiques par construction.

FORMAT D'ÉCRITURE (fichiers .txt ou .md dans data/<collection>/)

    Titre: D'où vient le mot « bougnat » ?
    Chapo: Derrière le nom, il y a un métier et une migration.
    Date: 2026-08-14
    Couverture: charbon-paris.jpg
    Statut: publie

    Le mot « bougnat » désigne à Paris les Auvergnats venus s'y installer.

    ## Du charbon au comptoir

    Les marchands livraient les immeubles, étage par étage.

    > Le comptoir et le charbon, dans la même boutique.

L'en-tête s'arrête à la première ligne vide. Tout le reste est le corps.

Le corps N'EST PAS DU MARKDOWN, volontairement : une ligne vide sépare deux
paragraphes, « ## » ouvre un sous-titre, « > » une citation. Deux raisons —
le client n'a aucune syntaxe à apprendre, et comme on n'insère JAMAIS de HTML
écrit par lui (tout est échappé avant insertion), l'injection est impossible
par construction plutôt que par vigilance.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from html import escape
from pathlib import Path

from utils.cleaners import slugifier as _slugifier

EXTENSIONS_CONTENU = {".txt", ".md"}

# Marqueurs remplis avec du HTML déjà construit : eux seuls échappent à
# l'échappement. Tout le reste est du texte du client, échappé sans exception.
MARQUEURS_HTML = {"corps", "items", "couverture"}

_MOIS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre")

# Vitesse de lecture couramment retenue pour un adulte en français.
_MOTS_PAR_MINUTE = 200


# ── OUTILS DE TEXTE ────────────────────────────────────────────────────

def slugifier(texte: str) -> str:
    """Identifiant d'URL, avec un repli lisible si le texte ne donne rien.

    La normalisation elle-même vit dans utils/cleaners : ici on ne fait
    qu'ajouter la garantie « jamais vide », propre aux adresses de pages.
    """
    return _slugifier(texte) or "page"


def _normaliser_cle(cle: str) -> str:
    """« Chapô », « CHAPO », « chapo » désignent tous la même clé."""
    return slugifier(cle).replace("-", "_")


def date_en_francais(jour: date) -> str:
    """2026-08-14 → « 14 août 2026 »."""
    return f"{jour.day} {_MOIS_FR[jour.month - 1]} {jour.year}"


def _lire_date(valeur: str, defaut: date) -> date:
    """Accepte l'ISO (2026-08-14) et la forme française (14/08/2026)."""
    valeur = (valeur or "").strip()
    for motif in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(valeur, motif).date()
        except ValueError:
            continue
    return defaut


def temps_de_lecture(corps: str) -> int:
    """Minutes de lecture, jamais moins d'une (« 0 min » se lirait mal)."""
    mots = len([m for m in corps.split() if m])
    return max(1, round(mots / _MOTS_PAR_MINUTE))


# ── LECTURE D'UN CONTENU ───────────────────────────────────────────────

def decouper_corps(corps: str) -> list[dict]:
    """Découpe le corps en blocs affichables.

    Tolère les fins de ligne Windows : un texte collé depuis un traitement de
    texte utilise « \\r\\n », et sans cette tolérance il finirait en un seul
    énorme paragraphe.
    """
    blocs = []
    for morceau in re.split(r"\r?\n\s*\r?\n", corps):
        morceau = morceau.strip()
        if not morceau:
            continue
        if morceau.startswith("## "):
            blocs.append({"type": "sous_titre", "texte": morceau[3:].strip()})
        elif morceau.startswith("> "):
            blocs.append({"type": "citation", "texte": morceau[2:].strip()})
        else:
            # Un paragraphe peut tenir sur plusieurs lignes sans qu'on veuille
            # le couper : seule la ligne VIDE sépare deux paragraphes.
            blocs.append({
                "type": "paragraphe",
                "texte": re.sub(r"\s*\r?\n\s*", " ", morceau),
            })
    return blocs


def lire_contenu(chemin: Path) -> dict:
    """Lit un fichier de contenu et retourne sa représentation structurée.

    Volontairement permissif : un fichier sans en-tête reste exploitable (le
    titre vient du nom de fichier, la date de sa date de modification). Mieux
    vaut une page correcte qu'un refus au premier oubli — le client n'est pas
    développeur.
    """
    brut = chemin.read_text(encoding="utf-8", errors="ignore")
    lignes = brut.splitlines()

    entete, debut_corps = {}, 0
    for i, ligne in enumerate(lignes):
        if not ligne.strip():                     # ligne vide = fin d'en-tête
            debut_corps = i + 1
            break
        paire = re.match(r"^([A-Za-zÀ-ÿ_ ]{2,20})\s*:\s*(.*)$", ligne)
        if not paire:                             # pas d'en-tête du tout
            debut_corps = 0
            entete = {}
            break
        entete[_normaliser_cle(paire.group(1))] = paire.group(2).strip()
    else:
        debut_corps = len(lignes)                 # fichier sans corps

    corps = "\n".join(lignes[debut_corps:]).strip()

    titre = entete.get("titre") or chemin.stem.replace("-", " ").replace("_", " ").strip()
    modifie = date.fromtimestamp(chemin.stat().st_mtime)
    jour = _lire_date(entete.get("date", ""), modifie)
    statut = slugifier(entete.get("statut", "publie")) or "publie"

    return {
        "slug": slugifier(entete.get("slug") or chemin.stem),
        "titre": titre,
        "chapo": entete.get("chapo", ""),
        "corps": corps,
        "blocs": decouper_corps(corps),
        "couverture": entete.get("couverture", ""),
        "date": jour.isoformat(),
        "date_fr": date_en_francais(jour),
        "statut": "brouillon" if statut.startswith("brouillon") else "publie",
        "temps_lecture": temps_de_lecture(corps),
        "fichier": chemin.name,
    }


def lire_collection(project, collection: dict) -> list[dict]:
    """Lit tous les contenus d'une collection, les plus récents d'abord.

    Les brouillons sont exclus : ils permettent au client de préparer une page
    et d'y revenir sans qu'elle soit publique entre-temps.
    """
    dossier = project.data_dir / collection.get("source", collection["id"])
    if not dossier.is_dir():
        return []

    contenus = [
        lire_contenu(f)
        for f in sorted(dossier.iterdir())
        if f.is_file() and f.suffix.lower() in EXTENSIONS_CONTENU
    ]
    publies = [c for c in contenus if c["statut"] == "publie"]
    publies.sort(key=lambda c: c["date"], reverse=True)
    return publies


def collections_declarees(config: dict) -> list[dict]:
    """Collections déclarées dans config["site"]["collections"]."""
    collections = (config.get("site", {}) or {}).get("collections") or []
    normalisees = []
    for collection in collections:
        if not isinstance(collection, dict) or not collection.get("id"):
            continue
        identifiant = slugifier(collection["id"])
        normalisees.append({
            "id": identifiant,
            "titre": collection.get("titre", identifiant.capitalize()),
            "chapeau": collection.get("chapeau", ""),
            "source": collection.get("source", identifiant),
            "url": slugifier(collection.get("url", identifiant)),
            "flux": bool(collection.get("flux", True)),
        })
    return normalisees


# ── REMPLISSAGE DES GABARITS ───────────────────────────────────────────

def remplir(gabarit: str, valeurs: dict) -> str:
    """Remplace les {{marqueurs}} d'un gabarit par leurs valeurs.

    Tout est échappé, SAUF les marqueurs listés dans MARQUEURS_HTML qui
    reçoivent du HTML déjà construit par nos soins. C'est là que se joue la
    sécurité : le texte du client ne peut jamais devenir du balisage.
    """
    def remplacer(trouve):
        cle = trouve.group(1).strip()
        valeur = valeurs.get(cle, "")
        if cle in MARQUEURS_HTML:
            return str(valeur)
        return escape(str(valeur), quote=True)

    return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", remplacer, gabarit)


def marqueurs_presents(gabarit: str) -> set[str]:
    """Marqueurs effectivement utilisés dans un gabarit."""
    return set(re.findall(r"\{\{\s*([a-z_]+)\s*\}\}", gabarit))


def rendre_corps(blocs: list[dict], gabarits: dict) -> str:
    """Assemble le corps d'un contenu à partir des gabarits de blocs."""
    morceaux = []
    for bloc in blocs:
        gabarit = gabarits.get(bloc["type"])
        if not gabarit:
            continue
        morceaux.append(remplir(gabarit, {"texte": bloc["texte"]}))
    return "\n".join(morceaux)


def rendre_couverture(contenu: dict, gabarit_image: str, racine: str) -> str:
    """Construit la balise image de couverture, ou rien si aucune n'est fournie."""
    if not contenu.get("couverture") or not gabarit_image:
        return ""
    return remplir(gabarit_image, {
        "src": f"{racine}assets/{contenu['couverture']}",
        "alt": contenu["titre"],
    })


def valeurs_contenu(contenu: dict, collection: dict, gabarits: dict,
                    racine: str) -> dict:
    """Valeurs disponibles dans le gabarit d'une page de contenu."""
    return {
        "titre": contenu["titre"],
        "chapo": contenu["chapo"],
        "date": contenu["date"],
        "date_fr": contenu["date_fr"],
        "temps_lecture": str(contenu["temps_lecture"]),
        "slug": contenu["slug"],
        "titre_collection": collection["titre"],
        # La page de liste vit dans le MÊME dossier que les contenus : un lien
        # direct, sans détour par la racine du site.
        "url_liste": "index.html",
        "url_accueil": f"{racine}index.html",
        "racine": racine,
        "corps": rendre_corps(contenu["blocs"], gabarits),
        "couverture": rendre_couverture(contenu, gabarits.get("image", ""), racine),
    }


def rendre_collection(collection: dict, contenus: list[dict],
                      gabarits: dict) -> list[tuple[str, str]]:
    """Produit tous les fichiers HTML d'une collection.

    Retourne une liste de (chemin relatif à output/, contenu HTML).
    Zéro appel IA : les gabarits ont été générés une fois, on les remplit.
    """
    fichiers = []
    racine = "../"          # les pages vivent dans un sous-dossier

    # 1. une page par contenu
    for contenu in contenus:
        page = remplir(
            gabarits["page"],
            valeurs_contenu(contenu, collection, gabarits, racine),
        )
        fichiers.append((f"{collection['url']}/{contenu['slug']}.html", page))

    # 2. la page de liste
    items = []
    for contenu in contenus:
        valeurs = valeurs_contenu(contenu, collection, gabarits, racine)
        valeurs["url"] = f"{contenu['slug']}.html"
        items.append(remplir(gabarits["item"], valeurs))

    liste = remplir(gabarits["liste"], {
        "titre_collection": collection["titre"],
        "chapeau": collection["chapeau"],
        "items": "\n".join(items),
        "nombre": str(len(contenus)),
        "racine": racine,
        "url_accueil": f"{racine}index.html",
    })
    fichiers.append((f"{collection['url']}/index.html", liste))

    return fichiers


# ── FLUX RSS (zéro token) ──────────────────────────────────────────────

def rendre_flux(collection: dict, contenus: list[dict], site_url: str = "") -> str:
    """Flux RSS de la collection — mécanique, aucun appel IA.

    Les URL absolues demandent un domaine. Sans lui, on émet des chemins
    relatifs : le flux reste valide et devient correct dès que `site.url` est
    renseigné dans config.json.
    """
    base = site_url.rstrip("/")
    lien_collection = f"{base}/{collection['url']}/" if base else f"{collection['url']}/"

    entrees = []
    for contenu in contenus:
        lien = (f"{base}/{collection['url']}/{contenu['slug']}.html" if base
                else f"{collection['url']}/{contenu['slug']}.html")
        entrees.append(
            "    <item>\n"
            f"      <title>{escape(contenu['titre'])}</title>\n"
            f"      <link>{escape(lien)}</link>\n"
            f"      <guid isPermaLink=\"false\">{escape(contenu['slug'])}</guid>\n"
            f"      <description>{escape(contenu['chapo'])}</description>\n"
            f"      <pubDate>{contenu['date']}</pubDate>\n"
            "    </item>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{escape(collection['titre'])}</title>\n"
        f"    <link>{escape(lien_collection)}</link>\n"
        f"    <description>{escape(collection['chapeau'])}</description>\n"
        f"    <language>fr</language>\n"
        + "\n".join(entrees) + "\n"
        "  </channel>\n"
        "</rss>\n"
    )
