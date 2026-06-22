import anthropic
import os
import json
import logging
from utils.project import Project


class BaseAgent:
    """Classe mère dont héritent tous les agents."""

    def __init__(self, name: str, role: str, project: Project):
        self.name = name
        self.role = role
        self.project = project
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.logger = self._setup_logger()

    def _setup_logger(self):
        """Configure les logs de l'agent dans le dossier du projet."""
        logger = logging.getLogger(f"{self.project.name}.{self.name}")
        logger.setLevel(logging.INFO)

        self.project.logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.project.logs_dir / f"{self.name}.log"
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        ))
        logger.addHandler(handler)
        return logger

    def read_json(self, filepath: str) -> dict:
        """Lit un fichier JSON relatif à la racine du projet."""
        path = self.project.root / filepath
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_text(self, filepath: str) -> str:
        """Lit un fichier texte relatif à la racine du projet."""
        path = self.project.root / filepath
        return path.read_text(encoding="utf-8")

    def write_json(self, filepath: str, data: dict):
        """Écrit un fichier JSON relatif à la racine du projet."""
        path = self.project.root / filepath
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Fichier écrit : {path}")

    def call_claude(self, system_prompt: str, user_message: str, max_tokens: int = 4096) -> str:
        """Appelle l'API Claude et retourne la réponse texte."""
        self.logger.info(f"Appel API Claude — {len(user_message)} caractères")

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        response = message.content[0].text
        usage = message.usage
        self.logger.info(
            f"Réponse reçue — {len(response)} caractères | "
            f"tokens in: {usage.input_tokens}, out: {usage.output_tokens}"
        )
        return response

    def run(self, context: dict) -> dict:
        """Méthode principale — chaque agent DOIT la redéfinir."""
        raise NotImplementedError(f"L'agent {self.name} doit implémenter run()")
