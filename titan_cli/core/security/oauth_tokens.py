"""OAuth token storage bridge inside Titan's secret trust boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import keyring

from ._vault import OriginType, ScopeType, SecretManager
from .redaction import register_secret

OAuthSecretOrigin = OriginType
OAuthStorageScope = ScopeType


@dataclass(frozen=True)
class ResolvedOAuthSecret:
    """Secret value plus its origin and writable storage scope, when any."""

    value: str
    origin: OAuthSecretOrigin
    storage_scope: OAuthStorageScope | None

    @property
    def scope(self) -> str:
        """Backward-compatible label for callers migrating from SecretManager."""
        return "user" if self.origin == "keyring" else self.origin


class OAuthSecretStore:
    """Secret-boundary adapter for OAuth token blobs and legacy credentials."""

    def __init__(
        self,
        *,
        project_path: Path | None = None,
        vault: SecretManager | None = None,
    ) -> None:
        self._vault = vault or SecretManager(project_path=project_path)

    def resolve(
        self,
        key: str,
        *,
        namespace: str = "titan",
    ) -> ResolvedOAuthSecret | None:
        """Resolve a secret through the vault cascade."""
        value, origin = self._vault.resolve(key, namespace=namespace)
        if not value or not value.strip() or origin is None:
            return None
        register_secret(value)
        return ResolvedOAuthSecret(
            value=value,
            origin=origin,
            storage_scope=_storage_scope_for_origin(origin),
        )

    def resolve_env(self, key: str) -> str | None:
        """Resolve an explicit environment variable by name."""
        value = os.environ.get(key)
        if value is None and key.upper() != key:
            value = os.environ.get(key.upper())
        if not value or not value.strip():
            return None
        register_secret(value)
        return value.strip()

    def set(
        self,
        key: str,
        value: str,
        *,
        namespace: str = "titan",
        scope: OAuthStorageScope = "user",
    ) -> None:
        """Store an OAuth secret in a writable vault scope."""
        self._vault.set(key, value, namespace=namespace, scope=scope)

    def delete(
        self,
        key: str,
        *,
        namespace: str = "titan",
        scope: OAuthStorageScope = "user",
    ) -> None:
        """Delete an OAuth secret from a writable vault scope."""
        self._vault.delete(key, namespace=namespace, scope=scope)

    def get_from_scope(
        self,
        key: str,
        *,
        namespace: str = "titan",
        scope: OAuthStorageScope = "user",
    ) -> str | None:
        """Read one writable scope for delete-postcondition checks."""
        value: str | None
        if scope == "project":
            value = self._vault._project_secrets.get(key.upper())
        elif scope == "user":
            value = keyring.get_password(namespace, key)
        else:
            raise ValueError(
                f"Unknown OAuth storage scope {scope!r}. "
                "Valid scopes: 'user', 'project'."
            )
        if not value or not value.strip():
            return None
        register_secret(value)
        return value


def create_oauth_secret_store(project_path: Path | None = None) -> OAuthSecretStore:
    """Create an OAuth secret store scoped to a project root."""
    return OAuthSecretStore(project_path=project_path)


def _storage_scope_for_origin(origin: OAuthSecretOrigin) -> OAuthStorageScope | None:
    if origin == "project":
        return "project"
    if origin == "keyring":
        return "user"
    return None
