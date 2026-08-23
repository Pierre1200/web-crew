"""
Fonctions utilitaires de nettoyage et de normalisation de texte.
Réutilisables par tous les agents.
"""
import json
import re
import unicodedata

# Les ligatures ne se décomposent pas en NFKD : sans ce passage préalable,
# « œuvre » perdrait son « o » et deviendrait « uvre ».
_LIGATURES = (("œ", "oe"), ("Œ", "OE"), ("æ", "ae"), ("Æ", "AE"), ("ß", "ss"))


def slugifier(texte: str) -> str:
    """Transforme un texte en identifiant utilisable dans une URL ou un nom de
    fichier : « D'où vient le nom de l'atelier ? » → « d-ou-vient-le-nom-de-l-atelier ».

    Point d'entrée UNIQUE de la normalisation : les noms de fichiers images et
    les adresses de pages passent par ici. Dupliquer cette logique, c'est
    garantir qu'un correctif appliqué d'un côté manquera de l'autre.
    """
    for ligature, remplacement in _LIGATURES:
        texte = texte.replace(ligature, remplacement)
    texte = unicodedata.normalize("NFKD", texte)
    texte = texte.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", texte).strip("-").lower()


def compact_json(data) -> str:
    """Sérialise en JSON compact (sans indentation ni espaces superflus).

    Pour les données injectées DANS les prompts : ~10-20 % de tokens d'entrée
    en moins vs indent=2, sans perte pour le modèle qui parse aussi bien.
    Ne pas utiliser pour les fichiers écrits sur disque (lisibilité humaine).
    """
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def strip_markdown_fences(text: str) -> str:
    """
    Enlève les balises markdown ``` que Claude ajoute parfois.
    Équivalent à un 'nettoyage' avant parsing.
    """
    clean = text.strip()

    # Enlève la première ligne si elle commence par ```
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]

    # Enlève les ``` de fin
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]

    return clean.strip()


_FERMETURE = {"{": "}", "[": "]"}


def diagnostiquer_json(texte: str) -> str:
    """Explique POURQUOI un JSON est invalide, au lieu de le supposer tronqué.

    L'ancien message disait « probablement tronqué » dans tous les cas. Lors du
    premier run réel, il s'est trompé une fois sur deux et a fait perdre un
    quart d'heure de diagnostic : la vraie cause était une accolade manquante
    au milieu du document, le contenu étant complet.

    On parcourt le texte en tenant une pile des conteneurs ouverts, en
    respectant les chaînes et les échappements. À la fin, la pile dit tout :
      - pile vide et texte fini dans une chaîne : coupure en plein milieu
      - pile non vide : il manque des fermetures, et on sait lesquelles et où
      - pile vide : le problème est ailleurs (virgule, guillemet, clé en double)
    """
    pile = []                    # [(caractère ouvrant, numéro de ligne)]
    ligne = 1
    dans_chaine = False
    echappe = False

    for caractere in texte:
        if caractere == "\n":
            ligne += 1

        if dans_chaine:
            # Un antislash neutralise le caractère suivant, y compris un
            # guillemet : sans ça, "il a dit \"oui\"" fermerait trop tôt.
            if echappe:
                echappe = False
            elif caractere == "\\":
                echappe = True
            elif caractere == '"':
                dans_chaine = False
            continue

        if caractere == '"':
            dans_chaine = True
        elif caractere in "{[":
            pile.append((caractere, ligne))
        elif caractere in "}]" and pile:
            pile.pop()

    if dans_chaine:
        return (
            f"la réponse s'arrête au milieu d'une chaîne de caractères "
            f"(ligne {ligne}) : c'est une vraie troncature, le modèle a été "
            f"coupé par sa limite de tokens. Relève max_tokens pour cet agent."
        )

    if pile:
        ouvrant, ligne_ouverture = pile[-1]
        manquants = "".join(_FERMETURE[c] for c, _ in reversed(pile))
        nature = "objet" if ouvrant == "{" else "tableau"
        return (
            f"{len(pile)} conteneur(s) jamais refermé(s) : il manque « {manquants} ». "
            f"Le plus profond est un {nature} ouvert ligne {ligne_ouverture}. "
            f"Si le contenu semble complet, c'est une fermeture oubliée en "
            f"cours de route, pas une troncature : ajoute « {manquants} » au "
            f"bon endroit et le contenu est récupérable."
        )

    return (
        "tous les conteneurs sont refermés : le contenu n'est pas tronqué. "
        "Cherche plutôt une virgule en trop ou manquante, un guillemet non "
        "échappé, ou une valeur mal formée."
    )


def parse_json_safe(text: str) -> dict:
    """Nettoie puis parse une réponse JSON de Claude.

    En cas d'échec, le message dit précisément ce qui cloche : c'est ce qui
    permet de réparer une réponse à la main plutôt que de repayer l'appel.
    """
    clean = strip_markdown_fences(text)

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        ligne, colonne = e.lineno, e.colno
        raise ValueError(
            f"JSON invalide : {diagnostiquer_json(clean)}\n"
            f"   Le parseur a lâché ligne {ligne}, colonne {colonne} "
            f"(caractère {e.pos} sur {len(clean)}) : {e.msg}."
        ) from e


def extract_css_classes(css: str) -> list:
    """Extrait les noms de classes uniques d'un CSS (ex: 'navbar__link', 'btn--primary').

    Remplace le passage du CSS complet dans le prompt HTML : ~250 tokens au lieu de ~3500.
    Le modèle garde la cohérence des classes sans consommer le budget d'output.
    """
    classes = re.findall(r'\.([a-zA-Z][\w-]*)', css)
    return sorted(set(classes))


def clean_code_output(text: str) -> str:
    """
    Nettoie du code (HTML, CSS, JS) généré par Claude.
    Enlève les balises markdown et vérifie qu'il reste du contenu.
    """
    clean = strip_markdown_fences(text)

    if not clean:
        raise ValueError("Le code généré est vide après nettoyage")

    return clean