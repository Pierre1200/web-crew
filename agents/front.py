"""LES AGENTS QUI ÉCRIVENT LE FRONT NEXT.

Trois agents, trois natures différentes :

    CharteAgent      des VALEURS. Il ne produit pas de CSS, il produit des
                     couleurs et des polices, que Python pose dans les tokens.
    FrontAgent       le code du site. C'est le nœud le plus dur de la chaîne,
                     et ce n'est pas là qu'on économise.
    ReparateurAgent  reçoit une erreur de compilateur et le fichier fautif.

DEUX DÉCISIONS QUI TIENNENT TOUT LE FICHIER.

**On ne transporte jamais du code dans du JSON.** Un fichier TSX entier échappé
dans une chaîne JSON, c'est exactement ce qui a lâché deux fois sur douze au
premier run réel. Les fichiers voyagent donc entre des marqueurs de ligne, que
rien n'oblige à échapper.

**La charte ne renvoie que des valeurs.** Le modèle ne peut pas casser la
structure d'une feuille de style qu'il n'écrit pas. C'est le même principe que
les gabarits de la V1, mais appliqué là où il est sûr : une valeur validée par
une expression régulière ne peut pas devenir du balisage.
"""
from __future__ import annotations

import re
from pathlib import Path

import typer

from agents.base_agent import BaseAgent
from utils.cleaners import compact_json
from utils.docs_next import digest
from utils.project import Project

# ── LE TRANSPORT DES FICHIERS ──────────────────────────────────────────

_OUVERTURE = re.compile(r"^===\s*FICHIER:\s*(.+?)\s*===$", re.MULTILINE)
_FERMETURE = "=== FIN ==="

# Ce que le crew a le droit d'écrire dans le squelette. Tout le reste est
# refusé AVANT d'écrire : un modèle qui réécrit next.config.ts ou base.css
# défait le squelette, et le squelette est ce qui rend le résultat prévisible.
PREFIXES_AUTORISES = ("lib/", "composants/", "app/", "contenu/", "public/assets/")
FICHIERS_INTERDITS = {
    # La charte est écrite par CharteAgent, qui passe juste avant : la laisser
    # ouverte, c'est laisser le front effacer la palette qu'on vient de payer.
    # Les correctifs appartiennent à la boucle visuelle, et à elle seule.
    "app/charte.css", "app/correctifs.css",
    "app/base.css", "app/layout.tsx", "app/error.tsx", "app/not-found.tsx",
    "app/robots.ts", "app/sitemap.ts", "app/flux.xml/route.ts",
    "app/mentions-legales/page.tsx", "lib/site.ts", "lib/contenu.ts",
    "lib/data/messages.ts", "lib/data/LISEZMOI.md", "composants/Enveloppe.tsx",
    "composants/Comportements.tsx", "composants/Etat.tsx", "composants/Cadre.tsx",
    "composants/Trait.tsx", "composants/FormulaireContact.tsx",
}


class FichierRefuse(ValueError):
    """Le modèle a voulu écrire hors de son périmètre."""


def chemin_sur(relatif: str) -> str:
    """Valide un chemin proposé par le modèle. Lève si quoi que ce soit cloche.

    Trois refus, du plus grossier au plus subtil : sortir du dossier, écrire
    hors des zones du crew, écraser un fichier du squelette.
    """
    relatif = relatif.strip()
    # On enlève un « ./ » de tête, et rien d'autre : un lstrip("./") gourmand
    # transformerait « ../../etc/passwd » en « etc/passwd » et désamorcerait le
    # contrôle qui suit.
    if relatif.startswith("./"):
        relatif = relatif[2:]

    if ".." in Path(relatif).parts or Path(relatif).is_absolute():
        raise FichierRefuse(f"Chemin hors du projet : {relatif}")
    if relatif in FICHIERS_INTERDITS:
        raise FichierRefuse(f"Fichier du squelette, non modifiable : {relatif}")
    if relatif != "site.config.ts" and not relatif.startswith(PREFIXES_AUTORISES):
        raise FichierRefuse(f"Hors du périmètre du crew : {relatif}")

    return relatif


