"""
Préparation des vraies images du client — zéro token, pur Python.

Le dossier data/ contient les photos réellement fournies (portraits, logos,
œuvres). Jusqu'ici elles étaient cataloguées par l'ingestion puis oubliées :
le designer avait pour consigne d'utiliser des images de remplissage
(picsum.photos) pour TOUT. Le site livré ne montrait donc jamais le client.

Ce module fait trois choses, sans le moindre appel IA :
1. copie les images de data/ vers output/assets/ sous un nom utilisable en URL
2. lit leurs dimensions réelles en décodant les en-têtes binaires
3. produit un manifeste que le designer utilise pour écrire de vraies balises
   <img> avec width et height corrects

Pourquoi les dimensions comptent : sans width/height, le navigateur ne connaît
la place à réserver qu'une fois l'image chargée, et la page « saute » sous les
yeux du visiteur. C'est le défaut le plus visible d'un site amateur.

Les en-têtes sont décodés à la main plutôt qu'avec une bibliothèque : c'est
une trentaine d'octets à lire par format, ça évite une dépendance de plus, et
tout échec de lecture dégrade proprement (pas de dimensions → le designer omet
simplement les attributs).
"""
from __future__ import annotations
import re
import shutil
import struct
from math import gcd
from pathlib import Path

from utils.cleaners import slugifier

EXTENSIONS_IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif"}

# Au-delà, l'image ralentit le chargement du site et mérite d'être allégée.
POIDS_LOURD_KO = 500


# ── LECTURE DES DIMENSIONS (décodage d'en-têtes binaires) ──────────────

def _dimensions_png(donnees: bytes) -> tuple[int, int] | None:
    # Signature 8 octets, puis le bloc IHDR : largeur et hauteur sont deux
    # entiers 32 bits gros-boutistes aux offsets 16 et 20.
    if not donnees.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    largeur, hauteur = struct.unpack(">II", donnees[16:24])
    return largeur, hauteur


def _dimensions_gif(donnees: bytes) -> tuple[int, int] | None:
    # "GIF87a"/"GIF89a" puis deux entiers 16 bits petits-boutistes.
    if not donnees[:6] in (b"GIF87a", b"GIF89a"):
        return None
    largeur, hauteur = struct.unpack("<HH", donnees[6:10])
    return largeur, hauteur


def _dimensions_jpeg(donnees: bytes) -> tuple[int, int] | None:
    """Un JPEG est une suite de segments ; il faut les parcourir jusqu'au SOF.

    Chaque segment commence par 0xFF suivi d'un identifiant, puis de sa
    longueur. On saute de segment en segment jusqu'à tomber sur un « Start Of
    Frame » (0xC0 à 0xCF, sauf quelques identifiants réservés), le seul qui
    contienne les dimensions. Analogie C : on avance un pointeur de la taille
    annoncée par chaque en-tête, jusqu'au bloc recherché.
    """
    if not donnees.startswith(b"\xff\xd8"):
        return None

    i, n = 2, len(donnees)
    while i + 9 < n:
        if donnees[i] != 0xFF:
            i += 1
            continue
        marqueur = donnees[i + 1]
        # 0xD0-0xD9 (redémarrage, début/fin) et 0xFF de bourrage : pas de longueur
        if marqueur in (0xD8, 0xD9) or 0xD0 <= marqueur <= 0xD7 or marqueur == 0xFF:
            i += 2
            continue
        longueur = struct.unpack(">H", donnees[i + 2:i + 4])[0]
        # Start Of Frame : les identifiants C4 (Huffman), C8 et CC n'en sont pas
        if 0xC0 <= marqueur <= 0xCF and marqueur not in (0xC4, 0xC8, 0xCC):
            hauteur, largeur = struct.unpack(">HH", donnees[i + 5:i + 9])
            return largeur, hauteur
        i += 2 + longueur
    return None


