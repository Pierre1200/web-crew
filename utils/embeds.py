"""
Lecteurs vidéo/audio embarqués — construction des URL d'intégration.

Zéro token : pur Python, aucun appel IA. Les formats d'URL des fournisseurs
sont exacts et stables ; les faire deviner à un modèle, c'est prendre le risque
d'un lecteur qui ne charge pas chez le client. Le designer reçoit donc des URL
déjà construites et n'a plus qu'à décider de la MISE EN PAGE de la galerie.

Utilisation côté config.json :

    "site": {
      "medias": {
        "titre_section": "Les vidéos",
        "items": [
          {"titre": "L'Auberge Aveyronnaise", "url": "https://youtu.be/XXXXXXXXXXX"},
          {"titre": "Playlist", "url": "https://open.spotify.com/playlist/XXXX"}
        ]
      }
    }

Le fournisseur est déduit de l'URL collée : rien d'autre à renseigner.
Pour ajouter un fournisseur, ajouter une entrée dans _FOURNISSEURS — le reste
du pipeline (designer, validateur) suit sans modification.
"""
from __future__ import annotations
import re
from urllib.parse import quote

# Registre des fournisseurs supportés.
#   type     : "video" ou "audio" — décide du gabarit (ratio vs hauteur fixe)
#   motifs   : expressions régulières essayées dans l'ordre sur l'URL collée ;
#              le groupe capturé devient l'identifiant du média
#   embed    : gabarit de l'URL d'intégration ({id} et {id_encode} disponibles)
#   page     : gabarit du lien vers la page publique (utile en repli sans JS)
#   vignette : gabarit de l'image d'aperçu, ou None si le fournisseur n'en expose pas
#   ratio    : proportions à respecter (vidéo)
#   hauteur  : hauteur fixe en pixels (lecteurs audio, qui n'ont pas de ratio)
_FOURNISSEURS = {
    "youtube": {
        "libelle": "YouTube",
        "type": "video",
        "motifs": [
            r"youtu\.be/([A-Za-z0-9_-]{6,})",
            r"youtube\.com/watch\?(?:.*&)?v=([A-Za-z0-9_-]{6,})",
            r"youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{6,})",
            r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})",
            r"youtube\.com/live/([A-Za-z0-9_-]{6,})",
        ],
        # -nocookie : pas de cookie publicitaire tant que le visiteur ne lit pas
        "embed": "https://www.youtube-nocookie.com/embed/{id}",
        "page": "https://www.youtube.com/watch?v={id}",
        "vignette": "https://i.ytimg.com/vi/{id}/hqdefault.jpg",
        "ratio": "16 / 9",
        "hauteur": None,
    },
    "vimeo": {
        "libelle": "Vimeo",
        "type": "video",
        "motifs": [
            r"player\.vimeo\.com/video/(\d+)",
            r"vimeo\.com/(?:channels/[^/]+/)?(\d+)",
        ],
        "embed": "https://player.vimeo.com/video/{id}",
        "page": "https://vimeo.com/{id}",
        "vignette": None,
        "ratio": "16 / 9",
        "hauteur": None,
    },
    "dailymotion": {
        "libelle": "Dailymotion",
        "type": "video",
        "motifs": [
            r"dailymotion\.com/embed/video/([A-Za-z0-9]+)",
            r"dailymotion\.com/video/([A-Za-z0-9]+)",
            r"dai\.ly/([A-Za-z0-9]+)",
        ],
        "embed": "https://www.dailymotion.com/embed/video/{id}",
        "page": "https://www.dailymotion.com/video/{id}",
        "vignette": None,
        "ratio": "16 / 9",
        "hauteur": None,
    },
    "spotify": {
        "libelle": "Spotify",
        "type": "audio",
        # L'identifiant capturé inclut le type : "playlist/37i9dQ...", "track/4cO..."
        "motifs": [
            r"open\.spotify\.com/(?:intl-[a-z]{2}/)?"
            r"((?:track|album|playlist|episode|show)/[A-Za-z0-9]+)",
        ],
        "embed": "https://open.spotify.com/embed/{id}",
        "page": "https://open.spotify.com/{id}",
        "vignette": None,
        "ratio": None,
        "hauteur": 352,
    },
    "soundcloud": {
        "libelle": "SoundCloud",
        "type": "audio",
        "motifs": [r"soundcloud\.com/([\w-]+/[\w-]+)"],
        # Le lecteur SoundCloud attend l'URL publique encodée en paramètre
        "embed": (
            "https://w.soundcloud.com/player/?url="
            "https%3A%2F%2Fsoundcloud.com%2F{id_encode}"
            "&color=%23404040&auto_play=false&show_user=true"
        ),
        "page": "https://soundcloud.com/{id}",
        "vignette": None,
        "ratio": None,
        "hauteur": 166,
    },
    "deezer": {
        "libelle": "Deezer",
        "type": "audio",
        "motifs": [
            r"deezer\.com/(?:[a-z]{2}/)?((?:track|album|playlist)/\d+)",
        ],
        "embed": "https://widget.deezer.com/widget/auto/{id}",
        "page": "https://www.deezer.com/{id}",
        "vignette": None,
        "ratio": None,
        "hauteur": 300,
    },
    "peertube": {
        "libelle": "PeerTube",
        "type": "video",
        # PeerTube est fédéré : l'instance fait partie de l'identifiant
        "motifs": [r"https?://([\w.-]+/(?:w|videos/watch)/[\w-]+)"],
        "embed": None,  # construit par _embed_peertube (dépend de l'instance)
        "page": "https://{id}",
        "vignette": None,
        "ratio": "16 / 9",
        "hauteur": None,
    },
}