def decouper_fichiers(reponse: str) -> dict[str, str]:
    """Extrait les fichiers d'une réponse.

        === FICHIER: lib/types.ts ===
        export type Realisation = { ... };
        === FIN ===

    Un fichier sans marqueur de fin est ignoré : c'est le signe d'une réponse
    coupée, et écrire un fichier tronqué serait pire que de ne rien écrire.
    """
    fichiers: dict[str, str] = {}
    ouvertures = list(_OUVERTURE.finditer(reponse))

    for index, ouverture in enumerate(ouvertures):
        debut = ouverture.end()
        suivante = ouvertures[index + 1].start() if index + 1 < len(ouvertures) else len(reponse)
        bloc = reponse[debut:suivante]

        fin = bloc.find(_FERMETURE)
        if fin == -1:
            continue  # réponse tronquée sur ce fichier

        fichiers[ouverture.group(1)] = bloc[:fin].strip("\n") + "\n"

    return fichiers


def enrober_couche(relatif: str, contenu: str) -> str:
    """Range composants.css dans sa couche, même si le modèle l'a oublié.

    Toute la boucle de correction visuelle repose là-dessus : les correctifs
    sont HORS couche, donc ils battent n'importe quelle règle de n'importe
    quelle couche, quelle que soit sa spécificité. Une feuille de composants
    laissée hors couche briserait cette garantie en silence, et un correctif
    `.hero {...}` serait battu par un `.section .hero {...}` sans que rien ne
    le signale.

    On ne demande donc pas au modèle d'y penser : on l'enveloppe.
    """
    if relatif != "app/composants.css" or "@layer" in contenu:
        return contenu

    corps = "\n".join(f"  {ligne}" if ligne.strip() else ligne
                      for ligne in contenu.rstrip("\n").splitlines())
    return (
        "/* Enveloppé dans sa couche par le crew : les correctifs visuels, hors\n"
        "   couche, doivent pouvoir l'emporter sans `!important`. */\n"
        f"@layer composants {{\n{corps}\n}}\n"
    )


def ecrire_fichiers(site_dir: Path, fichiers: dict[str, str]) -> tuple[list[str], list[str]]:
    """Écrit ce qui est autorisé, renvoie (écrits, refusés)."""
    ecrits, refuses = [], []

    for relatif, contenu in fichiers.items():
        try:
            sur = chemin_sur(relatif)
        except FichierRefuse as e:
            refuses.append(str(e))
            continue

        cible = Path(site_dir) / sur
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(enrober_couche(sur, contenu), encoding="utf-8")
        ecrits.append(sur)

    return ecrits, refuses


# ── LA CHARTE ──────────────────────────────────────────────────────────

# Une valeur de token acceptable : couleurs, tailles, familles de polices,
# fonctions CSS simples. Ce qui est exclu compte plus que ce qui est admis :
# ni « ; » ni « } » (qui fermeraient la règle et en ouvriraient une autre), ni
# « url( » (qui ferait sortir une requête vers un tiers).
_VALEUR_SURE = re.compile(r"^[-#\w\s.,()%/'\"]+$")
_INTERDIT_DANS_VALEUR = re.compile(r"url\s*\(|;|\}|\{|@import|expression\s*\(", re.IGNORECASE)


def valeur_sure(valeur: str) -> bool:
    return bool(_VALEUR_SURE.match(valeur)) and not _INTERDIT_DANS_VALEUR.search(valeur)


def appliquer_tokens(charte_css: str, tokens: dict[str, str]) -> tuple[str, list[str]]:
    """Remplace la VALEUR des tokens existants, sans toucher au reste.

    Un token inconnu est ignoré : les noms sont un contrat, base.css et
    composants.css les utilisent. En inventer un ne casse rien, mais n'a aucun
    effet, et le dire évite de chercher pourquoi la couleur n'a pas bougé.
    """
    ignores = []

    for nom, valeur in tokens.items():
        nom = nom.strip().lstrip("-")
        valeur = str(valeur).strip().rstrip(";").strip()

        if not valeur_sure(valeur):
            ignores.append(f"--{nom} : valeur refusée ({valeur!r})")
            continue

        motif = re.compile(rf"^(\s*--{re.escape(nom)}:\s*)([^;]+)(;)", re.MULTILINE)
        charte_css, remplacements = motif.subn(rf"\g<1>{valeur}\g<3>", charte_css)
        if remplacements == 0:
            ignores.append(f"--{nom} : token absent de la charte")

    return charte_css, ignores


