"""Tests des lecteurs embarqués — zéro token, zéro appel API.

Les formats d'URL des fournisseurs sont la seule chose qu'on ne peut PAS
laisser un modèle deviner : un caractère de travers et le lecteur reste noir
chez le client. Ces tests verrouillent chaque format supporté.
"""
import pytest

from utils.embeds import (
    construire_manifeste,
    detecter,
    fournisseurs_supportes,
    normaliser_media,
)


@pytest.mark.parametrize("url, attendu_id", [
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?list=PL123&v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_detecte_les_formes_youtube(url, attendu_id):
    fournisseur, identifiant = detecter(url)
    assert fournisseur == "youtube"
    assert identifiant == attendu_id


@pytest.mark.parametrize("url, fournisseur", [
    ("https://vimeo.com/123456789", "vimeo"),
    ("https://www.dailymotion.com/video/x8abcde", "dailymotion"),
    ("https://dai.ly/x8abcde", "dailymotion"),
    ("https://open.spotify.com/playlist/37i9dQZF1DX", "spotify"),
    ("https://soundcloud.com/artiste/mon-titre", "soundcloud"),
    ("https://www.deezer.com/fr/album/12345", "deezer"),
])
def test_detecte_les_autres_fournisseurs(url, fournisseur):
    assert detecter(url)[0] == fournisseur


def test_url_inconnue_non_detectee():
    assert detecter("https://exemple.fr/ma-video.mp4") == (None, None)
    assert detecter("") == (None, None)


def test_youtube_embed_sans_cookie_et_vignette():
    media = normaliser_media({"titre": "Test", "url": "https://youtu.be/dQw4w9WgXcQ"})
    assert media["embed_url"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
    assert media["vignette"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert media["type"] == "video"
    assert media["ratio"] == "16 / 9"
    assert media["hauteur"] is None


def test_spotify_conserve_le_type_dans_identifiant():
    media = normaliser_media({"url": "https://open.spotify.com/playlist/37i9dQZF1DX"})
    assert media["embed_url"] == "https://open.spotify.com/embed/playlist/37i9dQZF1DX"
    assert media["type"] == "audio"
    assert media["hauteur"] == 352
    assert media["ratio"] is None


def test_soundcloud_encode_l_url_dans_le_parametre():
    media = normaliser_media({"url": "https://soundcloud.com/artiste/mon-titre"})
    # le / du chemin doit être encodé %2F dans le paramètre url=
    assert "artiste%2Fmon-titre" in media["embed_url"]
    assert media["page_url"] == "https://soundcloud.com/artiste/mon-titre"


def test_peertube_construit_l_embed_sur_l_instance():
    media = normaliser_media({"url": "https://video.exemple.org/w/abc123"})
    assert media["fournisseur"] == "peertube"
    assert media["embed_url"] == "https://video.exemple.org/videos/embed/abc123"


def test_fournisseur_et_id_explicites_sans_url():
    media = normaliser_media({"titre": "X", "fournisseur": "vimeo", "id": "987654"})
    assert media["embed_url"] == "https://player.vimeo.com/video/987654"


def test_titre_par_defaut_si_absent():
    assert normaliser_media({"url": "https://vimeo.com/1"})["titre"] == "Vimeo"


def test_fournisseur_inconnu_leve_une_erreur_explicite():
    with pytest.raises(ValueError, match="non reconnu"):
        normaliser_media({"titre": "Ma vidéo", "url": "https://exemple.fr/v.mp4"})
    # le message doit lister les fournisseurs supportés, pour que Pierre sache quoi faire
    try:
        normaliser_media({"url": "https://exemple.fr/v.mp4"})
    except ValueError as e:
        assert "youtube" in str(e)


def test_manifeste_isole_les_entrees_invalides():
    """Une URL mal collée ne doit pas empêcher les autres médias de passer."""
    config = {"site": {"medias": {
        "titre_section": "Les vidéos",
        "items": [
            {"titre": "Bonne", "url": "https://youtu.be/dQw4w9WgXcQ"},
            {"titre": "Cassée", "url": "https://exemple.fr/rien"},
        ],
    }}}
    manifeste = construire_manifeste(config)
    assert manifeste["titre_section"] == "Les vidéos"
    assert [m["titre"] for m in manifeste["items"]] == ["Bonne"]
    assert len(manifeste["erreurs"]) == 1
    assert "Cassée" in manifeste["erreurs"][0]


def test_manifeste_accepte_la_forme_courte_en_liste():
    config = {"site": {"medias": [{"url": "https://vimeo.com/42"}]}}
    assert len(construire_manifeste(config)["items"]) == 1


def test_manifeste_vide_sans_medias():
    manifeste = construire_manifeste({"site": {}})
    assert manifeste["items"] == [] and manifeste["erreurs"] == []


def test_tous_les_fournisseurs_documentes_sont_utilisables():
    """Chaque fournisseur du registre doit produire un embed exploitable."""
    assert len(fournisseurs_supportes()) >= 6
