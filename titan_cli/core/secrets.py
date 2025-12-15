# titan_cli/core/secrets.py
import os
import keyring
from pathlib import Path
from typing import Optional, Literal
from dotenv import load_dotenv
from ..ui.components.typography import TextRenderer
from ..ui.views.prompts import PromptsRenderer
from ..messages import msg

ScopeType = Literal["env", "project", "user"]

class SecretManager:
    """
    Manages secrets with a 3-level cascade:
    
    1. Environment variables (HIGHEST - CI/CD)
    2. Project secrets (.titan/secrets.env - team-shared)
    3. System keyring (USER - personal credentials)
    """

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self._load_project_secrets()

    def _load_project_secrets(self):
        """Load secrets from .titan/secrets.env"""
        secrets_file = self.project_path / ".titan" / "secrets.env"
        if secrets_file.exists():
            load_dotenv(secrets_file)

    def get(self, key: str, namespace: str = "titan") -> Optional[str]:
        """
        Get secret with cascading priority
        
        Priority:
        1. Environment variable (e.g., GITHUB_TOKEN, includes project secrets loaded at init)
        2. System keyring (user-level)
        3. None
        
        Note: Project secrets (.titan/secrets.env) are loaded
        into environment on init, so they are checked in step 1.
        """
        # 1. Environment variable (includes project secrets)
        env_key = key.upper()
        if env_key in os.environ:
            return os.environ[env_key]

        # 2. System keyring
        try:
            value = keyring.get_password(namespace, key)
            if value:
                return value
        except Exception:
            pass  # Keyring might not be available

        return None

    def set(
        self,
        key: str,
        value: str,
        namespace: str = "titan",
        scope: ScopeType = "user"
    ):
        """
        Set secret
        
        Args:
            key: Secret key (e.g., "anthropic_api_key")
            value: Secret value
            namespace: Keyring namespace
            scope: Where to store:
                - "env": Current environment only (temporary)
                - "project": .titan/secrets.env (team-shared)
                - "user": System keyring (personal, secure)
        """
        if scope == "env":
            # Set in current environment only
            os.environ[key.upper()] = value

        elif scope == "user":
            # Store in system keyring (most secure)
            try:
                keyring.set_password(namespace, key, value)
            except Exception as e:
                # Fallback to project scope if keyring fails (common on macOS with unsigned apps)
                text = TextRenderer()
                text.warning(msg.Secrets.KEYRING_FALLBACK.format(e=e))
                # Recursively call with project scope
                self.set(key, value, scope="project")

        elif scope == "project":
            # Store in .titan/secrets.env
            secrets_file = self.project_path / ".titan" / "secrets.env"
            secrets_file.parent.mkdir(parents=True, exist_ok=True)

            # Read existing content
            existing_lines = []
            if secrets_file.exists():
                with open(secrets_file, "r") as f:
                    existing_lines = f.readlines()

            # Update or append
            key_upper = key.upper()
            updated = False
            for i, line in enumerate(existing_lines):
                if line.startswith(f"{key_upper}="):
                    existing_lines[i] = f"{key_upper}='{value}'\n"
                    updated = True
                    break

            if not updated:
                existing_lines.append(f"{key_upper}='{value}'\n")

            # Write back
            with open(secrets_file, "w") as f:
                f.writelines(existing_lines)

    def delete(self, key: str, namespace: str = "titan", scope: ScopeType = "user"):
        """Delete secret from specified scope"""
        if scope == "env":
            env_key = key.upper()
            os.environ.pop(env_key, None)

        elif scope == "user":
            try:
                keyring.delete_password(namespace, key)
            except Exception:
                pass # Keyring might not be available

        elif scope == "project":
            secrets_file = self.project_path / ".titan" / "secrets.env"
            if not secrets_file.exists():
                return

            # Read and filter
            with open(secrets_file, "r") as f:
                lines = f.readlines()

            key_upper = key.upper()
            filtered = [line for line in lines if not line.startswith(f"{key_upper}=")]

            # Write back
            with open(secrets_file, "w") as f:
                f.writelines(filtered)

    def prompt_and_set(
        self,
        key: str,
        prompt_text: str,
        scope: ScopeType = "user",
        namespace: str = "titan"
    ) -> Optional[str]:
        """
        Interactively prompt for secret and store it
        
        Returns:
            The entered value or None if cancelled
        """
        text = TextRenderer()
        prompts = PromptsRenderer(text_renderer=text)

        try:
            value = prompts.ask_text(prompt_text, password=True)  # Hidden input
            if value:
                self.set(key, value, namespace=namespace, scope=scope)
                text.success(msg.Projects.SECRET_SAVED.format(key=key, scope=scope))
                return value
            return None
        except (EOFError, KeyboardInterrupt):
            text.warning(msg.Secrets.AI_SETUP_CANCELLED) 
            return None
