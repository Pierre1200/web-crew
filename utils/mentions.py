"""
Page de mentions légales — zéro token, pur Python.

Le premier run réel a produit seize liens vers `mentions-legales.html`, une page
qu'aucun module ne savait générer. Le designer avait raison de l'attendre : en
France, un site accessible au public doit indiquer qui l'édite et qui l'héberge.

La page est construite à partir de `config.json`, sans IA : ce sont des faits
administratifs, pas de la rédaction. Ce qui manque est signalé explicitement
dans la page plutôt que deviné, pour que l'oubli se voie à la relecture.

⚠️ Ceci produit un SQUELETTE conforme aux usages, pas un avis juridique. Le
contenu doit être relu et validé par le client avant mise en ligne.
"""
from __future__ import annotations
import re
from html import escape

FICHIER = "mentions-legales.html"

# Rubriques attendues sur un site vitrine français. L'ordre est celui qu'on
# retrouve partout : qui édite, qui publie, qui héberge, puis les droits.
_MENTION_MANQUANTE = "à compléter"


def _premier(source: dict, *cles) -> str:
    """Première valeur non vide parmi plusieurs clés possibles.

    Les config.json des projets ne nomment pas ce champ de la même façon
    (`nom`, `nom_asso`, `nom_galerie`) : on prend ce qui existe.
    """
    for cle in cles:
        valeur = (source.get(cle) or "").strip()
        if valeur:
            return valeur
    return ""


def donnees_mentions(config: dict) -> dict:
    """Rassemble les informations légales depuis config.json.

    Cherche d'abord dans `site.mentions`, puis retombe sur `client`. Toute
    valeur absente devient « à compléter » : mieux vaut un trou visible qu'une
    information inventée sur un document à portée juridique.
    """
    site = config.get("site", {}) or {}
    client = config.get("client", {}) or {}
    mentions = site.get("mentions", {}) or {}
    hebergeur = mentions.get("hebergeur", {}) or {}

    nom = _premier(mentions, "editeur") or _premier(
        client, "nom", "nom_asso", "nom_galerie", "porteur"
    )

    return {
        "editeur": nom or _MENTION_MANQUANTE,
        "statut": _premier(mentions, "statut") or _MENTION_MANQUANTE,
        "adresse": _premier(mentions, "adresse") or _premier(client, "adresse") or "",
        "siret": _premier(mentions, "siret"),
        "rna": _premier(mentions, "rna", "numero_prefecture"),
        "directeur": _premier(mentions, "directeur_publication")
                     or _premier(client, "contact_principal") or _MENTION_MANQUANTE,
        "email": _premier(mentions, "email") or _premier(client, "email"),
        "telephone": _premier(mentions, "telephone") or _premier(client, "telephone"),
        "hebergeur_nom": _premier(hebergeur, "nom") or _MENTION_MANQUANTE,
        "hebergeur_adresse": _premier(hebergeur, "adresse"),
        "hebergeur_site": _premier(hebergeur, "site"),
        "url_site": _premier(site, "url"),
    }


def champs_manquants(donnees: dict) -> list[str]:
    """Informations légalement attendues qui n'ont pas été renseignées."""
    obligatoires = {
        "editeur": "le nom de l'éditeur du site",
        "directeur": "le directeur de la publication",
        "hebergeur_nom": "le nom de l'hébergeur",
    }
    manquants = [
        libelle for cle, libelle in obligatoires.items()
        if donnees[cle] == _MENTION_MANQUANTE
    ]
    if not donnees["siret"] and not donnees["rna"]:
        manquants.append("le SIRET ou le numéro RNA de l'association")
    if not donnees["hebergeur_adresse"]:
        manquants.append("l'adresse de l'hébergeur")
    return manquants


def _extraire(html: str, balise: str) -> str:
    """Récupère l'en-tête ou le pied de l'accueil, pour que la page s'y fonde."""
    trouve = re.search(rf"<{balise}\b.*?</{balise}>", html, re.DOTALL | re.IGNORECASE)
    return trouve.group(0) if trouve else ""


def _ligne(intitule: str, valeur: str) -> str:
    return f"      <p><strong>{intitule}</strong> : {escape(valeur)}</p>\n" if valeur else ""


def rendre_mentions(project) -> tuple[str, list[str]]:
    """Construit la page de mentions légales du projet.

    Retourne (html, champs manquants). La page vit à la racine de `output/` :
    les liens de l'en-tête repris de l'accueil restent donc valides tels quels.
    """
    config = project.load_config()
    donnees = donnees_mentions(config)
    manquants = champs_manquants(donnees)

    index = project.output_dir / "index.html"
    html_accueil = index.read_text(encoding="utf-8") if index.exists() else ""
    entete = _extraire(html_accueil, "header")
    pied = _extraire(html_accueil, "footer")

    identite = (
        _ligne("Éditeur", donnees["editeur"])
        + _ligne("Statut", donnees["statut"])
        + _ligne("Adresse", donnees["adresse"])
        + _ligne("SIRET", donnees["siret"])
        + _ligne("Numéro RNA", donnees["rna"])
        + _ligne("Directeur de la publication", donnees["directeur"])
        + _ligne("Courriel", donnees["email"])
        + _ligne("Téléphone", donnees["telephone"])
    )
    hebergement = (
        _ligne("Hébergeur", donnees["hebergeur_nom"])
        + _ligne("Adresse", donnees["hebergeur_adresse"])
        + _ligne("Site", donnees["hebergeur_site"])
    )

    avertissement = ""
    if manquants:
        # Visible sur la page elle-même : un trou dans un document légal doit
        # sauter aux yeux à la relecture, pas rester tapi dans un journal.
        liste = "".join(f"<li>{escape(m)}</li>" for m in manquants)
        avertissement = (
            '      <p class="mentions__alerte"><strong>À compléter avant mise '
            f'en ligne :</strong></p>\n      <ul>{liste}</ul>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, follow">
    <title>Mentions légales</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
{entete}
    <main class="mentions">
      <h1>Mentions légales</h1>
{avertissement}
      <h2>Éditeur du site</h2>
{identite}
      <h2>Hébergement</h2>
{hebergement}
      <h2>Propriété intellectuelle</h2>
      <p>L'ensemble des contenus de ce site (textes, images, éléments
      graphiques) est protégé par le droit d'auteur. Toute reproduction, même
      partielle, est soumise à l'autorisation préalable de l'éditeur.</p>

      <h2>Données personnelles</h2>
      <p>Les informations transmises via le formulaire de contact servent
      uniquement à répondre à la demande. Elles ne sont ni cédées ni vendues.
      Conformément au règlement général sur la protection des données, vous
      disposez d'un droit d'accès, de rectification et de suppression des
      données vous concernant, en écrivant à l'adresse ci-dessus.</p>

      <h2>Cookies</h2>
      <p>Ce site ne dépose aucun cookie de mesure d'audience ni de publicité.</p>
    </main>
{pied}
</body>
</html>
""", manquants
