from __future__ import annotations
import re
import typer
from pathlib import Path
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import extract_css_classes
from utils.embeds import construire_manifeste
from utils.images import EXTENSIONS_IMAGES
from utils.pages import collections_declarees

# Classes ajoutées dynamiquement par main.js — absentes du CSS statique, c'est normal
_JS_DYNAMIC_CLASSES = {"visible", "scrolled", "open", "active", "loaded", "is-open", "is-active"}

# Types de problèmes que la boucle de correction (generate-safe) sait réparer.
# Tout autre type d'erreur arrête la boucle avec un message explicite, au lieu
# de tourner à vide jusqu'à max_tentatives.
FIXABLE_TYPES = {
    "html_tronque", "html_incomplet", "js_tronque", "classe_absente",
    "media_manquant",
}


class ValidatorAgent(BaseAgent):
    """Inspecte le site généré et détecte les problèmes, sans appeler l'IA.

    ⚠️ CET AGENT NE CONTACTE JAMAIS L'API. Il hérite bien de MODEL et EFFORT de
    BaseAgent, mais ces réglages ne servent à rien ici : aucun appel n'est émis,
    et la clé API n'est même pas requise pour le faire tourner (le client
    Anthropic est créé paresseusement, au premier appel réel). Si tu ajoutes un
    jour un appel dans cette classe, choisis son modèle explicitement plutôt que
    d'hériter d'Opus 5 sans t'en apercevoir.

    Chaque problème est un dict structuré, jamais une simple phrase :
        {"type": str, "niveau": "erreur"|"warning", "message": str, ...extras}

    - "erreur"  : le site est cassé ou incomplet → invalide le run
    - "warning" : point d'attention, le site reste livrable

    Le champ "type" sert à l'aiguillage de la correction automatique.
    Avant, main.py et designer.fix() faisaient du pattern-matching sur les
    messages français ("tronqué" in p...) : reformuler un message cassait la
    correction en silence. Avec un type, le contrat est explicite.
    """

    def __init__(self, project: Project):
        super().__init__(
            name="validator",
            role="Validateur, contrôle qualité du site généré",
            project=project
        )
        self.problemes = []

    def _pb(self, type_: str, niveau: str, message: str, **extras):
        """Enregistre un problème structuré (type + niveau + message + extras)."""
        probleme = {"type": type_, "niveau": niveau, "message": message}
        probleme.update(extras)
        self.problemes.append(probleme)

    def _lire(self, fichier: str) -> str:
        """Lit un fichier du dossier de sortie du projet."""
        path = self.project.output_dir / fichier
        if not path.exists():
            self._pb("fichier_manquant", "erreur",
                     f"Fichier manquant : {fichier}", fichier=fichier)
            return ""
        return path.read_text(encoding="utf-8")

    def check_html_complet(self, html: str, sections_keywords: list = None):
        """Vérifie que le HTML n'est pas tronqué."""
        if not html:
            return
        if "</html>" not in html:
            self._pb("html_tronque", "erreur",
                     "HTML tronqué : balise </html> manquante")
        if "<body" not in html:
            self._pb("html_incomplet", "erreur",
                     "HTML incomplet : pas de <body>")
        # Heuristique faible (simple recherche du nom dans le HTML) → warning,
        # pas erreur : un faux positif ne doit pas invalider le site.
        for section in (sections_keywords or []):
            if section not in html.lower():
                self._pb("section_manquante", "warning",
                         f"Section possiblement manquante : {section}",
                         section=section)

    def check_classes_coherentes(self, html: str, css: str):
        """Pour chaque classe du HTML, vérifie qu'elle existe dans le CSS."""
        if not html or not css:
            return

        classes_html = set()
        for match in re.findall(r'class="([^"]*)"', html):
            for classe in match.split():
                classes_html.add(classe)

        classes_css = set(extract_css_classes(css))

        for classe in sorted(classes_html):
            if classe not in classes_css and classe not in _JS_DYNAMIC_CLASSES:
                self._pb("classe_absente", "erreur",
                         f"Classe '{classe}' utilisée dans le HTML mais absente du CSS",
                         classe=classe)

    def check_liens_fichiers(self, html: str):
        """Vérifie que le HTML lie bien le CSS et le JS."""
        if not html:
            return
        if 'href="style.css"' not in html:
            self._pb("lien_css_manquant", "erreur",
                     "Lien vers style.css manquant dans le HTML")
        if 'src="main.js"' not in html:
            self._pb("lien_js_manquant", "erreur",
                     "Lien vers main.js manquant dans le HTML")

    def check_js_complet(self, js: str):
        """Détecte un JS tronqué en comptant les accolades."""
        if not js:
            return
        ouvrantes = js.count("{")
        fermantes = js.count("}")
        if ouvrantes != fermantes:
            self._pb("js_tronque", "erreur",
                     f"JS possiblement tronqué : {ouvrantes} '{{' mais {fermantes} '}}'")

    def check_css_complet(self, css: str):
        """Détecte un CSS tronqué en comptant les accolades (même principe que le JS)."""
        if not css:
            return
        ouvrantes = css.count("{")
        fermantes = css.count("}")
        if ouvrantes != fermantes:
            self._pb("css_tronque", "erreur",
                     f"CSS possiblement tronqué : {ouvrantes} '{{' mais {fermantes} '}}'")

    def check_css_moderne(self, css: str):
        """Contrôle les exigences CSS que le prompt du designer impose.

        Trois points objectifs, tous non bloquants, le site reste livrable,
        mais chacun signale une feuille moins solide qu'elle ne devrait l'être.
        """
        if not css:
            return

        # Sans couches, les correctifs de la critique visuelle sont ajoutés hors
        # couche mais ne l'emportent qu'à spécificité égale : la correction
        # automatique devient un coup de dés.
        if "@layer" not in css:
            self._pb(
                "cascade_sans_layer", "warning",
                "CSS sans @layer, les correctifs visuels automatiques risquent "
                "d'être battus par des règles existantes plus spécifiques",
            )

        # Accessibilité : certains visiteurs désactivent les animations au
        # niveau du système, il faut que le site en tienne compte.
        if "prefers-reduced-motion" not in css:
            self._pb(
                "motion_non_geree", "warning",
                "Aucun @media (prefers-reduced-motion), les animations "
                "s'imposeront aux visiteurs qui les ont désactivées",
            )

        # !important est le symptôme d'une cascade qu'on ne maîtrise plus ;
        # quelques-uns sont normaux (surcharges tierces), une dizaine non.
        nb_important = css.count("!important")
        if nb_important > 8:
            self._pb(
                "cascade_forcee", "warning",
                f"{nb_important} !important dans le CSS, cascade mal maîtrisée, "
                "les correctifs ultérieurs seront difficiles à appliquer",
            )

    def check_viewport(self, html: str):
        """Vérifie la présence de la meta viewport, critique pour le responsive."""
        if html and '<meta name="viewport"' not in html:
            self._pb("viewport_manquant", "erreur",
                     "Meta viewport manquante, site non responsive sur mobile")

    def check_h1(self, html: str):
        """Vérifie la présence d'au moins un <h1> pour le SEO."""
        if html and '<h1' not in html.lower():
            self._pb("h1_manquant", "warning",
                     "Aucun <h1> trouvé, structure SEO incorrecte")

    def check_web_fonts(self, html: str, css: str):
        """Vérifie qu'une police web est chargée (Google Fonts ou @import CSS)."""
        if not html:
            return
        has_gfonts = 'fonts.googleapis.com' in html
        has_import = bool(css) and '@import' in css and 'font' in css.lower()
        if not has_gfonts and not has_import:
            self._pb("fonts_manquantes", "warning",
                     "Aucune police web chargée, le site utilisera les polices système")

    def check_formulaires(self, html: str):
        """Détecte les formulaires factices : un <form> sans attribut action
        n'envoie rien nulle part, le visiteur croit avoir écrit au client.
        """
        if not html:
            return
        for form_tag in re.findall(r'<form[^>]*>', html):
            if 'action=' not in form_tag:
                self._pb("formulaire_sans_action", "warning",
                         "Formulaire sans attribut action, aucun envoi réel "
                         "(renseigne site.formspree_id dans config.json)")

    def check_medias(self, html: str):
        """Vérifie que chaque média déclaré dans config.json est bien intégré.

        Un lecteur oublié, c'est une vidéo que le client ne verra pas sur son
        site : on compare l'URL d'intégration attendue au HTML réellement livré.
        """
        if not html:
            return
        try:
            manifeste = construire_manifeste(self.load_config())
        except (OSError, ValueError) as e:
            self.logger.info(f"config.json illisible, médias non vérifiés : {e}")
            return

        for erreur in manifeste["erreurs"]:
            self._pb("media_invalide", "erreur", erreur)

        for media in manifeste["items"]:
            if media["embed_url"] not in html:
                self._pb(
                    "media_manquant", "erreur",
                    f"Média « {media['titre']} » ({media['libelle']}) absent du HTML",
                    media=media["titre"],
                )

    def check_images(self, html: str, css: str):
        """Contrôle les vraies images du client : liens cassés, oubliées, remplissage.

        Inspection pure, le validateur ne copie ni ne modifie rien, il compare
        ce que le HTML référence à ce qui existe réellement sur le disque.
        """
        if not html:
            return

        output = self.project.output_dir
        dossier_assets = output / "assets"

        # 1. Tous les chemins locaux référencés (src du HTML + url() du CSS)
        references = set(re.findall(r'src="([^"]+)"', html))
        references |= set(re.findall(r'url\(\s*["\']?([^"\')]+)', css or ""))
        locales = {
            r.split("?")[0].split("#")[0]
            for r in references
            if r and not r.startswith(("http://", "https://", "data:", "//"))
        }

        # 2. Un lien local qui ne pointe sur rien : image ou script manquant,
        #    donc visuellement cassé chez le client. Couvre src d'<img> ET de
        #    <script>, d'où un nom de problème volontairement générique.
        for reference in sorted(locales):
            if not (output / reference).exists():
                self._pb(
                    "ressource_cassee", "erreur",
                    f"Ressource introuvable : {reference} est référencée dans "
                    "le site mais le fichier n'existe pas dans output/",
                    fichier=reference,
                )

        # 3. Une image fournie par le client mais jamais affichée
        if dossier_assets.is_dir():
            fichiers_utilises = {Path(r).name for r in locales}
            for fichier in sorted(dossier_assets.iterdir()):
                if (fichier.is_file()
                        and fichier.suffix.lower() in EXTENSIONS_IMAGES
                        and fichier.name not in fichiers_utilises):
                    self._pb(
                        "image_inutilisee", "warning",
                        f"Image client jamais affichée : {fichier.name}",
                        fichier=fichier.name,
                    )

        # 4. Du remplissage alors que le client a fourni ses propres visuels
        nb_placeholders = html.count("picsum.photos")
        a_des_images_reelles = dossier_assets.is_dir() and any(
            f.suffix.lower() in EXTENSIONS_IMAGES
            for f in dossier_assets.iterdir() if f.is_file()
        )
        if nb_placeholders and a_des_images_reelles:
            self._pb(
                "placeholder_en_production", "warning",
                f"{nb_placeholders} image(s) de remplissage alors que le client "
                "a fourni ses propres visuels, à remplacer avant livraison",
            )

    def check_pages_collections(self):
        """Contrôle les pages secondaires (blog, réalisations…).

        Le validateur ne regardait qu'index.html. Une page de collection dont
        le lien vers `../style.css` serait cassé s'afficherait sans aucun style
        chez le client, sans que rien ne le signale.
        """
        output = self.project.output_dir
        if not output.is_dir():
            return

        secondaires = [
            p for p in sorted(output.rglob("*.html"))
            if p != output / "index.html"
        ]
        if not secondaires:
            return

        self.logger.info(f"{len(secondaires)} page(s) secondaire(s) contrôlée(s)")

        for page in secondaires:
            nom = page.relative_to(output).as_posix()
            try:
                html = page.read_text(encoding="utf-8")
            except OSError:
                continue

            # Les chemins sont relatifs à la page, pas à la racine du site :
            # c'est précisément là que se glissent les erreurs de préfixe.
            for reference in set(re.findall(r'(?:src|href)="([^"]+)"', html)):
                propre = reference.split("?")[0].split("#")[0]
                if not propre or propre.startswith(("http://", "https://", "data:",
                                                    "//", "mailto:", "tel:", "#")):
                    continue
                if not (page.parent / propre).exists():
                    self._pb(
                        "lien_page_casse", "erreur",
                        f"{nom} : lien cassé vers « {propre} »",
                        page=nom, cible=propre,
                    )

            if "<h1" not in html.lower():
                self._pb("h1_manquant", "warning",
                         f"{nom} : aucun <h1>", page=nom)
            if '<meta name="viewport"' not in html:
                self._pb("viewport_manquant", "erreur",
                         f"{nom} : meta viewport manquante", page=nom)

    def check_collections_vides(self):
        """Signale une collection déclarée dont aucun contenu n'a été publié."""
        try:
            collections = collections_declarees(self.load_config())
        except (OSError, ValueError):
            return

        for collection in collections:
            dossier = self.project.output_dir / collection["url"]
            if not (dossier / "index.html").exists():
                self._pb(
                    "collection_vide", "warning",
                    f"Collection « {collection['titre']} » déclarée mais non "
                    f"générée, dépose des fichiers .txt dans "
                    f"data/{collection['source']}/ puis lance `pages`",
                    collection=collection["id"],
                )

    def check_textes_complets(self):
        """Vérifie que chaque section de textes.json contient bien du contenu.

        Premier check de CONTENU (et non de structure) : une section vide
        signifie que le copywriter a mal travaillé, même si le HTML est valide.
        """
        try:
            textes = self.read_json("temp/textes.json")
        except Exception as e:
            self.logger.info(f"textes.json illisible, check de contenu sauté : {e}")
            return
        for section, contenu in textes.items():
            vide = not contenu or (isinstance(contenu, str) and not contenu.strip())
            if vide:
                self._pb("section_vide", "warning",
                         f"Section '{section}' vide dans textes.json",
                         section=section)

    def run(self, context: dict) -> dict:
        typer.echo("✅ Validateur : inspection du site...")
        self.problemes = []

        sections_keywords = []
        try:
            textes = self.read_json("temp/textes.json")
            sections_keywords = [k.replace("_", "-") for k in textes.keys()]
        except Exception as e:
            self.logger.info(f"textes.json illisible, sections non vérifiées : {e}")

        html = self._lire("index.html")
        css = self._lire("style.css")
        js = self._lire("main.js")

        self.check_html_complet(html, sections_keywords)
        self.check_viewport(html)
        self.check_h1(html)
        self.check_web_fonts(html, css)
        self.check_classes_coherentes(html, css)
        self.check_liens_fichiers(html)
        self.check_css_complet(css)
        self.check_css_moderne(css)
        self.check_js_complet(js)
        self.check_formulaires(html)
        self.check_images(html, css)
        self.check_medias(html)
        self.check_pages_collections()
        self.check_collections_vides()
        self.check_textes_complets()

        erreurs  = [p for p in self.problemes if p["niveau"] == "erreur"]
        warnings = [p for p in self.problemes if p["niveau"] == "warning"]

        if not self.problemes:
            typer.echo("✅ Aucun problème détecté, le site est valide !")
        else:
            typer.echo(f"⚠️  {len(erreurs)} erreur(s), {len(warnings)} warning(s) :")
            for p in self.problemes:
                icone = "❌" if p["niveau"] == "erreur" else "⚠️ "
                typer.echo(f"   {icone} {p['message']}")

        for p in self.problemes:
            self.logger.info(f"[{p['niveau']}] {p['type']}, {p['message']}")

        # Seules les ERREURS invalident le site : les warnings sont des points
        # d'attention, pas des blocages (avant, tout invalidait, et la boucle
        # de correction tournait à vide sur des problèmes incorrigeables).
        return {
            "valide": len(erreurs) == 0,
            "problemes": self.problemes,
            "erreurs": erreurs,
            "warnings": warnings,
        }
