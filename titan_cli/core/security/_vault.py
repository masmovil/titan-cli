# Private vault: the only module in Titan allowed to touch raw secret strings
# or the OS keyring. Nothing outside titan_cli/core/security/ may import it —
# enforced by tests/core/security/test_architecture.py.
import os
import re
from pathlib import Path
from typing import Literal, Optional

import keyring
from dotenv import dotenv_values

from .redaction import register_secret

ScopeType = Literal["project", "user"]

# Where a resolved value came from. "keyring" is the only level the vault
# owns end-to-end (namespaced, deletable); "env" and "project" are global
# inputs — retry/delete logic must not treat them as stale keyring entries.
OriginType = Literal["env", "project", "keyring"]

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
    `dotenv_values(..., interpolate=False)` unchanged. Double quotes with
    backslash escapes: a single-quoted form cannot carry the quote character
    itself, and an unescaped newline would split the entry into two lines.
    (Interpolation is disabled on the read side — otherwise `${...}` inside
    a secret would be expanded against the environment.)
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


# A dotenv entry as `_load_project_secrets` accepts it: optional leading
# whitespace and `export`, then the key. Line matching for set()/delete()
# must use the same shape, or entries load fine but can never be updated
# or removed from the file.
def _line_defines_key(line: str, key_upper: str) -> bool:
    match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
    return bool(match) and match.group(1).upper() == key_upper


class SecretManager:
    """
    Manages secrets with a 3-level cascade:

    1. Environment variables (HIGHEST - CI/CD)
    2. Project secrets (.titan/secrets.env, held in memory - team-shared)
    3. System keyring (USER - personal credentials)

    The env and project levels are deliberately GLOBAL — they exist for
    CI/CD and team-shared credentials and do not participate in keyring
    namespacing. Only the keyring level is namespace-scoped.

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
            # interpolate=False: a `${...}` sequence inside a stored secret is
            # part of the secret, not a reference to the environment.
            self._project_secrets = {
                key.upper(): value
                for key, value in dotenv_values(secrets_file, interpolate=False).items()
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
        value, _ = self.resolve(key, namespace=namespace)
        return value

    def resolve(
        self, key: str, namespace: str = "titan"
    ) -> tuple[Optional[str], Optional[OriginType]]:
        """
        Like `get`, but also reports WHICH level satisfied the read.

        The origin never carries the value anywhere new — it exists so
        callers inside the boundary can make level-aware decisions (e.g. a
        failed command must not delete a keyring entry when the value came
        from the environment).
        """
        # Blank values are treated as ABSENT at every level, uniformly: an
        # empty/whitespace env var means "unset" in practice, and a blank
        # credential authenticates as nothing and fails as an opaque 401
        # downstream. A blank at one level falls through to the next.
        env_key = key.upper()
        if env_key in os.environ:
            value = os.environ[env_key]
            if value.strip():
                register_secret(value)
                return value, "env"

        if env_key in self._project_secrets:
            value = self._project_secrets[env_key]
            if value.strip():
                register_secret(value)
                return value, "project"

        try:
            value = keyring.get_password(namespace, key)
        except Exception:
            # Keyring might not be available for THIS read; the legacy
            # fallback below gets its own attempt, same as a miss.
            value = None
        if value and value.strip():
            register_secret(value)
            return value, "keyring"

        if namespace not in LEGACY_NAMESPACES:
            legacy = self._get_legacy_and_migrate(key, namespace)
            if legacy is not None:
                return legacy, "keyring"

        return None, None

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
        # Register on the way IN, not only on read-back: in the
        # store-then-immediately-use flow, output produced before the first
        # read would otherwise not be redacted.
        register_secret(value)

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
            # Replace the FIRST definition and drop any duplicates: dotenv
            # resolves the LAST one, so rewriting only the first while a
            # second survives would leave the stale value winning on load.
            updated = False
            kept_lines = []
            for line in existing_lines:
                if _line_defines_key(line, key_upper):
                    if not updated:
                        kept_lines.append(entry)
                        updated = True
                    continue
                kept_lines.append(line)
            existing_lines = kept_lines

            if not updated:
                # A file without a trailing newline would glue the new entry
                # onto the previous one, destroying both.
                if existing_lines and not existing_lines[-1].endswith("\n"):
                    existing_lines[-1] += "\n"
                existing_lines.append(entry)

            # Plaintext credentials must never be world-readable, not even
            # for an instant: create WITH 0600 (a plain open() would create
            # under the umask and leave a readable window until a chmod).
            # The chmod still runs for files that predate the tightening.
            fd = os.open(secrets_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.writelines(existing_lines)
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
            # BUT only when this namespace holds its own copy — that is the
            # evidence it owns the key (it stored or migrated it). The legacy
            # entries are shared by every namespace's fallback, so sweeping
            # unconditionally would let one plugin's delete destroy the copy
            # another plugin has yet to migrate. Any read/exists through a
            # scoped namespace migrates the key first, so legitimate owners
            # always have the scoped copy by the time they delete.
            targets = [namespace]
            if namespace not in LEGACY_NAMESPACES:
                try:
                    owns_key = keyring.get_password(namespace, key) is not None
                except Exception:
                    owns_key = False
                if owns_key:
                    targets.extend(LEGACY_NAMESPACES)
            for target in targets:
                try:
                    keyring.delete_password(target, key)
                except Exception:
                    pass  # Keyring might not be available / entry absent

        elif scope == "project":
            key_upper = key.upper()
            secrets_file = self.project_path / ".titan" / "secrets.env"

            # File first, memory second: dropping the in-memory copy before a
            # file operation that then fails would leave get() reporting the
            # secret gone while the file still holds it.
            if secrets_file.exists():
                with open(secrets_file, "r") as f:
                    lines = f.readlines()

                filtered = [line for line in lines if not _line_defines_key(line, key_upper)]

                with open(secrets_file, "w") as f:
                    f.writelines(filtered)

            self._project_secrets.pop(key_upper, None)

        else:
            raise ValueError(
                f"Unknown secret scope {scope!r}. Valid scopes: 'user', 'project'."
            )