class CharteAgent(BaseAgent):
    """Traduit la direction artistique en valeurs de tokens."""

    MODEL = "claude-opus-5"
    EFFORT = "high"

    def __init__(self, project: Project):
        super().__init__("charte", "Charte, valeurs des tokens de design", project)

    def _prompt_systeme(self) -> str:
        return """Tu traduis une direction artistique en valeurs de tokens CSS.

Tu ne produis PAS de CSS. Tu produis un objet JSON dont les clés sont des noms
de tokens et les valeurs des valeurs CSS simples. Python les posera lui-même
dans la feuille de style : tu ne peux donc rien casser, et tu n'as aucune
syntaxe à respecter au-delà de la valeur elle-même.

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après, sans balises.

Règles absolues :
- contrastes WCAG AA : 4,5:1 pour le texte courant, 3:1 pour les grands titres.
  Les tokens « -encre » sont les variantes FONCÉES, seules utilisées en petit.
- deux accents et pas trois : --action (liens, boutons) et --repere (dates,
  états). Ils ne se touchent jamais dans un même bloc.
- les familles de polices se terminent TOUJOURS par une famille générique de
  secours (serif, sans-serif) et sont écrites entre guillemets si le nom
  contient une espace.
- aucune valeur ne contient « ; », « } », ni « url( » : elles seraient refusées.

N'invente aucun nom de token : ceux qui te sont donnés sont les seuls qui
existent. Tu peux n'en renvoyer qu'une partie."""

    def run(self, context: dict) -> dict:
        charte = Path(self.project.site_dir) / "app" / "charte.css"
        source = charte.read_text(encoding="utf-8")
        noms = re.findall(r"^\s*--([\w-]+):", source, re.MULTILINE)

        try:
            direction = self.read_json("temp/direction.json")
        except (OSError, ValueError):
            direction = {}

        plan = context.get("plan", {})
        message = f"""Direction artistique retenue :
{compact_json(direction)}

Guide de style du plan :
{compact_json(plan.get("style_guide", {}))}

Tokens existants, les seuls que tu peux renseigner :
{", ".join(sorted(set(noms)))}

Renvoie le JSON des valeurs."""

        reponse = self.call_claude(self._prompt_systeme(), message, max_tokens=4000)
        tokens = self.parse_json_response(reponse)

        nouvelle, ignores = appliquer_tokens(source, tokens)
        charte.write_text(nouvelle, encoding="utf-8")

        for avertissement in ignores:
            typer.echo(f"   ⚠️  {avertissement}")
        typer.echo(f"🎨 Charte écrite, {len(tokens) - len(ignores)} token(s) posé(s)")

        return {"tokens": tokens, "ignores": ignores}


# ── LE FRONT ───────────────────────────────────────────────────────────

