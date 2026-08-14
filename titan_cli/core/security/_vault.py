# Private vault: the only module in Titan allowed to touch raw secret strings
# or the OS keyring. Nothing outside titan_cli/core/security/ may import it —
# enforced by tests/core/security/test_architecture.py.
import os
from pathlib import Path
from typing import Literal, Optional

import keyring
from dotenv import dotenv_values

from .redaction import register_secret

ScopeType = Literal["project", "user"]

# Service names that predate the scoped namespaces (titan.core /
# titan.plugins.<name>). A keyring read that misses under a scoped namespace
# falls back here and, on a hit, copies the entry to its new home, so existing
# users are never re-prompted. The legacy copy is deliberately left in place:
# an installed pre-broker Titan on the same machine reads only these service
# names, and deleting its copy breaks it key by key. `delete()` still sweeps
# them, so a deleted key cannot be resurrected. Remove the leftover copies
# (and this fallback) once no pre-broker version remains in use.
LEGACY_NAMESPACES = ("titan", "ragnarok")


def _quote_env_value(value: str) -> str:
    """
    Serialize a value for a dotenv line so it round-trips through
    `dotenv_values` unchanged. Double quotes with backslash escapes: a
    single-quoted form cannot carry the quote character itself, and an
    unescaped newline would split the entry into two lines.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


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

        if namespace not in LEGACY_NAMESPACES:
            return self._get_legacy_and_migrate(key, namespace)

        return None

    def _get_legacy_and_migrate(self, key: str, namespace: str) -> Optional[str]:
        """Look `key` up under the legacy service names; copy to `namespace` on a hit."""
        for legacy in LEGACY_NAMESPACES:
            try:
                value = keyring.get_password(legacy, key)
            except Exception:
                # One namespace failing must not abort the whole fallback:
                # the next legacy service may still hold the key.
                continue
            if value:
                register_secret(value)
                # Best-effort: the read must succeed even if the keyring
                # refuses the write (e.g. a read-only backend).
                try:
                    keyring.set_password(namespace, key, value)
                except Exception:
                    pass
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
            entry = f"{key_upper}={_quote_env_value(value)}\n"
            updated = False
            for i, line in enumerate(existing_lines):
                if line.startswith(f"{key_upper}="):
                    existing_lines[i] = entry
                    updated = True
                    break

            if not updated:
                existing_lines.append(entry)

            with open(secrets_file, "w") as f:
                f.writelines(existing_lines)
            # Plaintext credentials must not be world-readable: the plain
            # open() above creates the file with the process umask (0644
            # on most systems), so tighten it explicitly every write.
            os.chmod(secrets_file, 0o600)

            self._project_secrets[key_upper] = value

        else:
            raise ValueError(
                f"Unknown secret scope {scope!r}. Valid scopes: 'user', 'project'. "
                f"Writing secrets to os.environ is not supported."
            )

    def delete(self, key: str, namespace: str = "titan", scope: ScopeType = "user"):
        """Delete secret from specified scope"""
        if scope == "user":
            # Sweep the legacy service names too: a copy left there would be
            # resurrected by the lazy-migration fallback on the next read.
            targets = (namespace, *LEGACY_NAMESPACES) if namespace not in LEGACY_NAMESPACES else (namespace,)
            for target in targets:
                try:
                    keyring.delete_password(target, key)
                except Exception:
                    pass  # Keyring might not be available / entry absent

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
