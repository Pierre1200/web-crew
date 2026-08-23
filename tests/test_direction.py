"""Tests de la direction artistique — sans aucun appel API.

Les réponses du modèle sont simulées : on vérifie la VALIDATION de ce qu'il
renvoie et la façon dont la direction se propage au designer et à la critique
visuelle.
"""
import json
import os

import pytest

from agents.direction import ARCHETYPES, CLES_ATTENDUES, DirectionAgent
from main import _direction_reutilisable
from agents.designer import DesignerAgent, _PRINCIPES_GENERIQUES
from agents.visuel import VisuelAgent

DIRECTION_VALIDE = {
    "archetype": "editorial-asymetrique",
    "intention": "Donner l'impression d'entrer dans un atelier.",
    "palette": {"variables": {"--fond": "oklch(97% 0.01 80)"},
                "derivations": ["--surface: color-mix(in oklab, var(--fond) 92%, black);"],
                "usage_accent": "titres uniquement, jamais sur les fonds"},
    "typographie": {"echelle": {"h1": "clamp(2.5rem, 6vw, 4rem)"}, "mesure": "62ch"},
    "espacement": {"echelle": [8, 16, 24, 40, 64, 96, 160],
                   "rythme_sections": {"hero": "160px, très aéré"}},
    "surfaces": {"traitement": "papier légèrement texturé", "ombres": "aucune"},
    "mouvement": {"politique": "rien ne bouge sauf le titre",
                  "elements_animes": ["titre du hero"]},
    "signature": "La texture papier et l'absence totale d'ombre.",
    "pieges_a_eviter": ["Ne pas centrer le hero", "Pas de carte à ombre portée"],
}


def _config(proj):
    (proj.root / "config.json").write_text(
        json.dumps({"site": {"sections": ["Hero"]}}), encoding="utf-8"
    )
    (proj.root / "brief.md").write_text("Un brief de test.", encoding="utf-8")


def _simuler_reponse(monkeypatch, charge):
    """Fait répondre l'API sans l'appeler."""
    monkeypatch.setattr(
        DirectionAgent, "call_claude",
        lambda self, s, u, max_tokens=0, **kw: json.dumps(charge),
    )


def _ecrire_direction(proj, direction=None):
    (proj.temp_dir / "direction.json").write_text(
        json.dumps(direction or DIRECTION_VALIDE, ensure_ascii=False), encoding="utf-8"
    )


# ── Validation de ce que renvoie le modèle ─────────────────────────────

def test_direction_valide_est_ecrite(proj, monkeypatch):
    _config(proj)
    _simuler_reponse(monkeypatch, DIRECTION_VALIDE)

    resultat = DirectionAgent(proj).run({})
    assert resultat["archetype"] == "editorial-asymetrique"
    assert (proj.temp_dir / "direction.json").exists()


def test_direction_incomplete_est_refusee(proj, monkeypatch):
    """Une direction amputée casserait le designer plus loin : on arrête ici."""
    _config(proj)
    incomplete = {k: v for k, v in DIRECTION_VALIDE.items() if k != "espacement"}
    _simuler_reponse(monkeypatch, incomplete)

    with pytest.raises(ValueError, match="espacement"):
        DirectionAgent(proj).run({})


def test_archetype_hors_liste_passe_mais_est_signale(proj, monkeypatch):
    _config(proj)
    exotique = dict(DIRECTION_VALIDE, archetype="mon-archetype-invente")
    _simuler_reponse(monkeypatch, exotique)

    resultat = DirectionAgent(proj).run({})
    assert resultat["archetype"] == "mon-archetype-invente"  # non bloquant


def test_prompt_systeme_liste_les_archetypes(proj):
    _config(proj)
    prompt = DirectionAgent(proj)._prompt_systeme()
    for nom in ARCHETYPES:
        assert nom in prompt


def test_toutes_les_cles_attendues_sont_dans_l_exemple_du_prompt(proj):
    """Le gabarit JSON montré au modèle doit couvrir ce qu'on exige de lui."""
    _config(proj)
    prompt = DirectionAgent(proj)._prompt_utilisateur({})
    for cle in CLES_ATTENDUES:
        assert f'"{cle}"' in prompt


# ── Propagation vers le designer ───────────────────────────────────────

def test_sans_direction_le_designer_garde_ses_principes_generiques(proj):
    _config(proj)
    bloc, principes = DesignerAgent(proj)._bloc_direction()
    assert bloc == ""
    assert principes == _PRINCIPES_GENERIQUES


