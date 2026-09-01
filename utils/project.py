import json
from pathlib import Path

# Racine des projets, calculée depuis CE fichier (utils/ → racine du dépôt).
# Avant : Path("projects") était relatif au répertoire courant — lancer
# main.py depuis un autre dossier créait les projets au mauvais endroit.
# Analogie C : c'est la différence entre un chemin relatif au CWD du process
# et un chemin construit depuis l'emplacement du binaire.
_PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"


class Project:
    """Représente un projet client branché sur le crew."""

    def __init__(self, name: str):
        self.name = name
        self.root = _PROJECTS_DIR / name

        self.brief_path  = self.root / "brief.md"
        self.config_path = self.root / "config.json"
        self.data_dir    = self.root / "data"
        self.output_dir  = self.root / "output"
        # LE SITE NEXT DE LA V2. Le squelette y est copié, le crew le remplit,
        # `npm run build` en sort un export statique dans site/out/.
        # output_dir reste le dossier LIVRÉ : il reçoit le contenu de site/out/,
        # ce qui laisse diff, restore et l'audit de sécurité fonctionner sans
        # rien changer.
        self.site_dir    = self.root / "site"
        self.temp_dir    = self.root / "temp"
        self.logs_dir    = self.root / "logs"

    def load_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_brief(self) -> str:
        return self.brief_path.read_text(encoding="utf-8")

    def fichiers_requis_manquants(self) -> list:
        """Noms des fichiers indispensables absents (brief.md, config.json).

        Liste vide = le projet est prêt à être traité.
        """
        return [p.name for p in (self.brief_path, self.config_path) if not p.exists()]

    def setup_dirs(self):
        """Crée tous les dossiers du projet s'ils n'existent pas."""
        for d in [self.data_dir, self.output_dir, self.temp_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