def _dimensions_webp(donnees: bytes) -> tuple[int, int] | None:
    """WebP existe en trois variantes, chacune avec son propre en-tête."""
    if donnees[:4] != b"RIFF" or donnees[8:12] != b"WEBP":
        return None
    variante = donnees[12:16]

    if variante == b"VP8X":  # étendu : dimensions sur 24 bits, moins 1
        largeur = int.from_bytes(donnees[24:27], "little") + 1
        hauteur = int.from_bytes(donnees[27:30], "little") + 1
        return largeur, hauteur

    if variante == b"VP8 ":  # avec perte
        if donnees[23:26] != b"\x9d\x01\x2a":  # code de synchronisation
            return None
        largeur = struct.unpack("<H", donnees[26:28])[0] & 0x3FFF
        hauteur = struct.unpack("<H", donnees[28:30])[0] & 0x3FFF
        return largeur, hauteur

    if variante == b"VP8L":  # sans perte
        if donnees[20] != 0x2F:
            return None
        bits = int.from_bytes(donnees[21:25], "little")
        largeur = (bits & 0x3FFF) + 1
        hauteur = ((bits >> 14) & 0x3FFF) + 1
        return largeur, hauteur

    return None


def _dimensions_svg(donnees: bytes) -> tuple[int, int] | None:
    """Un SVG est du texte : on lit width/height, sinon le viewBox."""
    try:
        texte = donnees[:4096].decode("utf-8", errors="ignore")
    except Exception:
        return None

    largeur = re.search(r'\bwidth\s*=\s*["\']([\d.]+)', texte)
    hauteur = re.search(r'\bheight\s*=\s*["\']([\d.]+)', texte)
    if largeur and hauteur:
        return round(float(largeur.group(1))), round(float(hauteur.group(1)))

    boite = re.search(
        r'viewBox\s*=\s*["\']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', texte
    )
    if boite:
        return round(float(boite.group(1))), round(float(boite.group(2)))
    return None


_LECTEURS = (
    _dimensions_png,
    _dimensions_gif,
    _dimensions_jpeg,
    _dimensions_webp,
    _dimensions_svg,
)


def dimensions_depuis_octets(donnees: bytes) -> tuple[int, int] | None:
    """Dimensions d'une image déjà en mémoire, ou None si le format est illisible.

    Les lecteurs vérifient chacun leur signature : on peut donc les essayer
    tous sans se fier à l'extension du fichier, qui ment parfois.

    Séparé de `dimensions()` pour servir aussi aux images extraites d'un
    document Word ou PDF, qui n'ont pas encore de fichier sur le disque.
    """
    donnees = donnees[:65536]
    for lecteur in _LECTEURS:
        try:
            taille = lecteur(donnees)
        except (struct.error, IndexError, ValueError):
            continue
        if taille and taille[0] > 0 and taille[1] > 0:
            return taille
    return None


def dimensions(chemin: Path) -> tuple[int, int] | None:
    """Dimensions réelles d'un fichier image, ou None si illisible."""
    try:
        return dimensions_depuis_octets(chemin.read_bytes())
    except OSError:
        return None


# ── PRÉPARATION DES FICHIERS ───────────────────────────────────────────

def nom_web(nom: str) -> str:
    """Transforme un nom de fichier en nom utilisable dans une URL.

    « 1.2 La Charte Graphique 2025.PNG » → « 1-2-la-charte-graphique-2025.png »
    Les accents sont décomposés puis les signes diacritiques retirés, ce qui
    évite les URL encodées illisibles et les surprises selon le serveur.
    """
    chemin = Path(nom)
    # La normalisation vit dans utils/cleaners : un seul endroit à corriger le
    # jour où un caractère exotique passe entre les mailles.
    return f"{slugifier(chemin.stem) or 'image'}{chemin.suffix.lower()}"