class FrontAgent(BaseAgent):
    """Écrit le modèle de contenu, la couture, les composants et les pages.

    Un seul appel pour l'ensemble, comme le designer de la V1 : ces fichiers se
    répondent les uns aux autres (un type, une fonction de lecture, une page
    qui l'appelle), et les produire en trois appels séparés, c'est produire
    trois versions d'un même contrat.
    """

    MODEL = "claude-opus-5"
    EFFORT = "xhigh"

    def __init__(self, project: Project):
        super().__init__("front", "Front, pages, composants et modèle de contenu", project)

    def _contrat(self) -> str:
        """Les règles du squelette, lues DANS le squelette.

        Elles ne sont pas recopiées dans ce prompt : le jour où le contrat
        change, il change à un seul endroit, et le prompt suit tout seul.
        """
        morceaux = []
        for fichier in ("LISEZMOI.md", "lib/data/LISEZMOI.md"):
            chemin = Path(self.project.site_dir) / fichier
            if chemin.is_file():
                morceaux.append(f"--- {fichier} ---\n{chemin.read_text(encoding='utf-8')}")
        return "\n\n".join(morceaux)

    def _arborescence(self) -> str:
        """Ce que le squelette contient déjà, pour ne pas le réécrire."""
        racine = Path(self.project.site_dir)
        fichiers = sorted(
            str(c.relative_to(racine))
            for c in racine.rglob("*")
            if c.is_file()
            and not any(p in {"node_modules", ".next", "out"} for p in c.relative_to(racine).parts)
        )
        return "\n".join(f"  {f}" for f in fichiers)

    def _prompt_systeme(self) -> str:
        return f"""Tu écris le front d'un site vitrine, en Next.js App Router, React et
TypeScript, en EXPORT STATIQUE. Tu pars d'un squelette déjà validé et tu ne
produis que les variations.

{digest(Path(self.project.site_dir))}

FORMAT DE RÉPONSE. Un fichier par bloc, exactement ainsi :

=== FICHIER: lib/types.ts ===
export type Realisation = {{ ... }};
=== FIN ===

Aucun texte hors des blocs. Pas de balises markdown, pas de ```. Le contenu du
bloc est le fichier, tel quel, en entier. N'abrège JAMAIS avec « ... » ou
« le reste est inchangé » : ce que tu n'écris pas n'existe pas.

CE QUE TU AS LE DROIT D'ÉCRIRE, et rien d'autre :
- site.config.ts (les valeurs du site : nom, menu, mentions, formulaire)
- lib/types.ts et lib/data/*.ts (le modèle de contenu et la couture)
- contenu/<collection>/*.json (les données)
- composants/*.tsx que tu crées
- app/page.tsx et app/<segment>/page.tsx
- app/composants.css (son contenu est rangé dans `@layer composants`)

Toute tentative d'écrire ailleurs sera refusée avant écriture. En particulier
tu ne touches NI à app/base.css, NI à app/layout.tsx, NI à next.config.ts.

LA RÈGLE MÈRE : aucune donnée en dur dans le balisage. Une page appelle une
fonction de lib/data/, jamais un fichier directement. Les contraintes de
couture qui suivent ne sont pas des conseils, elles sont le produit."""

    def run(self, context: dict) -> dict:
        plan = context.get("plan", {})
        textes = {}
        try:
            textes = self.read_json("temp/textes.json")
        except (OSError, ValueError):
            self.logger.info("Pas de textes.json, le front sera écrit depuis le brief seul")

        message = f"""{self.cahier_des_charges(plan)}

CONTRAT DU SQUELETTE, à respecter à la lettre :
{self._contrat()}

FICHIERS DÉJÀ PRÉSENTS dans le projet (ne les réécris pas, sauf ceux que tu as
le droit d'écrire) :
{self._arborescence()}

BRIEF DU CLIENT :
{self.read_text("brief.md")}

TEXTES DÉJÀ RÉDIGÉS (à placer dans contenu/ ou site.config.ts, pas à réécrire) :
{compact_json(textes) if textes else "aucun"}

Écris maintenant tous les fichiers nécessaires."""

        # Streaming et budget large : c'est le plus gros appel de la chaîne, et
        # une réponse coupée au milieu d'un fichier fait perdre la passe
        # entière. `decouper_fichiers` ignore les fichiers sans marqueur de
        # fin, donc une troncature ne produit jamais de fichier à moitié écrit.
        reponse = self.call_claude_continuable(
            self._prompt_systeme(), message, max_tokens=64000, auto_continue=True
        )

        fichiers = decouper_fichiers(reponse)
        if not fichiers:
            (self.project.logs_dir / "front_reponse_sans_fichier.txt").write_text(
                reponse, encoding="utf-8"
            )
            raise ValueError(
                "Le front n'a produit aucun fichier exploitable, réponse brute "
                f"dans {self.project.logs_dir}/front_reponse_sans_fichier.txt"
            )

        ecrits, refuses = ecrire_fichiers(self.project.site_dir, fichiers)

        for refus in refuses:
            typer.echo(f"   ⛔ {refus}")
            self.logger.warning(f"Écriture refusée, {refus}")

        typer.echo(f"✅ Front écrit, {len(ecrits)} fichier(s)")
        for fichier in ecrits:
            typer.echo(f"   • {fichier}")

        return {"ecrits": ecrits, "refuses": refuses}


# ── LA RÉPARATION ──────────────────────────────────────────────────────