def fournisseurs_supportes() -> list[str]:
    """Noms des fournisseurs reconnus — pour les messages d'erreur et la doc."""
    return sorted(_FOURNISSEURS)


def _embed_peertube(identifiant: str) -> str:
    """PeerTube : /w/<id> et /videos/watch/<id> deviennent /videos/embed/<id>."""
    hote, _, reste = identifiant.partition("/")
    video_id = reste.rsplit("/", 1)[-1]
    return f"https://{hote}/videos/embed/{video_id}"


def detecter(url: str) -> tuple[str | None, str | None]:
    """Déduit (fournisseur, identifiant) depuis une URL collée.

    Retourne (None, None) si aucun fournisseur connu ne correspond.
    """
    if not url:
        return None, None
    for nom, spec in _FOURNISSEURS.items():
        for motif in spec["motifs"]:
            trouve = re.search(motif, url, flags=re.IGNORECASE)
            if trouve:
                return nom, trouve.group(1)
    return None, None


def normaliser_media(entree: dict) -> dict:
    """Transforme une entrée de config.json en média prêt à intégrer.

    Accepte soit {"url": "<url collée>"}, soit {"fournisseur": ..., "id": ...}
    pour les cas où l'URL publique ne contient pas l'identifiant.

    Lève ValueError avec un message explicite si le média est inexploitable :
    mieux vaut un arrêt clair qu'un lecteur vide sur le site du client.
    """
    titre = (entree.get("titre") or "").strip()
    url = (entree.get("url") or "").strip()

    fournisseur = (entree.get("fournisseur") or "").strip().lower()
    identifiant = (entree.get("id") or "").strip()

    if not fournisseur or not identifiant:
        fournisseur, identifiant = detecter(url)

    if not fournisseur:
        raise ValueError(
            f"Média « {titre or url or '?'} » : fournisseur non reconnu. "
            f"Fournisseurs supportés : {', '.join(fournisseurs_supportes())}. "
            "Colle l'URL publique du média, ou renseigne 'fournisseur' et 'id'."
        )
    if fournisseur not in _FOURNISSEURS:
        raise ValueError(
            f"Média « {titre or url} » : fournisseur '{fournisseur}' inconnu. "
            f"Supportés : {', '.join(fournisseurs_supportes())}."
        )

    spec = _FOURNISSEURS[fournisseur]
    contexte = {"id": identifiant, "id_encode": quote(identifiant, safe="")}

    if fournisseur == "peertube":
        embed_url = _embed_peertube(identifiant)
    else:
        embed_url = spec["embed"].format(**contexte)

    return {
        "titre": titre or spec["libelle"],
        "description": (entree.get("description") or "").strip(),
        "fournisseur": fournisseur,
        "libelle": spec["libelle"],
        "type": spec["type"],
        "embed_url": embed_url,
        "page_url": spec["page"].format(**contexte),
        "vignette": spec["vignette"].format(**contexte) if spec["vignette"] else None,
        "ratio": spec["ratio"],
        "hauteur": spec["hauteur"],
    }


def construire_manifeste(config: dict) -> dict:
    """Lit config["site"]["medias"] et renvoie le manifeste normalisé.

    Retourne {"titre_section": str, "items": [...], "erreurs": [str]}.
    Un média invalide n'interrompt pas les autres : il est signalé dans
    "erreurs" et exclu du manifeste, pour qu'une URL mal collée ne bloque
    pas la génération de tout le site.
    """
    medias = (config.get("site", {}) or {}).get("medias") or {}

    # Tolère la forme courte "medias": [ ... ] sans titre de section
    if isinstance(medias, list):
        medias = {"items": medias}

    items, erreurs = [], []
    for entree in medias.get("items", []) or []:
        try:
            items.append(normaliser_media(entree))
        except ValueError as e:
            erreurs.append(str(e))

    return {
        "titre_section": medias.get("titre_section", ""),
        "items": items,
        "erreurs": erreurs,
    }
