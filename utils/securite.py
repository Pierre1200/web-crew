"""
Sécurité du site livré — inventaire, en-têtes, durcissement. Zéro token.

Un site statique a une surface d'attaque minuscule : pas de serveur applicatif,
pas de base, pas de dépendances à patcher, pas de comptes. Prétendre le
contraire serait du théâtre. Les vrais sujets sont au nombre de trois :

  1. LES TIERS — polices, lecteurs vidéo, formulaires : de la donnée qui part
     vers des services que le client n'a jamais choisis.
  2. LE DURCISSEMENT ABSENT — en-têtes HTTP et CSP : gratuit, et ça se voit
     dans un audit.
  3. LES SECRETS — une clé oubliée dans un fichier qu'on s'apprête à livrer.

Tout est déterministe ici : la sécurité se vérifie par motifs, pas par
jugement. Un modèle coûterait de l'argent et introduirait du hasard là où une
expression régulière est plus fiable et reproductible.
"""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import urlparse

# Contextes d'utilisation d'une ressource externe → directive CSP concernée.
_DIRECTIVE_PAR_CONTEXTE = {
    "script": "script-src",
    "style": "style-src",
    "font": "font-src",
    "image": "img-src",
    "iframe": "frame-src",
    "connexion": "connect-src",
    "formulaire": "form-action",
}

