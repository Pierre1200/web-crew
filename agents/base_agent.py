import anthropic
import os
import json
import logging
import typer
from utils.project import Project
from utils.cleaners import parse_json_safe


class BaseAgent:
    """Classe mère dont héritent tous les agents."""

    # Modèle unique pour toute l'équipe — surchargeable via WEBCREW_MODEL
    # (ou par un agent qui redéfinit l'attribut). Évite la duplication du
    # nom de modèle dispersée dans chaque appel API.
    MODEL = os.getenv("WEBCREW_MODEL", "claude-opus-5")

    # Raisonnement adaptatif. THINKING = None n'envoie pas le paramètre :
    # obligatoire sur Haiku 4.5 qui ne supporte pas l'adaptatif. Attention,
    # sur Opus 5 le raisonnement est actif PAR DÉFAUT — ne pas envoyer le
    # paramètre n'économise donc rien, c'est `effort` qui règle la dépense.
    THINKING = {"type": "adaptive"}

    # Profondeur de raisonnement et de travail : low | medium | high | xhigh | max.
    # C'est LE levier qualité/coût des modèles récents. "high" est le défaut de
    # l'API ; "xhigh" est le meilleur réglage pour les tâches de code (designer).
    # EFFORT = None n'envoie pas le paramètre — OBLIGATOIRE sur Haiku 4.5, qui
    # rejette output_config.effort avec une erreur 400.
    EFFORT = "high"

    # Consommation cumulée du run, par modèle. Attribut de CLASSE (analogie C :
    # variable statique partagée) : tous les agents du process incrémentent la
    # même table, main.py l'affiche en fin de commande. Le détail appel par
    # appel reste dans les logs de chaque agent.
    CONSO_RUN = {}  # {modèle: {"in": int, "out": int, "appels": int}}

    def __init__(self, name: str, role: str, project: Project):
        self.name = name
        self.role = role
        self.project = project
        self._client = None  # créé au premier appel API — voir la property client
        self.logger = self._setup_logger()

    @property
    def client(self):
        """Client Anthropic créé paresseusement (lazy), au premier appel API.

        Avant, le client (et donc la clé API) était exigé dès __init__ : le
        validateur « zéro token » refusait de tourner sans ANTHROPIC_API_KEY
        alors qu'il n'appelle jamais l'API. Une @property se comporte comme un
        attribut à l'usage (self.client) mais exécute ce code à chaque accès.
        """
        if self._client is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY absente — renseigne-la dans .env "
                    "ou dans l'environnement avant de lancer un agent."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def load_config(self) -> dict:
        """Charge le config.json du projet. Point d'accès unique à la config."""
        return self.project.load_config()

    def _enregistrer_usage(self, usage):
        """Cumule les tokens d'un appel API dans le compteur d'équipe."""
        conso = BaseAgent.CONSO_RUN.setdefault(
            self.MODEL, {"in": 0, "out": 0, "appels": 0}
        )
        conso["in"] += usage.input_tokens
        conso["out"] += usage.output_tokens
        conso["appels"] += 1

    def _kwargs_thinking(self) -> dict:
        """Renvoie {'thinking': ...} si l'agent l'active, sinon {} — pour ne pas
        envoyer le paramètre aux modèles qui ne le supportent pas (Haiku 4.5)."""
        return {"thinking": self.THINKING} if self.THINKING else {}

    def _kwargs_effort(self) -> dict:
        """Renvoie {'output_config': {'effort': ...}} si l'agent le définit.

        Séparé de _kwargs_thinking parce que les deux paramètres n'ont pas la
        même compatibilité : Haiku 4.5 refuse les deux, mais un agent pourrait
        vouloir du raisonnement sans régler l'effort (ou l'inverse).
        """
        return {"output_config": {"effort": self.EFFORT}} if self.EFFORT else {}

    def _setup_logger(self):
        """Configure les logs de l'agent dans le dossier du projet."""
        logger = logging.getLogger(f"{self.project.name}.{self.name}")
        logger.setLevel(logging.INFO)

        # logging.getLogger renvoie un singleton par nom : sans cette garde, on
        # ajoute un handler à chaque instanciation → lignes de log dupliquées.
        if logger.handlers:
            return logger

        self.project.logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.project.logs_dir / f"{self.name}.log"
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        ))
        logger.addHandler(handler)
        return logger

    def _extraire_texte(self, message, allow_empty: bool = False) -> str:
        """Extrait le texte d'une réponse Claude de façon défensive.

        Gère les refus (stop_reason == 'refusal') et ne suppose pas que le
        premier bloc est du texte — évite l'IndexError si content est vide ou
        commence par un bloc non-texte.

        `allow_empty=True` tolère une réponse sans bloc texte : utile en
        poursuite quand le budget de tokens a été entièrement consommé par le
        raisonnement (stop_reason == 'max_tokens') avant tout texte — la boucle
        appelante relancera la génération au lieu d'échouer.
        """
        if message.stop_reason == "refusal":
            raise RuntimeError(
                f"Génération refusée par le modèle (agent {self.name})"
            )
        parts = [
            b.text for b in message.content
            if getattr(b, "type", None) == "text"
        ]
        if not parts:
            if allow_empty:
                return ""
            raise RuntimeError(
                f"Réponse sans texte exploitable (agent {self.name}, "
                f"stop_reason={message.stop_reason})"
            )
        return "".join(parts)

    def parse_json_response(self, response: str) -> dict:
        """Parse le JSON d'une réponse Claude ; sauvegarde la brute si invalide.

        Avant, une réponse imparsable était perdue (seuls 200 caractères
        survivaient dans le message d'exception) : impossible de faire un
        post-mortem. Maintenant elle atterrit dans logs/<agent>_reponse_invalide.txt
        AVANT que l'erreur remonte — le `raise` nu relance l'exception d'origine.
        """
        try:
            return parse_json_safe(response)
        except ValueError:
            self.project.logs_dir.mkdir(parents=True, exist_ok=True)
            dump = self.project.logs_dir / f"{self.name}_reponse_invalide.txt"
            dump.write_text(response, encoding="utf-8")
            self.logger.error(f"JSON invalide — réponse brute sauvegardée : {dump}")
            typer.echo(f"   💾 Réponse brute sauvegardée pour analyse : {dump}")
            raise

    def cahier_des_charges(self, plan: dict) -> str:
        """Reconstitue la commande réelle du client, telle que le designer doit
        la respecter — et telle que la critique visuelle doit la vérifier.

        C'était LE trou de l'architecture : Pierre décrit une maquette précise
        dans brief.md, l'orchestrateur la transcrit fidèlement dans
        plan["taches"], et le designer ne lisait que style_guide + textes.json.
        Toute l'information de STRUCTURE (ordre des blocs, colonnes, contraintes
        de mise en page) était écrite sur le disque puis jetée — d'où des rendus
        qui appliquaient toujours le même gabarit quel que soit le brief.

        Trois sources, de la plus précise à la plus générale :
        - l'instruction que l'orchestrateur a écrite POUR le designer
        - config["site"]["sections"] : les libellés riches ("Hero — deux
          colonnes : portrait à gauche + accroche à droite"), pas les clés
          aplaties de textes.json
        - toute clé "_note…" sous site ou site.style : les consignes libres

        Vit dans BaseAgent parce que deux agents en dépendent : le designer
        pour produire, la critique visuelle pour juger la conformité.
        Retourne "" si le projet ne décrit rien.
        """
        site = self.load_config().get("site", {})

        instruction = next(
            (t.get("instruction", "") for t in plan.get("taches", [])
             if t.get("agent") == "designer"),
            "",
        )
        sections_config = site.get("sections", []) or []

        # Convention du projet : toute clé "_note…" est une consigne écrite pour
        # les agents (_note_sections, _note_formulaire…). On les ramasse toutes,
        # sous site et sous site.style — ajouter une nouvelle note dans un
        # config.json suffit alors à la faire remonter, sans toucher au code.
        notes = []
        for source in (site, site.get("style") or {}):
            if not isinstance(source, dict):
                continue
            for cle, valeur in source.items():
                if cle.startswith("_note") and isinstance(valeur, str) and valeur.strip():
                    notes.append(valeur.strip())

        if not (instruction or sections_config or notes):
            self.logger.info("Aucun cahier des charges — conventions par défaut")
            return ""

        blocs = [
            "CAHIER DES CHARGES DU CLIENT — fait autorité sur TOUTES les "
            "conventions par défaut listées plus bas."
        ]
        if instruction:
            blocs.append(f"\nMission confiée au designer :\n{instruction}")
        if sections_config:
            liste = "\n".join(f"  {i}. {s}" for i, s in enumerate(sections_config, 1))
            blocs.append(
                f"\nStructure et disposition attendues, DANS CET ORDRE EXACT :\n{liste}"
            )
        if notes:
            liste_notes = "\n".join(f"  - {n}" for n in notes)
            blocs.append(f"\nContraintes explicites du client :\n{liste_notes}")
        blocs.append(
            "\nN'ajoute AUCUNE section absente de cette liste et n'en retire aucune. "
            "Si le cahier des charges contredit une convention par défaut "
            "(hauteur du hero, présence d'une navigation, nombre de colonnes...), "
            "le cahier des charges gagne, sans exception."
        )

        self.logger.info(
            f"Cahier des charges transmis — instruction: {bool(instruction)}, "
            f"{len(sections_config)} section(s) décrite(s), {len(notes)} note(s)"
        )
        return "\n".join(blocs)

    def lire_contexte_ingestion(self) -> dict:
        """Relit temp/context.json produit par l'agent Ingestion, s'il existe.

        Retourne le contexte complet, ou {} si le fichier est absent, vide ou
        illisible — l'agent appelant fonctionne alors comme si data/ n'existait
        pas. Mutualisé ici : l'orchestrateur et le copywriter dupliquaient
        chacun cette lecture défensive (violation DRY).
        """
        path = self.project.temp_dir / "context.json"
        if not path.exists():
            return {}
        try:
            ctx = self.read_json("temp/context.json")
        except (ValueError, OSError) as e:
            self.logger.warning(f"context.json illisible, ignoré : {e}")
            return {}
        if not ctx or ctx.get("vide"):
            return {}
        return ctx

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

    def call_claude(self, system_prompt: str, user_message: str, max_tokens: int = 16000) -> str:
        """Appelle l'API Claude (sans streaming) et retourne la réponse texte.

        Pour les réponses courtes à schéma fixe (JSON de plan, métadonnées).
        Le défaut de 16 000 tient sous le délai d'expiration HTTP tout en
        laissant de la marge : ATTENTION, les tokens de raisonnement se
        déduisent de max_tokens — un budget trop serré peut être entièrement
        consommé par la réflexion, avant le moindre caractère de réponse.
        Au-delà, passer par call_claude_continuable (streaming).
        """
        self.logger.info(f"Appel API Claude — {len(user_message)} caractères")

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ],
            **self._kwargs_thinking(),
            **self._kwargs_effort(),
        )

        response = self._extraire_texte(message)
        usage = message.usage
        self._enregistrer_usage(usage)
        self.logger.info(
            f"Réponse reçue — {len(response)} caractères | "
            f"tokens in: {usage.input_tokens}, out: {usage.output_tokens}"
        )
        return response

    def call_claude_vision(
        self,
        system_prompt: str,
        blocs: list,
        max_tokens: int = 48000,
    ) -> str:
        """Appelle Claude EN STREAMING avec un message MIXTE (images + texte).

        `blocs` est une liste de blocs de contenu, dans l'ordre où le modèle
        doit les lire : une image, sa légende, l'image suivante, etc.
        Utilisé par la critique visuelle, qui doit REGARDER le site rendu et
        pas seulement lire son code source.

        Streaming et budget large, tous deux appris à la dure lors du premier
        run réel : l'agent tourne en effort `xhigh` avec une dizaine d'images
        en entrée. Il réfléchit donc beaucoup, et **les tokens de raisonnement
        se déduisent de max_tokens**. Avec 16 000, il ne restait plus assez de
        budget pour finir un JSON contenant des blocs CSS entiers : la réponse
        a été coupée en plein milieu d'une chaîne, et la passe entière perdue.

        Utiliser build_bloc_image() pour construire les blocs d'image.
        """
        nb_images = sum(1 for b in blocs if b.get("type") == "image")
        self.logger.info(f"Appel API Claude (vision) — {nb_images} image(s)")

        with self.client.messages.stream(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": blocs}],
            **self._kwargs_thinking(),
            **self._kwargs_effort(),
        ) as flux:
            message = flux.get_final_message()

        response = self._extraire_texte(message)
        usage = message.usage
        self._enregistrer_usage(usage)
        self.logger.info(
            f"Réponse reçue — {len(response)} caractères | "
            f"tokens in: {usage.input_tokens}, out: {usage.output_tokens} | "
            f"stop: {message.stop_reason}"
        )

        # Une troncature silencieuse coûte la passe entière : on le dit tout de
        # suite, pendant que la réponse brute est encore récupérable.
        if message.stop_reason == "max_tokens":
            self.logger.error(
                f"Réponse vision tronquée à max_tokens={max_tokens} — "
                "relever le budget de cet appel"
            )
            typer.echo(
                f"   ⚠️  Réponse coupée par la limite de {max_tokens} tokens. "
                "La réponse brute est sauvegardée si le parsing échoue."
            )
        return response

    @staticmethod
    def build_bloc_image(chemin) -> dict:
        """Construit un bloc d'image encodé en base64 pour l'API.

        base64 = encodage d'octets binaires en texte ASCII : une image ne peut
        pas voyager telle quelle dans du JSON, on la transcrit en caractères.
        """
        import base64
        from pathlib import Path

        chemin = Path(chemin)
        donnees = base64.standard_b64encode(chemin.read_bytes()).decode("utf-8")
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": donnees,
            },
        }

    def call_claude_continuable(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 32000,
        auto_continue: bool = False,
    ) -> str:
        """Appelle Claude EN STREAMING et poursuit si la limite est atteinte.

        Le streaming est obligatoire au-delà de ~16 000 tokens de sortie : sans
        lui, la requête HTTP expire avant la fin de la génération. En échange, on
        peut viser 32-64k tokens d'un coup, et la boucle de poursuite ci-dessous
        ne sert plus que de filet de sécurité. C'est important pour la QUALITÉ :
        chaque reprise crée une « couture » dans le code (c'est une couture de ce
        type qui avait produit un <label> dupliqué sur un site déjà livré).

        Poursuite automatique si `auto_continue=True` OU si l'entrée standard
        n'est pas un terminal (run CI/cron) — sinon on demande confirmation.
        """
        import sys

        messages = [{"role": "user", "content": user_message}]
        full_response = ""

        while True:
            self.logger.info(f"Appel API Claude — {len(messages[-1]['content'])} chars (dernier msg)")

            # with ... as stream : le SDK ouvre la connexion, la maintient le
            # temps de la génération, et la referme proprement à la sortie du
            # bloc (même en cas d'erreur). get_final_message() rassemble tous
            # les morceaux reçus en un objet identique à un appel classique.
            with self.client.messages.stream(
                model=self.MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
                **self._kwargs_thinking(),
                **self._kwargs_effort(),
            ) as stream:
                message = stream.get_final_message()

            chunk = self._extraire_texte(
                message, allow_empty=(message.stop_reason == "max_tokens")
            )
            usage = message.usage
            self._enregistrer_usage(usage)
            self.logger.info(
                f"Réponse reçue — {len(chunk)} chars | "
                f"in: {usage.input_tokens}, out: {usage.output_tokens} | "
                f"stop: {message.stop_reason}"
            )

            full_response += chunk

            if message.stop_reason != "max_tokens":
                break

            typer.echo(
                f"\n   ⚠️  Limite de tokens atteinte "
                f"({usage.output_tokens} tokens, {len(full_response)} chars générés au total)"
            )
            if auto_continue or not sys.stdin.isatty():
                typer.echo("   → Poursuite automatique de la génération...")
            elif not typer.confirm("   Continuer la génération ?", default=True):
                break

            # On renvoie les blocs complets (dont thinking), pas seulement le texte :
            # avec le raisonnement activé, les blocs de pensée doivent être conservés
            # tels quels sur le même modèle pour poursuivre la génération.
            messages.append({"role": "assistant", "content": message.content})
            messages.append({
                "role": "user",
                "content": "Continue exactement là où tu t'es arrêté, sans rien répéter de ce qui a déjà été généré."
            })

        return full_response

    def run(self, context: dict) -> dict:
        """Méthode principale — chaque agent DOIT la redéfinir."""
        raise NotImplementedError(f"L'agent {self.name} doit implémenter run()")
