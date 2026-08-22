from __future__ import annotations
import typer
from agents.base_agent import BaseAgent
from utils.project import Project
from utils.cleaners import clean_code_output, extract_css_classes, strip_markdown_fences, compact_json
from utils.embeds import construire_manifeste
from utils.images import preparer_assets, images_lourdes

_FORM_KEYWORDS = {"contact", "newsletter", "reserver", "formulaire", "rdv", "inscription"}

_SEP_HTML = "===HTML==="
_SEP_CSS  = "===CSS==="
_SEP_JS   = "===JS==="


class DesignerAgent(BaseAgent):
    """Génère le HTML, CSS et JS du site en une seule requête cohérente."""

    # Le designer tourne sur le modèle le plus capable, avec l'effort maximal
    # utile au code : c'est ICI que se joue la qualité du rendu livré au client.
    # Une seule requête par site (~1-2 €) contre des heures de retouche à la
    # main : ne PAS dégrader ce réglage pour économiser des tokens.
    MODEL = "claude-opus-5"
    EFFORT = "xhigh"

    def __init__(self, project: Project):
        super().__init__(
            name="designer",
            role="Designer — génère le HTML/CSS/JS du site",
            project=project
        )

    def _valider_html(self, html: str) -> bool:
        return "</html>" in html and "<body" in html

    def _parse_site_response(self, response: str) -> tuple[str, str, str]:
        """Extrait HTML, CSS et JS depuis la réponse multi-sections."""

        def extract(text: str, start_marker: str, end_marker: str | None = None) -> str:
            i = text.find(start_marker)
            if i == -1:
                return ""
            i += len(start_marker)
            if end_marker:
                j = text.find(end_marker, i)
                return text[i:j].strip() if j != -1 else text[i:].strip()
            return text[i:].strip()

        html = extract(response, _SEP_HTML, _SEP_CSS)
        css  = extract(response, _SEP_CSS,  _SEP_JS)
        js   = extract(response, _SEP_JS)

        # Avertir explicitement si un séparateur est absent — évite les fichiers vides silencieux
        if not html:
            self.logger.error(f"Séparateur {_SEP_HTML} absent de la réponse — HTML vide")
            typer.echo(f"   ❌ Séparateur {_SEP_HTML} introuvable dans la réponse du modèle")
        if not css:
            self.logger.error(f"Séparateur {_SEP_CSS} absent de la réponse — CSS vide")
            typer.echo(f"   ❌ Séparateur {_SEP_CSS} introuvable — CSS vide")
        if not js:
            self.logger.error(f"Séparateur {_SEP_JS} absent de la réponse — JS vide")
            typer.echo(f"   ❌ Séparateur {_SEP_JS} introuvable — JS vide")

        # Post-mortem : la réponse fautive est sauvegardée telle quelle,
        # sinon impossible de comprendre ce que le modèle a réellement renvoyé
        if not (html and css and js):
            self.project.logs_dir.mkdir(parents=True, exist_ok=True)
            dump = self.project.logs_dir / "designer_reponse_invalide.txt"
            dump.write_text(response, encoding="utf-8")
            self.logger.error(f"Réponse brute sauvegardée : {dump}")
            typer.echo(f"   💾 Réponse brute sauvegardée pour analyse : {dump}")

        html = strip_markdown_fences(html) if html else ""
        css  = strip_markdown_fences(css)  if css  else ""
        js   = strip_markdown_fences(js)   if js   else ""

        return html, css, js

    def _build_fonts_link(self, fonts: dict) -> str:
        """Construit le <link> Google Fonts depuis les noms de polices."""
        heading = fonts.get("heading", "")
        body    = fonts.get("body", "")
        if not heading and not body:
            return ""
        # Encode les noms pour l'URL (espaces → +)
        parts = []
        if heading:
            slug = heading.replace(" ", "+")
            parts.append(f"family={slug}:ital,wght@0,400;0,600;0,700;1,400")
        if body:
            slug = body.replace(" ", "+")
            parts.append(f"family={slug}:wght@300;400;600")
        query = "&".join(parts) + "&display=swap"
        return (
            '    <link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?{query}">'
        )

    def _regles_formulaires(self) -> tuple[str, str]:
        """Règles de branchement des formulaires, pour les prompts HTML et JS.

        Lit site.formspree_id dans config.json :
        - présent → les formulaires envoient RÉELLEMENT via Formspree
          (action + method + name sur chaque champ, soumission fetch en JS)
        - absent  → le JS doit rester honnête : pas de faux message « envoyé »,
          on invite à contacter directement par email/téléphone.
        """
        formspree_id = self.load_config().get("site", {}).get("formspree_id", "")

        if formspree_id:
            regles_html = f"""
- FORMULAIRES (envoi réel via Formspree) :
  - chaque <form> : action="https://formspree.io/f/{formspree_id}" method="POST"
  - chaque champ de saisie : attribut name explicite (name="nom", name="email", name="message"...)
  - dans chaque <form> : <input type="hidden" name="_subject" value="[Site] <objet selon la section>">"""
            regles_js = """
- Soumission des formulaires : preventDefault + validation, puis envoi RÉEL via
  fetch(form.action, {method: "POST", body: new FormData(form), headers: {Accept: "application/json"}}).
  Si response.ok → message de confirmation (textContent) + form.reset().
  Sinon (erreur HTTP ou exception réseau) → message d'erreur invitant à réessayer
  ou à écrire directement par email. Jamais d'innerHTML."""
        else:
            regles_html = ""
            regles_js = """
- IMPORTANT : aucun service d'envoi n'est configuré pour les formulaires. Le JS
  valide les champs mais NE DOIT PAS afficher de faux message « envoyé » :
  affiche un message honnête invitant à contacter directement par email ou
  téléphone (utilise les coordonnées présentes dans les textes si disponibles)."""
        return regles_html, regles_js

    def _bloc_images(self) -> tuple[str, bool]:
        """Copie les vraies images du client et prépare leur consigne d'intégration.

        Retourne (bloc de prompt, existe_des_images_reelles). Le second sert à
        décider si les images de remplissage restent autorisées : quand le
        client a fourni ses photos, un picsum.photos sur la page est un défaut,
        pas une commodité.
        """
        manifeste = preparer_assets(self.project, self.lire_contexte_ingestion())
        if not manifeste:
            self.logger.info("Aucune image client — images de remplissage utilisées")
            return "", False

        for lourde in images_lourdes(manifeste):
            message = (
                f"{lourde['fichier']} pèse {lourde['poids_ko']} ko — "
                "à compresser avant livraison"
            )
            self.logger.warning(message)
            typer.echo(f"   ⚠️  {message}")

        typer.echo(f"   🖼  {len(manifeste)} image(s) client copiée(s) dans output/assets/")
        self.logger.info(
            f"{len(manifeste)} image(s) réelle(s) : "
            + ", ".join(i["chemin_web"] for i in manifeste)
        )

        return f"""

IMAGES RÉELLES DU CLIENT — {len(manifeste)} fichier(s) déjà copiés dans output/assets/ :
{compact_json(manifeste)}

Règles d'intégration des images (strictes) :
- Utilise ces images EN PRIORITÉ. `src` reprend exactement le champ chemin_web \
(chemin relatif, tel quel) — n'invente aucun autre chemin, aucune autre extension.
- `width` et `height` reprennent les dimensions réelles indiquées. Elles réservent \
la place avant chargement et empêchent la page de sauter sous les yeux du visiteur.
- Respecte l'orientation : une image "portrait" ne se met pas dans un cadre \
panoramique. Cadre selon le champ ratio, et si tu recadres, fais-le avec \
object-fit: cover sans jamais déformer.
- `alt` décrit ce que montre l'image, en t'appuyant sur son nom d'origine et sur \
le champ description quand il existe — jamais « image » ni le nom du fichier brut.
- Place chaque image dans la section indiquée par section_suggeree quand ce champ \
est renseigné.
- Ajoute loading="lazy" sauf sur la première image visible (au-dessus de la ligne \
de flottaison), qui doit charger immédiatement.
- Un logo se place tel quel, sans recadrage ni filtre.""", True

    def _bloc_medias(self) -> str:
        """Prépare la galerie vidéo/audio à intégrer, si le projet en déclare une.

        Les URL d'intégration sont construites mécaniquement (utils/embeds.py) :
        le modèle ne doit RIEN inventer sur ce point, il choisit seulement la
        mise en page de la galerie en fonction du cahier des charges.
        """
        manifeste = construire_manifeste(self.load_config())

        for erreur in manifeste["erreurs"]:
            self.logger.error(f"Média ignoré — {erreur}")
            typer.echo(f"   ⚠️  {erreur}")

        items = manifeste["items"]
        if not items:
            return ""

        fournisseurs = sorted({m["libelle"] for m in items})
        self.logger.info(
            f"{len(items)} média(s) à intégrer — fournisseurs : {', '.join(fournisseurs)}"
        )
        typer.echo(f"   🎬 {len(items)} média(s) — {', '.join(fournisseurs)}")

        titre = manifeste["titre_section"]
        entete = f'Titre de la section médias : « {titre} »\n' if titre else ""

        return f"""

MÉDIAS À INTÉGRER — {len(items)} lecteur(s), hébergés chez plusieurs fournisseurs :
{entete}{compact_json(items)}

Règles d'intégration des médias (strictes) :
- Un <iframe> par média, dont l'attribut src reprend embed_url À L'IDENTIQUE — \
ne raccourcis, ne reconstruis et ne « corriges » aucune de ces URL.
- Sur chaque iframe : loading="lazy", title reprenant le titre du média, \
referrerpolicy="strict-origin-when-cross-origin", et allowfullscreen pour la vidéo.
- Les médias de type "video" gardent leurs proportions via aspect-ratio (valeur \
du champ ratio), largeur 100 %, jamais de hauteur fixe. Les médias de type \
"audio" utilisent la hauteur indiquée par le champ hauteur.
- Affiche le titre de chaque média, et sa description quand elle est fournie.
- La galerie doit rester lisible avec un seul média comme avec dix : la grille \
s'adapte au nombre d'éléments, elle ne suppose pas un compte fixe.
- La disposition de la galerie suit le cahier des charges du client s'il en parle."""

    def _generate_site(self, plan: dict, textes: dict) -> tuple[str, str, str]:
        """Génère HTML + CSS + JS en une seule requête pour garantir la cohérence."""
        style_guide  = plan["style_guide"]
        sections     = list(textes.keys())

        cahier = self.cahier_des_charges(plan)
        # Sans cahier des charges, on suppose une structure de site vitrine
        # classique. Avec, on ne force plus ni nav ni footer : une page
        # d'attente d'un seul écran n'a ni l'un ni l'autre.
        if cahier:
            structure_note = (
                "La structure du <body> est celle du cahier des charges ci-dessus."
            )
        else:
            structure_note = (
                "Structure du <body> : "
                + ", ".join(["nav"] + sections + ["footer"])
            )

        fonts        = style_guide.get("fonts", {})
        font_heading = fonts.get("heading", "")
        font_body    = fonts.get("body", "")
        fonts_link   = self._build_fonts_link(fonts)

        fonts_html_note = (
            f"\nOBLIGATOIRE dans le <head> (avant style.css) :\n{fonts_link}"
            if fonts_link else ""
        )
        fonts_css_note = ""
        if font_heading or font_body:
            fonts_css_note = "\nPolices à utiliser dans les variables :root (choisis le fallback générique adapté) :"
            if font_heading:
                fonts_css_note += f'\n- --font-heading: "{font_heading}", <fallback-adapté>;'
            if font_body:
                fonts_css_note += f'\n- --font-body: "{font_body}", <fallback-adapté>;'

        form_sections = [s for s in sections if any(kw in s.lower() for kw in _FORM_KEYWORDS)]
        # Heuristique par mot-clé : elle SUGGÈRE un formulaire, elle ne l'impose
        # pas. Une section « Contact » peut n'être qu'un lien mailto — c'est le
        # cas de la page d'attente Studio Bougnat, dont le brief l'interdit.
        form_info = (
            f"\n- Sections susceptibles de contenir un formulaire : "
            f"{', '.join(form_sections)}. Si le cahier des charges décrit un simple "
            f"lien (mailto, téléphone) au lieu d'un formulaire, suis le cahier et "
            f"n'écris aucune validation pour cette section."
            if form_sections else ""
        )
        regles_form_html, regles_form_js = self._regles_formulaires()
        bloc_medias = self._bloc_medias()
        bloc_images, a_des_images = self._bloc_images()

        # Quand le client a fourni ses photos, une image de remplissage sur la
        # page livrée est un défaut. Sans photo fournie, elle reste nécessaire.
        # Chaîne simple, pas f-string : les accolades s'écrivent donc en simple.
        # (En f-string il faudrait les doubler, et c'est justement ce qui avait
        # laissé passer un « {{mot-clé}} » littéral dans le prompt.)
        regle_placeholder = (
            "\n- Images de remplissage : à n'utiliser QUE si aucune image réelle "
            "ci-dessus ne convient à un emplacement. Format "
            'src="https://picsum.photos/seed/{mot-clé}/{largeur}/{hauteur}" '
            "avec la classe img-placeholder. Chaque remplissage devra être "
            "remplacé avant livraison : n'en mets pas par confort."
            if a_des_images else
            '\n- Images d\'illustration : src="https://picsum.photos/seed/'
            '{mot-clé}/{largeur}/{hauteur}" avec un mot-clé court tiré du '
            "contexte (minuscules, sans accent) et la classe img-placeholder — "
            "ratio adapté au cadrage voulu (4/3 → 800/600, 16/9 → 800/450)"
        )

        system_prompt = f"""\
Tu es directeur artistique ET intégrateur front-end.
Tu conçois des sites sur mesure : chaque projet a sa propre composition, dictée
par le cahier des charges du client — jamais un gabarit réutilisé tel quel.
Tu génères les 3 fichiers du site en UNE SEULE réponse.

Utilise EXACTEMENT ces séparateurs dans cet ordre, sans aucun texte entre les sections :

{_SEP_HTML}
(code HTML complet de <!DOCTYPE html> à </html>)
{_SEP_CSS}
(code CSS complet)
{_SEP_JS}
(code JavaScript complet)

Règle absolue : aucun texte avant {_SEP_HTML}, aucun texte après le dernier bloc JS.
Aucune explication. Si la génération est interrompue et reprise, continue directement \
le code sans rien résumer."""

        user_message = f"""{cahier}

IDENTITÉ VISUELLE (couleurs et polices décidées pour ce projet) :
{compact_json(style_guide)}

CONTENU RÉDIGÉ À INTÉGRER — une clé par bloc, à placer dans la structure demandée :
{compact_json(textes)}
{bloc_images}{bloc_medias}

{structure_note}

CONTRAINTES TECHNIQUES (non négociables) :
- HTML complet de <!DOCTYPE html> à </html>, sans omission ni troncature
- lang="fr" sur <html>, <meta charset="UTF-8"> et <meta name="viewport" \
content="width=device-width, initial-scale=1.0"> dans le <head>{fonts_html_note}
- <link rel="stylesheet" href="style.css"> dans le <head>
- <script src="main.js"></script> juste avant </body>
- Aucune balise <style>, aucun style inline, aucune librairie externe
- Classes BEM, strictement cohérentes entre le HTML et le CSS
- Accessibilité : un seul <h1>, hiérarchie de titres sans saut, alt décrivant \
chaque image, focus visible au clavier, contraste texte/fond conforme WCAG AA
- Chaque <img> porte width et height (évite le décalage au chargement)\
{regle_placeholder}{regles_form_html}
- CSS : variables dans :root (couleurs, polices, échelle d'espacement), reset \
minimal en tête, mobile-first{fonts_css_note}
- CSS rangé en couches déclarées en TÊTE de feuille : \
@layer reset, base, composants, utilitaires; — puis chaque règle écrite dans \
sa couche. Non négociable : des correctifs automatiques sont ajoutés hors couche \
après coup et doivent pouvoir l'emporter sans surenchère de spécificité.

CSS MODERNE — sers-toi de ces outils là où ils apportent quelque chose, \
pas partout ni pour la démonstration :
- Container queries : un composant réutilisable (carte, encart, média) réagit à \
la largeur de SON conteneur (`container-type: inline-size` sur le parent, \
`@container` sur l'enfant), pas à celle de l'écran. Les media queries restent \
pour la mise en page d'ensemble.
- `:has()` pour les mises en page qui dépendent du contenu réel : \
`.card:has(img)` autrement que sans image, une section qui change quand elle \
contient une galerie, etc.
- Couleur en `oklch()`, déclinaisons via `color-mix(in oklab, …)` : construis un \
système tonal (surfaces, survols, ombres) à partir des 3-4 couleurs du projet, \
au lieu d'empiler des hexadécimaux sans lien entre eux. Les dégradés en oklab \
n'ont pas la zone grisâtre des dégradés RGB.
- `subgrid` sur les grilles de cartes pour que titres, textes et boutons \
s'alignent d'une carte à l'autre — un alignement qui tient est une signature de \
travail soigné.
- `text-wrap: balance` sur les titres et `text-wrap: pretty` sur les paragraphes : \
supprime les lignes veuves et les coupures disgracieuses.
- Propriétés logiques (`margin-inline`, `padding-block`, `inset`) plutôt que \
leurs équivalents physiques.
- Conteneur fluide sans media query : \
`width: min(100% - 2 * var(--marge), 68rem); margin-inline: auto;`
- Tailles et espacements fluides en `clamp()`.
- Révélation au défilement : `animation-timeline: view()` encadré par \
`@supports (animation-timeline: view())`, avec repli JavaScript sinon.

PRINCIPES DE COMPOSITION — c'est ce qui sépare un site travaillé d'un gabarit :
- Rythme vertical VARIABLE : toutes les sections n'ont pas la même respiration. \
Alterne blocs denses et blocs aérés plutôt qu'un padding uniforme partout.
- Une seule chose domine par écran. Trois éléments de poids égal qui se disputent \
l'attention, c'est une page morte.
- Échelle d'espacement à sauts francs (8 / 16 / 24 / 40 / 64 / 96 / 160), pas une \
suite de multiples de 1rem qui aplatit tout.
- Largeur de lecture limitée (~68 caractères) sur les paragraphes. Les titres \
peuvent dépasser, le corps de texte jamais.
- Composition assumée : si la maquette impose une asymétrie, ne la recentre pas.
- Matière et profondeur : bordures fines, tons superposés, légère texture. \
Évite l'ombre portée générique posée sur chaque carte.
- Typographie soignée : interlettrage resserré sur les grands titres, interligne \
généreux sur le corps, contraste de graisses assumé.
- Mouvement SÉLECTIF : deux ou trois éléments animés qui le méritent, jamais \
toutes les sections. Toujours neutralisé sous @media (prefers-reduced-motion: reduce).

À ÉVITER — signature immédiate d'un site généré à la chaîne :
hero 100vh systématique, fade-in sur chaque section, trois cartes à ombre \
identique alignées, dégradé violet, emoji en guise d'icône, texte de remplissage, \
media query globale pour adapter un composant (c'est le rôle des container \
queries), empilement d'hexadécimaux sans système tonal, `!important`.

CONVENTIONS PAR DÉFAUT — à appliquer UNIQUEMENT si le cahier des charges ne dit \
rien de contraire sur le point concerné :
- Navigation sticky avec état .scrolled au défilement (si le site a une navigation)
- Grille de cartes fluide sans palier arbitraire : \
`repeat(auto-fit, minmax(min(100%, 18rem), 1fr))`
- Boutons .btn / .btn--primary / .btn--secondary, cartes .card
- Alternance de surfaces obtenue par color-mix sur la couleur de fond, plutôt \
que par deux couleurs sans rapport

JAVASCRIPT (vanilla, aucune librairie) — uniquement ce que la page utilise \
réellement, pas de code mort. Tout ce que le CSS sait faire seul reste au CSS :
- Révélation au défilement : seulement en repli, si tu n'as pas pu utiliser \
`animation-timeline: view()` — via IntersectionObserver (classe .visible), sur \
les seuls éléments choisis
- Navigation : classe .scrolled au défilement et menu burger mobile (classe .open) \
— seulement s'il y a une navigation
- Défilement doux : `scroll-behavior: smooth` en CSS suffit, pas de JS pour ça\
{form_info}{regles_form_js}"""

        typer.echo("   → Génération HTML + CSS + JS en une seule requête...")
        response = self.call_claude_continuable(system_prompt, user_message, max_tokens=64000)
        return self._parse_site_response(response)

    def run(self, context: dict) -> dict:
        typer.echo("🎨 Designer : génération du site...")

        plan   = self.read_json("temp/plan.json")
        textes = self.read_json("temp/textes.json")

        html, css, js = self._generate_site(plan, textes)

        output_dir = self.project.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "assets").mkdir(exist_ok=True)

        # Même garde pour les 3 fichiers : on n'écrase JAMAIS une version
        # existante par du contenu vide ou invalide (avant, seul index.html
        # était protégé — un séparateur manquant vidait style.css/main.js).
        ecrits = []

        if css:
            (output_dir / "style.css").write_text(css, encoding="utf-8")
            ecrits.append("style.css")
        else:
            self.logger.error("CSS vide après génération — style.css non écrasé")
            typer.echo("   ❌ CSS vide — style.css existant conservé")

        if js:
            (output_dir / "main.js").write_text(js, encoding="utf-8")
            ecrits.append("main.js")
        else:
            self.logger.error("JS vide après génération — main.js non écrasé")
            typer.echo("   ❌ JS vide — main.js existant conservé")

        if self._valider_html(html):
            (output_dir / "index.html").write_text(html, encoding="utf-8")
            ecrits.append("index.html")
        else:
            self.logger.error("HTML invalide après génération — index.html non écrasé")
            typer.echo("   ❌ HTML incomplet — index.html existant conservé")

        if ecrits:
            typer.echo(f"✅ Site généré → {output_dir}/")
            for f in ecrits:
                typer.echo(f"   • {f}")

        return {
            "output_dir": str(output_dir),
            "fichiers": ecrits,
        }

    def regenerate_html(self) -> bool:
        """Re-génère index.html depuis le CSS existant sur disque."""
        textes      = self.read_json("temp/textes.json")
        css         = (self.project.output_dir / "style.css").read_text(encoding="utf-8")
        sections    = list(textes.keys())
        classes_str = ", ".join(extract_css_classes(css))

        # Récupérer le plan pour réinjecter les fonts ET le cahier des charges :
        # sans lui, une régénération de secours reconstruirait une page au
        # gabarit générique et effacerait la maquette du client.
        try:
            plan  = self.read_json("temp/plan.json")
            fonts = plan.get("style_guide", {}).get("fonts", {})
        except Exception:
            plan, fonts = {}, {}

        cahier = self.cahier_des_charges(plan) if plan else ""
        structure_note = (
            "La structure du <body> est celle du cahier des charges ci-dessus."
            if cahier
            else "Structure du <body> : " + ", ".join(["nav"] + sections + ["footer"])
        )

        fonts_link = self._build_fonts_link(fonts)
        fonts_note = (
            f"\nOBLIGATOIRE dans le <head> (avant style.css) :\n{fonts_link}"
            if fonts_link else ""
        )

        system_prompt = """\
Tu es un développeur web senior.
Tu génères UNIQUEMENT la structure HTML5 complète.
Commence directement par <!DOCTYPE html> et termine obligatoirement par </body></html>."""

        regles_form_html, _ = self._regles_formulaires()
        bloc_medias = self._bloc_medias()
        bloc_images, a_des_images = self._bloc_images()
        regle_placeholder = (
            "Images de remplissage : uniquement si aucune image réelle ci-dessus "
            "ne convient."
            if a_des_images else
            'Images : src="https://picsum.photos/seed/{mot-clé}/{largeur}/{hauteur}" '
            "avec un mot-clé tiré du contexte de l'image (minuscules, sans accent)."
        )

        user_message = f"""{cahier}

Régénère l'index.html complet de ce site, en réutilisant le CSS déjà produit.

Classes CSS disponibles — utilise UNIQUEMENT celles-ci, n'en invente aucune :
{classes_str}
{bloc_images}{bloc_medias}

{structure_note}

OBLIGATOIRE dans le <head> :
- <meta charset="UTF-8">
- <meta name="viewport" content="width=device-width, initial-scale=1.0">{fonts_note}
- <link rel="stylesheet" href="style.css">
OBLIGATOIRE : <script src="main.js"></script> avant </body>
INTERDIT : balise <style>, CSS inline
Accessibilité : un seul <h1>, alt sur chaque image, width et height sur chaque <img>
{regle_placeholder}{regles_form_html}

Textes à intégrer :
{compact_json(textes)}"""

        html = clean_code_output(
            self.call_claude_continuable(system_prompt, user_message, max_tokens=32000)
        )
        if self._valider_html(html):
            (self.project.output_dir / "index.html").write_text(html, encoding="utf-8")
            self.logger.info("index.html régénéré avec succès")
            return True
        self.logger.error("HTML toujours invalide après regenerate_html")
        return False

    def regenerate_js(self) -> bool:
        """Re-génère main.js depuis le HTML existant sur disque.

        Le JS cible des ids et classes précis du DOM (getElementById...) :
        on lui passe donc le HTML actuel pour qu'il vise les bons éléments.
        """
        html = (self.project.output_dir / "index.html").read_text(encoding="utf-8")

        textes = self.read_json("temp/textes.json")
        sections = list(textes.keys())
        form_sections = [s for s in sections if any(kw in s.lower() for kw in _FORM_KEYWORDS)]
        form_info = (
            f"\n- Validation des formulaires des sections : {', '.join(form_sections)} "
            "(champs requis, format email, message d'erreur/succès via textContent)"
            if form_sections else ""
        )
        _, regles_form_js = self._regles_formulaires()

        system_prompt = """\
Tu es un développeur JavaScript senior.
Tu génères UNIQUEMENT du JavaScript vanilla (aucune librairie).
Réponds sans balise markdown, juste le code JS complet."""

        user_message = f"""Génère le main.js complet pour ce site vitrine.

Fonctionnalités requises :
- IntersectionObserver → ajoute la classe .visible au scroll (threshold 0.15)
- Nav sticky : classe .scrolled après 80px de scroll
- Smooth scroll sur les liens d'ancre
- Menu burger mobile (toggle classe .open sur nav){form_info}{regles_form_js}

Cible UNIQUEMENT les ids et classes présents dans ce HTML :
{html}"""

        js = clean_code_output(
            self.call_claude_continuable(system_prompt, user_message, max_tokens=16000)
        )
        if js and js.count("{") == js.count("}"):
            (self.project.output_dir / "main.js").write_text(js, encoding="utf-8")
            self.logger.info("main.js régénéré avec succès")
            return True
        self.logger.error("JS toujours déséquilibré après regenerate_js")
        return False

    def appliquer_correctifs_css(self, problemes: list) -> int:
        """Applique les corrections CSS proposées par la critique visuelle.

        ZÉRO TOKEN : la critique a déjà rédigé les règles, on ne redemande rien
        au modèle.

        Comment un correctif l'emporte, sans `!important` : la feuille générée
        range tout dans des couches (`@layer reset, base, composants,
        utilitaires`), et **une règle HORS couche bat toujours une règle dans une
        couche, quelle que soit sa spécificité**. Les correctifs sont donc
        ajoutés hors couche, en fin de fichier.

        C'est ce qui rend le mécanisme fiable : avec un simple ajout en fin de
        feuille, un correctif `.hero{...}` ne battrait PAS un `.section .hero{...}`
        existant (spécificité supérieure). Si la feuille n'utilise aucune couche,
        on retombe sur l'ordre d'écriture — le comportement d'avant, sans
        régression.

        Retourne le nombre de correctifs appliqués.
        """
        correctifs = [p for p in problemes if (p.get("correction_css") or "").strip()]
        if not correctifs:
            return 0

        css_path = self.project.output_dir / "style.css"
        if not css_path.exists():
            self.logger.error("style.css absent — correctifs visuels non appliqués")
            return 0

        morceaux = []
        for p in correctifs:
            constat = (p.get("constat") or "").replace("*/", "").strip()
            morceaux.append(
                f"/* [{p.get('gravite', '?')}] {p.get('zone', '?')} "
                f"({p.get('format', 'tous')}) — {constat[:140]} */"
            )
            morceaux.append(strip_markdown_fences(p["correction_css"]).strip())

        css_existant = css_path.read_text(encoding="utf-8")
        utilise_layers = "@layer" in css_existant

        entete = (
            "\n\n/* ===================================================== */\n"
            "/* Correctifs issus de la critique visuelle automatique     */\n"
        )
        entete += (
            "/* Hors couche : l'emportent sur toutes les couches.        */\n"
            if utilise_layers else
            "/* Feuille sans couches : l'emport dépend de la spécificité. */\n"
        )
        entete += "/* ===================================================== */\n"

        css_path.write_text(css_existant + entete + "\n".join(morceaux) + "\n", encoding="utf-8")

        if not utilise_layers:
            self.logger.warning(
                "style.css n'utilise pas @layer — un correctif peut être battu "
                "par une règle existante plus spécifique"
            )

        self.logger.info(f"{len(correctifs)} correctif(s) CSS visuel(s) appliqué(s)")
        return len(correctifs)

    def fix(self, classes_manquantes: list[str], css: str, html: str) -> str:
        """Génère UNIQUEMENT les règles CSS pour les classes manquantes.

        Reçoit directement les noms de classes (extraits par main.py depuis
        les problèmes structurés du validateur) — plus aucun parsing de
        message humain ici.
        """
        typer.echo("   🔧 Designer : génération des règles manquantes...")

        if not classes_manquantes:
            typer.echo("   ℹ️  Aucun problème de classe à corriger")
            return ""

        system_prompt = """\
Tu es un développeur CSS expert.
Tu génères UNIQUEMENT les nouvelles règles CSS pour des classes manquantes.
Ne réécris PAS le CSS existant.
Réponds sans balise markdown, juste les règles CSS."""

        noms_classes = classes_manquantes

        plan = self.read_json("temp/plan.json")
        couleurs = plan.get("style_guide", {}).get("couleurs", {})
        if isinstance(couleurs, dict):
            couleurs_str = ", ".join(f"{k}: {v}" for k, v in couleurs.items())
        elif isinstance(couleurs, list):
            couleurs_str = ", ".join(couleurs)
        else:
            couleurs_str = "les couleurs définies dans le projet"

        user_message = f"""CSS existant (ne pas réécrire) :
{css}

HTML utilisant les classes manquantes :
{html}

Classes absentes du CSS à styler :
{', '.join(noms_classes)}

Génère UNIQUEMENT les règles CSS pour ces {len(noms_classes)} classes.
Respecte les conventions (BEM, variables CSS) du CSS existant.
Palette du projet : {couleurs_str}."""

        response = self.call_claude_continuable(system_prompt, user_message, max_tokens=8000)
        return clean_code_output(response)