def _ratio_lisible(largeur: int, hauteur: int) -> str:
    """« 1200x1600 » → « 3 / 4 » : le ratio réduit, utilisable en aspect-ratio."""
    diviseur = gcd(largeur, hauteur) or 1
    return f"{largeur // diviseur} / {hauteur // diviseur}"


def _orientation(largeur: int, hauteur: int) -> str:
    if largeur > hauteur * 1.05:
        return "paysage"
    if hauteur > largeur * 1.05:
        return "portrait"
    return "carré"


def _decrire(chemin: Path, chemin_web: str, source: str) -> dict:
    """Construit l'entrée de manifeste d'une image déjà en place."""
    entree = {
        "fichier": chemin.name,
        "chemin_web": chemin_web,
        "source": source,
        "poids_ko": round(chemin.stat().st_size / 1024, 1),
        "largeur": None,
        "hauteur": None,
        "ratio": None,
        "orientation": None,
    }
    taille = dimensions(chemin)
    if taille:
        largeur, hauteur = taille
        entree.update({
            "largeur": largeur,
            "hauteur": hauteur,
            "ratio": _ratio_lisible(largeur, hauteur),
            "orientation": _orientation(largeur, hauteur),
        })
    return entree


def preparer_assets(project, contexte_ingestion: dict | None = None) -> list[dict]:
    """Copie les images du client dans output/assets/ et décrit chacune.

    Deux sources :
    - data/ : ce que le client a fourni, copié sous un nom compatible URL
    - output/assets/ : ce qui y a déjà été déposé à la main (un logo fourni,
      par exemple) et qu'il ne faut surtout pas ignorer

    Si l'ingestion a suggéré une section pour une image, l'information est
    reprise ici pour aider le designer à la placer au bon endroit.

    Opération idempotente : on peut l'appeler à chaque génération.
    """
    dossier_assets = project.output_dir / "assets"
    dossier_assets.mkdir(parents=True, exist_ok=True)

    manifeste: list[dict] = []
    deja_vus: set[str] = set()

    # 1. les images fournies par le client, copiées depuis data/
    if project.data_dir.is_dir():
        for source in sorted(project.data_dir.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in EXTENSIONS_IMAGES:
                continue
            cible_nom = nom_web(source.name)
            # collision de noms après normalisation : on préfixe par le dossier
            if cible_nom in deja_vus:
                parent = nom_web(source.parent.name or "img").rsplit(".", 1)[0]
                cible_nom = f"{parent}-{cible_nom}"
            cible = dossier_assets / cible_nom
            shutil.copy2(source, cible)
            deja_vus.add(cible_nom)
            entree = _decrire(cible, f"assets/{cible_nom}", "data")
            entree["nom_origine"] = source.name
            manifeste.append(entree)

    # 2. les images déjà présentes dans output/assets/ (déposées à la main)
    for existant in sorted(dossier_assets.iterdir()):
        if (existant.is_file()
                and existant.suffix.lower() in EXTENSIONS_IMAGES
                and existant.name not in deja_vus):
            deja_vus.add(existant.name)
            manifeste.append(_decrire(existant, f"assets/{existant.name}", "assets"))

    # 3. enrichissement par les suggestions de l'agent Ingestion
    suggestions = {}
    for suggestion in (contexte_ingestion or {}).get("images_suggerees", []) or []:
        if suggestion.get("nom"):
            suggestions[nom_web(suggestion["nom"])] = suggestion

    for entree in manifeste:
        suggestion = suggestions.get(nom_web(entree.get("nom_origine", entree["fichier"])))
        if suggestion:
            entree["section_suggeree"] = suggestion.get("section_suggeree", "")
            entree["description"] = suggestion.get("raison", "")

    return manifeste


def images_lourdes(manifeste: list[dict]) -> list[dict]:
    """Images dont le poids ralentira le chargement du site livré."""
    return [i for i in manifeste if (i.get("poids_ko") or 0) > POIDS_LOURD_KO]
