"""
Fonctions utilitaires de nettoyage des réponses de l'API Claude.
Réutilisables par tous les agents.
"""
import json


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


def parse_json_safe(text: str) -> dict:
    """
    Nettoie puis parse une réponse JSON de Claude.
    Lève une erreur claire si le JSON est invalide (ex: tronqué).
    """
    clean = strip_markdown_fences(text)

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        # Message d'erreur utile pour déboguer
        raise ValueError(
            f"JSON invalide (probablement tronqué). "
            f"Erreur à la position {e.pos}. "
            f"Début du contenu reçu : {clean[:200]}..."
        ) from e


def clean_code_output(text: str) -> str:
    """
    Nettoie du code (HTML, CSS, JS) généré par Claude.
    Enlève les balises markdown et vérifie qu'il reste du contenu.
    """
    clean = strip_markdown_fences(text)

    if not clean:
        raise ValueError("Le code généré est vide après nettoyage")

    return clean