class ReparateurAgent(BaseAgent):
    """Corrige ce que la porte de build a refusé.

    Il reçoit l'erreur du compilateur ET le contenu des fichiers mis en cause.
    C'est la différence avec la V1, qui aiguillait sur un type de problème
    déduit d'une inspection du HTML : ici le diagnostic vient de l'outil, il
    est exact, et il désigne le fichier et la ligne.
    """

    MODEL = "claude-opus-5"
    EFFORT = "xhigh"

    def __init__(self, project: Project):
        super().__init__("reparateur", "Réparateur, corrige les erreurs de build", project)

    def _prompt_systeme(self) -> str:
        return f"""Tu corriges des erreurs de compilation dans un site Next.js en export
statique. On te donne le diagnostic exact de l'outil et le contenu des fichiers
concernés.

{digest(Path(self.project.site_dir))}

Réponds avec les fichiers CORRIGÉS EN ENTIER, un par bloc :

=== FICHIER: chemin/du/fichier.tsx ===
le fichier complet, corrigé
=== FIN ===

Aucun texte hors des blocs. Ne renvoie que les fichiers que tu modifies.
N'abrège jamais : un fichier renvoyé remplace l'ancien intégralement.

Corrige la CAUSE, pas le symptôme. Supprimer un appel, désactiver une règle
avec eslint-disable ou remplacer un type par `any` fait passer la porte et
casse le site : ce sont des réparations interdites."""

    def _joindre_fichiers(self, problemes: list[dict]) -> str:
        """Le contenu des fichiers mis en cause, sans doublon."""
        racine = Path(self.project.site_dir)
        vus, morceaux = set(), []

        for probleme in problemes:
            relatif = probleme.get("fichier") or ""
            if not relatif or relatif in vus:
                continue
            chemin = racine / relatif
            if not chemin.is_file():
                continue
            vus.add(relatif)
            morceaux.append(f"=== FICHIER: {relatif} ===\n{chemin.read_text(encoding='utf-8')}\n=== FIN ===")

        return "\n\n".join(morceaux)

    def run(self, context: dict) -> dict:
        resultat = context["resultat_porte"]
        problemes = resultat["problemes"]

        detail = "\n".join(
            f"- [{p['type']}] {p['fichier'] or '?'}"
            + (f":{p['ligne']}" if p.get("ligne") else "")
            + f", {p['message']}"
            for p in problemes
        )
        fichiers = self._joindre_fichiers(problemes)

        message = f"""L'étape « {resultat['etape_echouee']} » a échoué.

DIAGNOSTIC DE L'OUTIL :
{detail}

CONTENU DES FICHIERS CONCERNÉS :
{fichiers or "(aucun fichier n'a pu être rattaché au diagnostic ; sers-toi du message)"}

Renvoie les fichiers corrigés."""

        reponse = self.call_claude_continuable(
            self._prompt_systeme(), message, max_tokens=32000, auto_continue=True
        )

        corriges = decouper_fichiers(reponse)
        ecrits, refuses = ecrire_fichiers(self.project.site_dir, corriges)

        for refus in refuses:
            typer.echo(f"   ⛔ {refus}")
        typer.echo(f"   🔧 {len(ecrits)} fichier(s) corrigé(s)")

        return {"ecrits": ecrits, "refuses": refuses}


# ── LES CORRECTIFS VISUELS ─────────────────────────────────────────────

def appliquer_correctifs(site_dir: Path, problemes: list[dict]) -> int:
    """Ajoute les règles proposées par la critique visuelle. ZÉRO TOKEN.

    La critique a déjà rédigé le CSS : on ne redemande rien au modèle.

    Elles vont dans app/correctifs.css, importé EN DERNIER par le layout. À
    spécificité égale, la dernière règle l'emporte : c'est ce qui rend le
    mécanisme fiable sans un seul `!important`. Et comme le fichier ne contient
    que ça, annuler une passe de correction revient à le vider.
    """
    from utils.cleaners import strip_markdown_fences

    correctifs = [p for p in problemes if (p.get("correction_css") or "").strip()]
    if not correctifs:
        return 0

    chemin = Path(site_dir) / "app" / "correctifs.css"
    if not chemin.exists():
        return 0

    morceaux = []
    for p in correctifs:
        # « */ » dans un constat fermerait le commentaire et ferait passer la
        # suite pour du CSS. On le retire avant, pas après.
        constat = (p.get("constat") or "").replace("*/", "").strip()
        morceaux.append(
            f"/* [{p.get('gravite', '?')}] {p.get('zone', '?')} "
            f"({p.get('format', 'tous')}) : {constat[:140]} */"
        )
        morceaux.append(strip_markdown_fences(p["correction_css"]).strip())

    entete = (
        "\n\n/* --- Passe de critique visuelle "
        f"({len(correctifs)} correctif(s)) --- */\n"
    )
    chemin.write_text(
        chemin.read_text(encoding="utf-8") + entete + "\n".join(morceaux) + "\n",
        encoding="utf-8",
    )
    return len(correctifs)