def test_avec_direction_les_principes_generiques_sont_remplaces(proj):
    """Des décisions chiffrées valent mieux que des conseils vagues."""
    _config(proj)
    _ecrire_direction(proj)
    bloc, principes = DesignerAgent(proj)._bloc_direction()

    assert principes == ""                      # plus de conseils génériques
    assert "DIRECTION ARTISTIQUE ARRÊTÉE" in bloc
    assert "editorial-asymetrique" in bloc
    assert "160px, très aéré" in bloc           # le rythme chiffré est transmis
    assert "Ne pas centrer le hero" in bloc     # les pièges du projet aussi


def test_direction_illisible_ne_casse_pas_le_designer(proj):
    _config(proj)
    (proj.temp_dir / "direction.json").write_text("{ json cassé", encoding="utf-8")
    bloc, principes = DesignerAgent(proj)._bloc_direction()
    assert bloc == "" and principes == _PRINCIPES_GENERIQUES


# ── Propagation vers la critique visuelle ──────────────────────────────

def test_la_critique_visuelle_juge_l_ecart_avec_la_direction(proj):
    _config(proj)
    _ecrire_direction(proj)
    contexte = VisuelAgent(proj)._prompt_contexte({"style_guide": {}})

    assert "DIRECTION ARTISTIQUE QUI AVAIT ÉTÉ ARRÊTÉE" in contexte
    assert "editorial-asymetrique" in contexte
    assert "au minimum « majeur »" in contexte


def test_la_critique_visuelle_fonctionne_sans_direction(proj):
    _config(proj)
    contexte = VisuelAgent(proj)._prompt_contexte({"style_guide": {}})
    assert "DIRECTION ARTISTIQUE QUI AVAIT ÉTÉ ARRÊTÉE" not in contexte


# ── Réutilisation du cadrage (zéro token) ──────────────────────────────
#
# Une direction artistique coûte ~0,30 € : la rejouer sans raison à chaque
# generate est de l'argent jeté. Mais la réutiliser après une retouche du
# brief ferait dessiner l'ancien site. La règle est celle de make : la cible
# est refaite si elle est plus vieille qu'une de ses sources.

def _ecrire_direction(proj, contenu=None, apres=None):
    """Écrit temp/direction.json, éventuellement daté après un autre fichier."""
    chemin = proj.temp_dir / "direction.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(DIRECTION_VALIDE if contenu is None else contenu, ensure_ascii=False),
        encoding="utf-8",
    )
    if apres is not None:
        repere = apres.stat().st_mtime
        os.utime(chemin, (repere + 10, repere + 10))
    return chemin


def _ecrire_cadrage(proj):
    proj.brief_path.write_text("# Brief", encoding="utf-8")
    proj.config_path.write_text('{"site": {}}', encoding="utf-8")


def test_direction_absente_est_a_calculer(proj):
    _ecrire_cadrage(proj)
    assert _direction_reutilisable(proj) is False


def test_direction_complete_et_recente_est_reutilisee(proj):
    _ecrire_cadrage(proj)
    _ecrire_direction(proj, apres=proj.config_path)
    assert _direction_reutilisable(proj) is True


def test_direction_plus_vieille_que_le_brief_est_rejouee(proj):
    """Le piège de design-only sans --replan : dessiner l'ancien cahier des charges."""
    _ecrire_cadrage(proj)
    chemin = _ecrire_direction(proj, apres=proj.config_path)
    plus_tard = chemin.stat().st_mtime + 10
    os.utime(proj.brief_path, (plus_tard, plus_tard))
    assert _direction_reutilisable(proj) is False


def test_direction_incomplete_est_rejouee(proj):
    """Une clé manquante rend le fichier inutilisable par le designer."""
    _ecrire_cadrage(proj)
    tronquee = {k: v for k, v in DIRECTION_VALIDE.items() if k != "palette"}
    _ecrire_direction(proj, contenu=tronquee, apres=proj.config_path)
    assert _direction_reutilisable(proj) is False


def test_direction_illisible_est_rejouee(proj):
    _ecrire_cadrage(proj)
    chemin = proj.temp_dir / "direction.json"
    chemin.write_text("{ pas du json", encoding="utf-8")
    repere = proj.config_path.stat().st_mtime
    os.utime(chemin, (repere + 10, repere + 10))
    assert _direction_reutilisable(proj) is False
