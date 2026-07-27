from __future__ import annotations

# titan_cli/core/secrets.py
from collections.abc import Iterable
import os
from dataclasses import dataclass
import keyring
from pathlib import Path
import tempfile
import threading
from typing import Literal, Optional

from dotenv import dotenv_values, load_dotenv

ScopeType = Literal["env", "project", "user"]

_PROJECT_ENV_KEYS_LOCK = threading.Lock()
_PROJECT_ENV_KEYS_BY_PATH: dict[Path, set[str]] = {}
_PROJECT_SECRET_FILE_LOCKS_GUARD = threading.Lock()
_PROJECT_SECRET_FILE_LOCKS_BY_PATH: dict[Path, threading.Lock] = {}


@dataclass(frozen=True)
class ResolvedSecret:
    """Secret value plus the scope that supplied it."""

    value: str
    scope: ScopeType


class _ProjectSecretsFileLock:
    """Cross-process lock for one project's shared secrets file."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._thread_lock: threading.Lock | None = None
        self._handle = None

    def __enter__(self) -> "_ProjectSecretsFileLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = _shared_project_secret_file_lock(self.lock_path)
        self._thread_lock.acquire()
        try:
            self._handle = self.lock_path.open("a+", encoding="utf-8")
            self._ensure_windows_lock_byte()
            self._lock_file()
        except Exception:
            self._close_handle()
            self._thread_lock.release()
            self._thread_lock = None
            raise
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            self._unlock_file()
        finally:
            self._close_handle()
            if self._thread_lock:
                self._thread_lock.release()
                self._thread_lock = None
        return False

    def _lock_file(self) -> None:
        if not self._handle:
            raise RuntimeError("Project secrets lock handle is not open.")
        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_LOCK, 1)
            return

        import fcntl

        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)

    def _unlock_file(self) -> None:
        if not self._handle:
            return
        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)

    def _ensure_windows_lock_byte(self) -> None:
        if os.name != "nt" or not self._handle:
            return
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() > 0:
            self._handle.seek(0)
            return
        self._handle.write("0")
        self._handle.flush()
        self._handle.seek(0)

    def _close_handle(self) -> None:
        if self._handle:
            self._handle.close()
            self._handle = None


def _shared_project_secret_file_lock(lock_path: Path) -> threading.Lock:
    """Return the process-wide thread lock for a project secrets lock file."""
    with _PROJECT_SECRET_FILE_LOCKS_GUARD:
        return _PROJECT_SECRET_FILE_LOCKS_BY_PATH.setdefault(
            lock_path,
            threading.Lock(),
        )


class SecretManager:
    """
    Manages secrets with a 3-level cascade:

    1. Environment variables (HIGHEST - CI/CD)
    2. Project secrets (.titan/secrets.env - team-shared)
    3. System keyring (USER - personal credentials)
    """

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = (project_path or Path.cwd()).expanduser().resolve(
            strict=False
        )
        self._project_secret_values: dict[str, str] = {}
        self._project_env_keys = self._shared_project_env_keys(self.project_path)
        self._load_project_secrets()

    def _load_project_secrets(self):
        """Load secrets from .titan/secrets.env"""
        secrets_file = self.project_path / ".titan" / "secrets.env"
        if secrets_file.exists():
            self._project_secret_values = self._read_project_secrets_file()
            self._mark_project_env_keys(
                key for key in self._project_secret_values if key not in os.environ
            )
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
        resolved = self.get_with_scope(key, namespace=namespace)
        return resolved.value if resolved else None

    def get_with_scope(
        self,
        key: str,
        namespace: str = "titan",
    ) -> Optional[ResolvedSecret]:
        """Get a secret with the scope that supplied the winning value."""
        env_key = key.upper()
        self._refresh_project_secret_values()
        env_value = os.environ.get(env_key)
        project_value = self._project_secret_values.get(env_key)

        if env_value is not None:
            if self._is_project_env_key(env_key) and project_value is not None:
                if env_value != project_value:
                    os.environ[env_key] = project_value
                return ResolvedSecret(project_value, "project")
            return ResolvedSecret(env_value, "env")

        if project_value is not None:
            return ResolvedSecret(project_value, "project")

        try:
            value = keyring.get_password(namespace, key)
            if value:
                return ResolvedSecret(value, "user")
        except Exception:
            pass  # Keyring might not be available

        return None

    def set(
        self, key: str, value: str, namespace: str = "titan", scope: ScopeType = "user"
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
            env_key = key.upper()
            os.environ[env_key] = value
            self._discard_project_env_key(env_key)

        elif scope == "user":
            # Store in system keyring (most secure)
            keyring.set_password(namespace, key, value)

        elif scope == "project":
            # Store in .titan/secrets.env
            secrets_file = self._project_secrets_file()
            with self._lock_project_secrets_file():
                secrets_file.parent.mkdir(parents=True, exist_ok=True)
                key_upper = key.upper()
                self._refresh_project_secret_values()
                should_update_env = (
                    self._is_project_env_key(key_upper)
                    or key_upper not in os.environ
                )

                existing_lines = self._read_project_secret_lines(secrets_file)

                updated = False
                for i, line in enumerate(existing_lines):
                    if line.startswith(f"{key_upper}="):
                        existing_lines[i] = f"{key_upper}='{value}'\n"
                        updated = True
                        break

                if not updated:
                    existing_lines.append(f"{key_upper}='{value}'\n")

                self._write_project_secret_lines_atomic(
                    secrets_file,
                    existing_lines,
                )
                self._refresh_project_secret_values()
                if should_update_env:
                    os.environ[key_upper] = value
                    self._mark_project_env_key(key_upper)

    def delete(self, key: str, namespace: str = "titan", scope: ScopeType = "user"):
        """Delete secret from specified scope"""
        if scope == "env":
            env_key = key.upper()
            os.environ.pop(env_key, None)
            self._discard_project_env_key(env_key)

        elif scope == "user":
            try:
                keyring.delete_password(namespace, key)
            except Exception:
                pass  # Keyring might not be available

        elif scope == "project":
            secrets_file = self._project_secrets_file()
            with self._lock_project_secrets_file():
                if not secrets_file.exists():
                    return
                key_upper = key.upper()

                lines = self._read_project_secret_lines(secrets_file)
                filtered = [
                    line for line in lines if not line.startswith(f"{key_upper}=")
                ]

                self._write_project_secret_lines_atomic(secrets_file, filtered)
                self._refresh_project_secret_values()
                if self._is_project_env_key(key_upper):
                    os.environ.pop(key_upper, None)
                    self._discard_project_env_key(key_upper)

    def _read_project_secrets_file(self) -> dict[str, str]:
        """Read project secrets without consulting process environment."""
        secrets_file = self._project_secrets_file()
        if not secrets_file.exists():
            return {}
        values = dotenv_values(secrets_file)
        return {
            key.upper(): value for key, value in values.items() if value is not None
        }

    def _project_secrets_file(self) -> Path:
        """Return the project-scoped secrets file path."""
        return self.project_path / ".titan" / "secrets.env"

    def _lock_project_secrets_file(self) -> _ProjectSecretsFileLock:
        """Return a cross-process lock for project-scoped secrets writes."""
        secrets_file = self._project_secrets_file()
        return _ProjectSecretsFileLock(
            secrets_file.with_name(f"{secrets_file.name}.lock"),
        )

    def _read_project_secret_lines(self, secrets_file: Path) -> list[str]:
        """Read the project secrets file as raw lines."""
        if not secrets_file.exists():
            return []
        with secrets_file.open("r", encoding="utf-8") as f:
            return f.readlines()

    def _write_project_secret_lines_atomic(
        self,
        secrets_file: Path,
        lines: list[str],
    ) -> None:
        """Atomically replace the project secrets file with raw lines."""
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=secrets_file.parent,
                prefix=f".{secrets_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                temp_path = Path(f.name)
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, secrets_file)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _shared_project_env_keys(project_path: Path) -> set[str]:
        """Return the process-wide project-injected env key set for a project."""
        with _PROJECT_ENV_KEYS_LOCK:
            return _PROJECT_ENV_KEYS_BY_PATH.setdefault(project_path, set())

    def _refresh_project_secret_values(self) -> None:
        """Refresh project secret values from disk without mutating env."""
        self._project_secret_values = self._read_project_secrets_file()

    def _is_project_env_key(self, key: str) -> bool:
        with _PROJECT_ENV_KEYS_LOCK:
            return key in self._project_env_keys

    def _mark_project_env_key(self, key: str) -> None:
        with _PROJECT_ENV_KEYS_LOCK:
            self._project_env_keys.add(key)

    def _mark_project_env_keys(self, keys: Iterable[str]) -> None:
        with _PROJECT_ENV_KEYS_LOCK:
            self._project_env_keys.update(keys)

    def _discard_project_env_key(self, key: str) -> None:
        with _PROJECT_ENV_KEYS_LOCK:
            self._project_env_keys.discard(key)
