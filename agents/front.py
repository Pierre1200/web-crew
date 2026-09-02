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
from utils.pages import collections_declarees
from utils.squelette import classes_du_squelette, inventaire_api
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

TU NE PRODUIS PAS DE CSS. Tu produis un objet JSON dont les clés sont des noms
de tokens et les valeurs des valeurs CSS. Python les pose lui-même dans la
feuille : tu ne peux donc rien casser, et tu n'as aucune syntaxe à respecter
au-delà de la valeur elle-même.

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après, sans balises.

COMMENT LES TOKENS S'EMPLOIENT. Le contraste se juge sur ces paires, et sur
elles seules :

  --encre        sur --fond        texte courant, minimum 4,5:1
  --encre-douce  sur --fond        texte secondaire, minimum 4,5:1
  --action-encre sur --fond        liens et libellés, minimum 4,5:1
  --repere-encre sur --fond        dates et états, minimum 4,5:1
  --fond         sur --action-encre texte des boutons pleins, minimum 4,5:1
  --encre        sur --fond-pose   texte dans les encadrés, minimum 4,5:1

Les tokens sans suffixe (--action, --repere) servent aux aplats, aux bordures
et aux traits, jamais à du texte. Les variantes « -encre » sont les seules
autorisées en petit corps.

RÈGLES ABSOLUES
- deux accents, pas trois : --action porte l'action (liens, boutons),
  --repere porte le temps (dates, états). Ils ne se touchent jamais dans un
  même bloc.
- oklch() et color-mix(in oklab, ...) sont acceptés et préférables : ils
  donnent un système tonal cohérent plutôt qu'une liste de couleurs sans lien.
- une famille de police se termine TOUJOURS par une famille générique de
  secours, et s'écrit entre guillemets si son nom contient une espace. Le nom
  doit être l'orthographe EXACTE d'une police Google : elle sera téléchargée
  telle quelle, et un nom inconnu ne donne aucun fichier.
