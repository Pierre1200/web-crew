import json
from pathlib import Path


class Project:
    """Représente un projet client branché sur le crew."""

    def __init__(self, name: str):
        self.name = name
        self.root = Path("projects") / name

        self.brief_path  = self.root / "brief.md"
        self.config_path = self.root / "config.json"
        self.data_dir    = self.root / "data"
        self.output_dir  = self.root / "output"
        self.temp_dir    = self.root / "temp"
        self.logs_dir    = self.root / "logs"

    def load_config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_brief(self) -> str:
        return self.brief_path.read_text(encoding="utf-8")

    def setup_dirs(self):
        """Crée tous les dossiers du projet s'ils n'existent pas."""
        for d in [self.data_dir, self.output_dir, self.temp_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
