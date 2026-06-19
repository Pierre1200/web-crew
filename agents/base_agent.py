import anthropic
import os
import json
import logging
from pathlib import Path
from datetime import datetime

class BaseAgent:
    """Classe mère dont héritent tous les agents."""

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.workspace = Path("workspace")
        self.logger = self._setup_logger()

    def _setup_logger(self):
        """Configure les logs de l'agent."""
        logger = logging.getLogger(self.name)
        logger.setLevel(logging.INFO)

        # Crée un fichier de log par agent
        log_file = Path("logs") / f"{self.name}.log"
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        ))
        logger.addHandler(handler)
        return logger

    def read_json(self, filepath: str) -> dict:
        """Lit un fichier JSON du workspace."""
        path = self.workspace / filepath
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, filepath: str, data: dict):
        """Écrit un fichier JSON dans le workspace."""
        path = self.workspace / filepath
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Fichier écrit : {path}")

    def load_prompt(self, prompt_name: str) -> str:
        """Charge un system prompt depuis le dossier prompts/."""
        path = Path("prompts") / f"{prompt_name}.txt"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

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
        self.logger.info(f"Réponse reçue — {len(response)} caractères")
        return response

    def run(self, context: dict) -> dict:
        """
        Méthode principale — chaque agent DOIT la redéfinir.
        Reçoit un contexte, retourne un résultat.
        """
        raise NotImplementedError(f"L'agent {self.name} doit implémenter run()")