- aucune valeur ne contient « ; », « } » ni « url( » : elles seraient refusées
  avant d'être posées.

N'invente aucun nom de token : ceux qu'on te donne sont les seuls qui existent.
Tu peux n'en renseigner qu'une partie ; ce que tu omets garde sa valeur par
défaut, qui est lisible mais terne.

Forme de la réponse :

{"fond": "oklch(0.97 0.01 85)", "encre": "oklch(0.22 0.02 60)",
 "action": "oklch(0.55 0.14 30)", "police-titre": "\"Fraunces\", Georgia, serif"}"""

    def run(self, context: dict) -> dict:
        charte = Path(self.project.site_dir) / "app" / "charte.css"
        source = charte.read_text(encoding="utf-8")
        noms = re.findall(r"^\s*--([\w-]+):", source, re.MULTILINE)

        try:
            direction = self.read_json("temp/direction.json")
        except (OSError, ValueError):
            direction = {}

        plan = context.get("plan", {})
        message = f"""Direction artistique retenue pour ce projet :
{compact_json(direction)}

Cadrage du chef de projet :
{compact_json(plan.get("style_guide", {}))}

Les tokens existants, les seuls que tu peux renseigner :
{", ".join(sorted(set(noms)))}

Traduis cette direction en valeurs. Si elle nomme des couleurs en oklch ou des
dérivations en color-mix, reprends-les telles quelles plutôt que de les
reconvertir."""

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

    def _prompt_systeme(self) -> str:
        """Tout ce qui ne dépend pas du brief.

        La séparation n'est pas cosmétique : ce bloc est identique d'un appel à
        l'autre pour un même projet, donc il se met en cache côté API. Le brief
        et les textes, eux, changent, et vivent dans le message.
        """
        site = Path(self.project.site_dir)

        return f"""Tu écris le front d'un site vitrine, en Next.js App Router, React et
TypeScript, en EXPORT STATIQUE. Tu pars d'un squelette déjà validé et tu ne
produis que les variations : le modèle de contenu, la couture de lecture, les
composants, les pages et leur habillage.

Trois portes automatiques jugeront ton travail sans indulgence : ESLint,
TypeScript et `next build`. Ce qui ne passe pas les trois n'est jamais publié.

{digest(site)}

CE QUE LE SQUELETTE OFFRE DÉJÀ. Tu l'importes, tu ne le réécris pas :
{inventaire_api(site)}

L'enveloppe pose DÉJÀ le lien d'évitement, l'en-tête, le menu, la zone de
contenu et le pied de page. Une page ne les réécrit jamais : elle rend le
contenu, et rien d'autre. Écrire un second <header> dans une page produit deux
en-têtes, et aucune porte ne le signale.

CLASSES CSS DÉJÀ HABILLÉES par app/base.css, à réutiliser telles quelles :
{", ".join(classes_du_squelette(site))}

Toute autre classe que tu emploies, tu la définis toi-même dans
app/composants.css. Une classe employée et jamais définie donne un bloc sans
style : la construction passe, et le défaut ne se voit qu'à l'oeil.

CE QUE TU AS LE DROIT D'ÉCRIRE, et rien d'autre :
- site.config.ts (nom, menu, mentions, motifs du formulaire, collections)
- lib/types.ts et lib/data/*.ts (le modèle de contenu et la couture)
- contenu/<collection>/*.json (les données)
- composants/*.tsx que tu crées
- app/page.tsx et app/<segment>/page.tsx
- app/composants.css (son contenu est rangé dans `@layer composants`)

Toute tentative d'écrire ailleurs est refusée avant écriture. En particulier tu
ne touches NI à app/base.css, NI à app/charte.css, NI à app/layout.tsx, NI à
next.config.ts.

ÉCRIS LES FICHIERS DANS CET ORDRE, parce que chacun dépend du précédent :
  1. lib/types.ts                  le contrat
  2. contenu/<collection>/*.json   les données, à la forme du contrat
  3. lib/data/*.ts                 la lecture : async, filtre et trie
  4. composants/*.tsx              ce que plusieurs pages partagent
  5. app/**/page.tsx               les pages, qui n'appellent que lib/data
  6. site.config.ts                les valeurs du site
  7. app/composants.css            l'habillage

QUATRE RÈGLES QUE LE CONTRAT NE DIT PAS, ET QUI CASSENT EN SILENCE
- Une page est un Server Component `async`. « use client » seulement pour un
  composant qui a besoin d'un état ou d'un écouteur d'événement.
- Aucun état déduit d'une date n'est calculé dans une page. `<Etat debut={{...}} fin={{...}} />` le recalcule chez le visiteur. Calculé au rendu, il serait figé
  au jour de la construction : le site annoncerait « en cours » des mois après.
- Une image qui n'existe pas encore ne se remplace pas par du texte.
  `<Cadre format="4x3" legende="..." />` tient exactement sa place, et sa
  légende dit ce qu'il faudra photographier.
- Champ absent = `null`, jamais `undefined` ni chaîne vide.
- Aucun tiret cadratin dans les textes que tu écris. C'est une règle de maison,
  elle vaut pour tout ce qui sera lu par un visiteur. Une virgule, un
  deux-points ou une parenthèse font le travail.

FORMAT DE RÉPONSE. Un fichier par bloc, exactement ainsi :

=== FICHIER: lib/types.ts ===
export type Realisation = {{
  id: string;
  slug: string;
  titre: string;
  chapo: string | null;
  en_ligne: boolean;
  cree_le: string;
  modifie_le: string;
}};
=== FIN ===

=== FICHIER: contenu/realisations/01-exemple.json ===
{{
  "id": "01-exemple",
  "slug": "un-titre-lisible",
  "titre": "Un titre lisible",
  "chapo": null,
  "en_ligne": true,
  "cree_le": "2026-03-12T00:00:00Z",
  "modifie_le": "2026-03-12T00:00:00Z"
}}
=== FIN ===

Aucun texte hors des blocs. Pas de balises markdown, pas de ```. Le contenu du
bloc est le fichier, tel quel, en entier. N'abrège JAMAIS avec « ... » ou « le
reste est inchangé » : ce que tu n'écris pas n'existe pas, et un fichier sans
marqueur de fin est jeté.

AVANT DE RÉPONDRE, VÉRIFIE CES SIX POINTS
  1. aucune page n'appelle `lireCollection` ni un chemin de fichier : elles
     passent toutes par une fonction de lib/data ;
  2. chaque type porte slug, en_ligne, cree_le, modifie_le, et des dates ISO ;
  3. chaque classe employée est dans la liste ci-dessus, ou définie par toi
     dans app/composants.css ;
  4. aucune section du cahier des charges ne manque, et aucune n'est ajoutée ;
  5. aucun import ne pointe vers un fichier absent de l'inventaire et que tu
     n'as pas écrit ;
  6. aucun fichier n'est tronqué."""

    def run(self, context: dict) -> dict:
        plan = context.get("plan", {})
        config = self.load_config()

        textes = {}
        try:
            textes = self.read_json("temp/textes.json")
        except (OSError, ValueError):
            self.logger.info("Pas de textes.json, le front sera écrit depuis le brief seul")

        # Les collections sont déclarées par Pierre dans config.json. Sans
        # elles, le modèle invente un identifiant, et le dossier contenu/ ne
        # correspond plus à rien de ce que le projet attendait.
        collections = collections_declarees(config)

        message = f"""{self.cahier_des_charges(plan)}

CONTRAT DU SQUELETTE, il fait autorité :
{self._contrat()}

COLLECTIONS DÉCLARÉES POUR CE PROJET. Reprends ces identifiants tels quels,
côté dossier `contenu/` comme côté adresses :
{compact_json(collections) if collections else "aucune"}

BRIEF DU CLIENT :
{self.read_text("brief.md")}

TEXTES DÉJÀ RÉDIGÉS. Place-les dans contenu/ ou site.config.ts, ne les réécris
pas et n'en invente pas d'autres :
{compact_json(textes) if textes else "aucun"}

Écris maintenant tous les fichiers nécessaires, dans l'ordre indiqué."""

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
        site = Path(self.project.site_dir)

        return f"""Tu corriges des erreurs de compilation dans un site Next.js en export
statique. On te donne le diagnostic exact de l'outil et le contenu des fichiers
concernés. Le diagnostic vient d'ESLint, de TypeScript ou de `next build` : il
ne se trompe pas sur ce qu'il affirme.

{digest(site)}

CE QUE LE SQUELETTE OFFRE, et que tu n'as pas à recréer pour réparer :
{inventaire_api(site)}

LES QUATRE ERREURS LES PLUS FRÉQUENTES SUR CE SQUELETTE, et leur vraie cause :

- « export const dynamic ... not configured on route » : une route asynchrone
  (sitemap, robots, route.ts) sans `export const dynamic = "force-static"`.
  Ajoute la ligne dans le fichier de la route, le message ne dit pas lequel.
- « Calling setState synchronously within an effect » : un `useEffect` qui pose
  un état. Passe par `useSyncExternalStore`, ou remonte le calcul au rendu.
  Ne désactive pas la règle.
- « Type X is not assignable to type Y » entre une donnée et son type : c'est
  presque toujours `undefined` ou une chaîne vide là où le contrat dit `null`.
  Corrige la DONNÉE, pas le type.
- une propriété qui n'existe pas sur un type : le contenu et lib/types.ts ont
  divergé. Le contrat gagne : c'est le fichier de contenu qu'on aligne.

RÉPONDS AVEC LES FICHIERS CORRIGÉS EN ENTIER, un par bloc :

=== FICHIER: chemin/du/fichier.tsx ===
le fichier complet, corrigé
=== FIN ===

Aucun texte hors des blocs. Ne renvoie QUE les fichiers que tu modifies : un
fichier renvoyé remplace l'ancien intégralement, donc renvoyer un fichier
inchangé n'a aucun effet utile et multiplie les occasions de le casser.
N'abrège jamais.

CORRIGE LA CAUSE, PAS LE SYMPTÔME. Ces réparations sont interdites, parce
qu'elles font passer la porte en cassant le site :
- supprimer l'appel ou la section qui pose problème ;
- désactiver une règle avec eslint-disable ;
- remplacer un type par `any`, ou faire taire une erreur avec `as` ;
- rendre optionnel un champ que le contrat déclare obligatoire.

Si l'erreur vient d'une classe CSS absente, ajoute la règle dans
app/composants.css plutôt que de changer le balisage : le balisage vient du
cahier des charges, la feuille de style non."""

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