# Motifs de secrets. Volontairement larges : un faux positif se lève en dix
# secondes, une clé livrée à un client se révoque et se regrette longtemps.
_MOTIFS_SECRETS = (
    ("clé API Anthropic", r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    ("clé API générique", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("jeton GitHub", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ("clé Google", r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    ("jeton JWT", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("clé AWS", r"\bAKIA[0-9A-Z]{16}\b"),
    ("variable secrète", r"(?i)\b(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
)

_EXTENSIONS_POLICES = (".woff2", ".woff", ".ttf", ".otf", ".eot")

# Hôtes qui servent des FICHIERS de police, quelle que soit la balise qui les
# annonce. Sans ça, un <link rel="preconnect" href="https://fonts.gstatic.com">
# serait classé « style » (aucune extension de police dans l'URL), font-src
# n'autoriserait pas gstatic, et les polices seraient bloquées à l'affichage.
_HOTES_POLICES = {
    "https://fonts.gstatic.com",
    "https://use.typekit.net",
    "https://p.typekit.net",
}


# ── INVENTAIRE DES TIERS ───────────────────────────────────────────────

def _origine(url: str) -> str:
    """https://fonts.gstatic.com/s/abc.woff2 → https://fonts.gstatic.com"""
    morceaux = urlparse(url)
    if not morceaux.scheme or not morceaux.netloc:
        return ""
    return f"{morceaux.scheme}://{morceaux.netloc}"


def inventorier_tiers(output_dir: Path) -> dict[str, set[str]]:
    """Recense TOUS les domaines externes contactés par le site livré.

    C'est la réponse exacte à « où partent les données de mes visiteurs ? ».
    Retourne {origine: {contextes}}, par exemple
    {"https://fonts.gstatic.com": {"font"}}.
    """
    inventaire: dict[str, set[str]] = {}

    def noter(url: str, contexte: str):
        origine = _origine(url)
        if not origine:
            return
        # Un hôte de polices sert des fichiers de police, même quand la balise
        # qui l'annonce (preconnect) ne le laisse pas deviner.
        if origine in _HOTES_POLICES:
            contexte = "font"
        inventaire.setdefault(origine, set()).add(contexte)

    for page in sorted(output_dir.rglob("*.html")):
        html = page.read_text(encoding="utf-8", errors="ignore")

        for url in re.findall(r'<script[^>]+src="([^"]+)"', html):
            noter(url, "script")
        for url in re.findall(r'<link[^>]+href="([^"]+)"', html):
            noter(url, "font" if url.endswith(_EXTENSIONS_POLICES) else "style")
        for url in re.findall(r'<img[^>]+src="([^"]+)"', html):
            noter(url, "image")
        for url in re.findall(r'<iframe[^>]+src="([^"]+)"', html):
            noter(url, "iframe")
        for url in re.findall(r'<form[^>]+action="([^"]+)"', html):
            noter(url, "formulaire")
            # Nos formulaires sont envoyés en JavaScript par
            # `fetch(form.action, …)` : l'URL est une VARIABLE, donc invisible
            # pour l'analyse du script. Sans cette ligne, connect-src
            # n'autoriserait pas la destination et la CSP bloquerait
            # silencieusement l'envoi — le visiteur croirait le site cassé.
            noter(url, "connexion")

    for feuille in sorted(output_dir.rglob("*.css")):
        css = feuille.read_text(encoding="utf-8", errors="ignore")
        for url in re.findall(r'url\(\s*["\']?(https?://[^"\')]+)', css):
            noter(url, "font" if url.endswith(_EXTENSIONS_POLICES) else "image")
        # @import charge une feuille de style distante
        for url in re.findall(r'@import\s+(?:url\()?["\']?(https?://[^"\')\s]+)', css):
            noter(url, "style")

    for script in sorted(output_dir.rglob("*.js")):
        js = script.read_text(encoding="utf-8", errors="ignore")
        for url in re.findall(r'fetch\(\s*["\'](https?://[^"\']+)', js):
            noter(url, "connexion")

    return inventaire


# ── POLITIQUE DE SÉCURITÉ DU CONTENU (CSP) ─────────────────────────────

def construire_csp(inventaire: dict[str, set[str]], styles_inline: bool = False) -> str:
    """Construit une CSP à partir des tiers RÉELLEMENT utilisés par le site.

    Une CSP recopiée d'un tutoriel casse le site ou ne protège rien. Celle-ci
    est déduite de ce que la page charge vraiment : tout le reste est refusé.

    `styles_inline` n'est activé que si le site contient réellement des
    attributs style= — une concession qu'on préfère éviter, mais qui vaut mieux
    qu'un site cassé.
    """
    sources: dict[str, set[str]] = {}
    for origine, contextes in inventaire.items():
        for contexte in contextes:
            directive = _DIRECTIVE_PAR_CONTEXTE.get(contexte)
            if directive:
                sources.setdefault(directive, set()).add(origine)

    def liste(directive: str, base: str) -> str:
        valeurs = " ".join(sorted(sources.get(directive, set())))
        return f"{directive} {base}{' ' + valeurs if valeurs else ''}"

    directives = [
        "default-src 'self'",
        liste("script-src", "'self'"),
        liste("style-src", "'self'" + (" 'unsafe-inline'" if styles_inline else "")),
        liste("font-src", "'self'"),
        liste("img-src", "'self' data:"),
        liste("frame-src", "'self'"),
        liste("connect-src", "'self'"),
        liste("form-action", "'self'"),
        # Verrous sans coût : rien n'en a besoin sur un site vitrine.
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'self'",
    ]
    return "; ".join(directives)


def a_des_styles_inline(output_dir: Path) -> bool:
    """Le site utilise-t-il des attributs style= ou des balises <style> ?"""
    for page in output_dir.rglob("*.html"):
        html = page.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'\sstyle\s*=\s*"', html) or "<style" in html:
            return True
    return False


# ── FICHIERS D'EN-TÊTES ────────────────────────────────────────────────

_EN_TETES_COMMUNS = (
    ("X-Content-Type-Options", "nosniff",
     "empêche le navigateur de deviner un type de fichier"),
    ("Referrer-Policy", "strict-origin-when-cross-origin",
     "ne transmet pas l'adresse complète de la page aux sites tiers"),
    ("Permissions-Policy", "geolocation=(), microphone=(), camera=(), interest-cohort=()",
     "refuse des capacités dont le site n'a aucun besoin"),
    ("X-Frame-Options", "SAMEORIGIN",
     "empêche l'affichage du site dans le cadre d'un autre (clickjacking)"),
)


def rendre_headers(csp: str, report_only: bool = False) -> str:
    """Fichier `_headers` — lu par Netlify et Cloudflare Pages."""
    nom_csp = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
    lignes = [
        "# En-têtes de sécurité — générés par web-crew depuis le site réel.",
        "# Netlify et Cloudflare Pages lisent ce fichier automatiquement.",
        "",
        "/*",
        f"  {nom_csp}: {csp}",
    ]
    lignes += [f"  {nom}: {valeur}" for nom, valeur, _ in _EN_TETES_COMMUNS]
    return "\n".join(lignes) + "\n"


def rendre_htaccess(csp: str, report_only: bool = False) -> str:
    """Fichier `.htaccess` — pour un hébergement Apache classique (OVH, o2switch…)."""
    nom_csp = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
    lignes = [
        "# En-têtes de sécurité — générés par web-crew depuis le site réel.",
        "# Hébergement Apache uniquement. Sur Netlify ou Cloudflare, c'est",
        "# le fichier _headers qui s'applique.",
        "",
        "<IfModule mod_headers.c>",
        f'  Header always set {nom_csp} "{csp}"',
    ]
    lignes += [f'  Header always set {nom} "{valeur}"' for nom, valeur, _ in _EN_TETES_COMMUNS]
    lignes += ["</IfModule>"]
    return "\n".join(lignes) + "\n"


# ── RECHERCHE DE SECRETS ───────────────────────────────────────────────

def chercher_secrets(dossier: Path) -> list[dict]:
    """Cherche des secrets dans les fichiers qu'on s'apprête à livrer.

    Ne corrige JAMAIS : un secret trouvé doit être révoqué par une personne,
    pas effacé en douce par un programme.
    """
    trouvailles = []
    if not dossier.is_dir():
        return trouvailles

    for fichier in sorted(dossier.rglob("*")):
        if not fichier.is_file() or fichier.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".webp", ".gif", ".woff", ".woff2", ".ttf"
        }:
            continue
        try:
            contenu = fichier.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for libelle, motif in _MOTIFS_SECRETS:
            for trouve in re.finditer(motif, contenu):
                extrait = trouve.group(0)
                trouvailles.append({
                    "fichier": fichier.name,
                    "type": libelle,
                    # On ne recopie jamais le secret en entier dans un rapport
                    "extrait": extrait[:12] + "…" if len(extrait) > 12 else extrait,
                })
    return trouvailles


# ── AUDIT DU LIVRABLE ──────────────────────────────────────────────────

def auditer(output_dir: Path) -> list[dict]:
    """Contrôles de sécurité sur le site généré. Retourne une liste de constats
    {type, niveau, message}, dans le même esprit que le validateur."""
    constats = []

    def noter(type_: str, niveau: str, message: str):
        constats.append({"type": type_, "niveau": niveau, "message": message})

    if not output_dir.is_dir():
        return constats

    for page in sorted(output_dir.rglob("*.html")):
        nom = page.relative_to(output_dir).as_posix()
        html = page.read_text(encoding="utf-8", errors="ignore")

        # Une ressource en http:// sur une page servie en https est bloquée
        # par le navigateur — le site paraît cassé sans explication.
        for url in re.findall(r'(?:src|href)="(http://[^"]+)"', html):
            noter("contenu_mixte", "erreur",
                  f"{nom} : ressource en http:// — sera bloquée en https ({url})")

        # Une page ouverte avec target=_blank garde une référence vers la nôtre
        # et peut la rediriger : rel=noopener coupe ce lien.
        for balise in re.findall(r'<a[^>]+target="_blank"[^>]*>', html):
            if "noopener" not in balise:
                noter("lien_sans_noopener", "warning",
                      f"{nom} : lien target=\"_blank\" sans rel=\"noopener noreferrer\"")

        for balise in re.findall(r"<iframe[^>]*>", html):
            if "referrerpolicy" not in balise:
                noter("iframe_sans_referrerpolicy", "warning",
                      f"{nom} : iframe sans referrerpolicy — l'adresse de la page "
                      "est transmise au service tiers")

        for adresse in set(re.findall(r"mailto:([^\"'?>]+)", html)):
            noter("email_en_clair", "warning",
                  f"{nom} : adresse {adresse} en clair — moissonnable par les robots à spam")

        if re.search(r"<form[^>]*>", html) and "_gotcha" not in html:
            noter("formulaire_sans_piege", "warning",
                  f"{nom} : formulaire sans pot de miel anti-robot")

    for script in sorted(output_dir.rglob("*.js")):
        js = script.read_text(encoding="utf-8", errors="ignore")
        nom = script.relative_to(output_dir).as_posix()
        for dangereux in ("innerHTML", "outerHTML", "document.write", "eval("):
            if dangereux in js:
                noter("js_dangereux", "erreur",
                      f"{nom} : usage de {dangereux} — voie d'injection si la "
                      "valeur vient du visiteur")

    return constats


# ── DURCISSEMENT (corrections mécaniques) ──────────────────────────────

def durcir_liens_externes(html: str) -> tuple[str, int]:
    """Ajoute rel="noopener noreferrer" aux liens target="_blank" qui en manquent."""
    corriges = 0

    def corriger(trouve):
        nonlocal corriges
        balise = trouve.group(0)
        if "noopener" in balise:
            return balise
        corriges += 1
        if re.search(r'\brel="([^"]*)"', balise):
            return re.sub(r'\brel="([^"]*)"',
                          lambda m: f'rel="{m.group(1)} noopener noreferrer"'.replace("  ", " "),
                          balise)
        return balise[:-1].rstrip() + ' rel="noopener noreferrer">'

    return re.sub(r'<a[^>]+target="_blank"[^>]*>', corriger, html), corriges


def ajouter_pot_de_miel(html: str) -> tuple[str, int]:
    """Ajoute un champ piège à chaque formulaire.

    Un robot remplit tous les champs qu'il trouve ; un humain ne voit pas
    celui-ci. Formspree reconnaît nativement le nom `_gotcha` et jette
    silencieusement les envois où il est rempli. Le champ est masqué par une
    classe CSS (pas de style inline, qui casserait la CSP).
    """
    if "_gotcha" in html:
        return html, 0

    piege = (
        '<p class="piege-robot" aria-hidden="true">'
        '<label>Ne pas remplir<input type="text" name="_gotcha" tabindex="-1" '
        'autocomplete="off"></label></p>'
    )
    ajoutes = 0

    def inserer(trouve):
        nonlocal ajoutes
        ajoutes += 1
        return trouve.group(0) + piege

    return re.sub(r"<form[^>]*>", inserer, html), ajoutes


CSS_POT_DE_MIEL = """
/* === Sécurité : champ piège anti-robot (web-crew) === */
.piege-robot {
  position: absolute;
  left: -9999px;
  width: 1px;
  height: 1px;
  overflow: hidden;
}
"""
