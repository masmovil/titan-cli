# Private vault: the only module in Titan allowed to touch raw secret strings
# or the OS keyring. Nothing outside titan_cli/core/security/ may import it
# (the transitional titan_cli/core/secrets.py shim is the single sanctioned
# exception until the legacy importers finish migrating).
import os
from pathlib import Path
from typing import Literal, Optional

import keyring
from dotenv import dotenv_values

from .redaction import register_secret

ScopeType = Literal["project", "user"]


class SecretManager:
    """
    Manages secrets with a 3-level cascade:

    1. Environment variables (HIGHEST - CI/CD)
    2. Project secrets (.titan/secrets.env, held in memory - team-shared)
    3. System keyring (USER - personal credentials)

    Project secrets are parsed into an internal dict and never written to
    `os.environ`: a subprocess must receive a secret explicitly, never by
    inheriting the parent environment.
    """

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self._project_secrets: dict[str, str] = {}
        self._load_project_secrets()

    def _load_project_secrets(self):
        """Parse .titan/secrets.env into memory without touching os.environ."""
        secrets_file = self.project_path / ".titan" / "secrets.env"
        if secrets_file.exists():
            self._project_secrets = {
                key.upper(): value
                for key, value in dotenv_values(secrets_file).items()
                if value is not None
            }

    def get(self, key: str, namespace: str = "titan") -> Optional[str]:
        """
        Get secret with cascading priority.

        Priority:
        1. Environment variable (e.g., GITHUB_TOKEN)
        2. Project secrets (.titan/secrets.env, in-memory)
        3. System keyring (user-level)
        4. None

        Every returned value is registered in the redaction filter.
        """
        env_key = key.upper()
        if env_key in os.environ:
            value = os.environ[env_key]
            register_secret(value)
            return value

        if env_key in self._project_secrets:
            value = self._project_secrets[env_key]
            register_secret(value)
            return value

        try:
            value = keyring.get_password(namespace, key)
        except Exception:
            return None  # Keyring might not be available
        if value:
            register_secret(value)
            return value

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
                - "project": .titan/secrets.env (team-shared)
                - "user": System keyring (personal, secure)
        """
        if scope == "user":
            # Store in system keyring (most secure). A keyring failure raises:
            # falling back to the project file would silently move a personal
            # credential into a team-shared location.
            keyring.set_password(namespace, key, value)

        elif scope == "project":
            secrets_file = self.project_path / ".titan" / "secrets.env"
            secrets_file.parent.mkdir(parents=True, exist_ok=True)

            existing_lines = []
            if secrets_file.exists():
                with open(secrets_file, "r") as f:
                    existing_lines = f.readlines()

            key_upper = key.upper()
            updated = False
            for i, line in enumerate(existing_lines):
                if line.startswith(f"{key_upper}="):
                    existing_lines[i] = f"{key_upper}='{value}'\n"
                    updated = True
                    break

            if not updated:
                existing_lines.append(f"{key_upper}='{value}'\n")

            with open(secrets_file, "w") as f:
                f.writelines(existing_lines)

            self._project_secrets[key_upper] = value

        else:
            raise ValueError(
                f"Unknown secret scope {scope!r}. Valid scopes: 'user', 'project'. "
                f"Writing secrets to os.environ is not supported."
            )

    def delete(self, key: str, namespace: str = "titan", scope: ScopeType = "user"):
        """Delete secret from specified scope"""
        if scope == "user":
            try:
                keyring.delete_password(namespace, key)
            except Exception:
                pass  # Keyring might not be available

        elif scope == "project":
            self._project_secrets.pop(key.upper(), None)

            secrets_file = self.project_path / ".titan" / "secrets.env"
            if not secrets_file.exists():
                return

            with open(secrets_file, "r") as f:
                lines = f.readlines()

            key_upper = key.upper()
            filtered = [line for line in lines if not line.startswith(f"{key_upper}=")]

            with open(secrets_file, "w") as f:
                f.writelines(filtered)

        else:
            raise ValueError(
                f"Unknown secret scope {scope!r}. Valid scopes: 'user', 'project'."
            )
