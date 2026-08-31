"""OAuth token storage backed by Titan's security boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, cast

from titan_cli.core.security.oauth_tokens import (
    OAuthSecretOrigin,
    OAuthStorageScope,
    ResolvedOAuthSecret,
    create_oauth_secret_store,
)

from .exceptions import OAuthStorageError
from .models import OAuthRequest, OAuthTokenSet, build_oauth_credential_key

_VALID_STORAGE_SCOPES: Final[frozenset[str]] = frozenset({"project", "user"})


@dataclass(frozen=True)
class StoredOAuthTokenSet:
    """Stored OAuth token set with source and writable scope metadata."""

    token_set: OAuthTokenSet
    origin: OAuthSecretOrigin
    storage_scope: OAuthStorageScope | None

    @property
    def scope(self) -> OAuthStorageScope | None:
        """Writable storage scope retained for older call sites."""
        return self.storage_scope


class OAuthTokenStore:
    """Stores one JSON token-set blob per OAuth credential."""

    def __init__(
        self,
        secrets: object | None = None,
        *,
        namespace: str = "titan",
        secret_prefix: str = "oauth",
    ) -> None:
        self.secrets = secrets or create_oauth_secret_store()
        self.namespace = namespace
        self.secret_prefix = secret_prefix

    def build_secret_key(self, request: OAuthRequest) -> str:
        """Return the SecretManager key for an OAuth request."""
        return f"{self.secret_prefix}_{build_oauth_credential_key(request)}"

    def read(self, request: OAuthRequest) -> OAuthTokenSet | None:
        """Read a stored token set, if present."""
        stored_token_set = self.read_with_scope(request)
        return stored_token_set.token_set if stored_token_set else None

    def read_with_scope(self, request: OAuthRequest) -> StoredOAuthTokenSet | None:
        """Read a stored token set with the scope that supplied it."""
        secret_key = self.build_secret_key(request)
        resolved_secret = self._get_secret_with_scope(secret_key)
        if not resolved_secret or not resolved_secret.value:
            return None

        try:
            payload = json.loads(resolved_secret.value)
            if not isinstance(payload, dict):
                raise ValueError("OAuth token payload is not an object.")
            return StoredOAuthTokenSet(
                token_set=OAuthTokenSet.from_dict(payload),
                origin=resolved_secret.origin,
                storage_scope=resolved_secret.storage_scope,
            )
        except Exception as exc:
            raise OAuthStorageError(
                f"Stored OAuth credential '{secret_key}' is not valid."
            ) from exc

    def write(
        self,
        request: OAuthRequest,
        token_set: OAuthTokenSet,
        *,
        scope: OAuthStorageScope = "user",
    ) -> str:
        """Write a token set and return the SecretManager key used."""
        secret_key = self.build_secret_key(request)
        try:
            scope = _validate_scope(scope)
            payload = json.dumps(
                token_set.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            )
            self._set_secret(secret_key, payload, scope=scope)
        except Exception as exc:
            raise OAuthStorageError(
                f"OAuth credential '{secret_key}' could not be written."
            ) from exc
        return secret_key

    def delete(
        self,
        request: OAuthRequest,
        *,
        scope: OAuthStorageScope = "user",
    ) -> None:
        """Delete a stored token set."""
        secret_key = self.build_secret_key(request)
        try:
            scope = _validate_scope(scope)
            self._delete_secret(secret_key, scope=scope)
            self._verify_secret_deleted(secret_key, scope=scope)
        except OAuthStorageError:
            raise
        except Exception as exc:
            raise OAuthStorageError(
                f"OAuth credential '{secret_key}' could not be deleted."
            ) from exc

    def read_env_secret(self, key: str) -> str | None:
        """Read an explicit access-token environment variable."""
        resolve_env = getattr(self.secrets, "resolve_env", None)
        if resolve_env:
            return resolve_env(key)
        return None

    def read_legacy_secret(self, key: str) -> ResolvedOAuthSecret | None:
        """Read a configured legacy single-token secret."""
        return self._get_secret_with_scope(key)

    def _get_secret_with_scope(self, key: str) -> ResolvedOAuthSecret | None:
        resolve = getattr(self.secrets, "resolve", None)
        if resolve:
            resolved_secret = resolve(key, namespace=self.namespace)
            normalized_secret = _normalize_resolved_secret(resolved_secret)
            if normalized_secret:
                return normalized_secret

        get_with_scope = getattr(self.secrets, "get_with_scope", None)
        if get_with_scope:
            if self.namespace == "titan":
                resolved_secret = get_with_scope(key)
            else:
                resolved_secret = get_with_scope(key, namespace=self.namespace)
            normalized_secret = _normalize_resolved_secret(resolved_secret)
            if normalized_secret:
                return normalized_secret

        raw_value = self._get_secret_legacy(key)
        return ResolvedOAuthSecret(raw_value, "keyring", "user") if raw_value else None

    def _get_secret_legacy(self, key: str) -> str | None:
        if self.namespace == "titan":
            return self.secrets.get(key)
        return self.secrets.get(key, namespace=self.namespace)

    def _set_secret(
        self,
        key: str,
        value: str,
        *,
        scope: OAuthStorageScope,
    ) -> None:
        if self.namespace == "titan":
            self.secrets.set(key, value, scope=scope)
            return
        self.secrets.set(key, value, namespace=self.namespace, scope=scope)

    def _delete_secret(self, key: str, *, scope: OAuthStorageScope) -> None:
        if self.namespace == "titan":
            self.secrets.delete(key, scope=scope)
            return
        self.secrets.delete(key, namespace=self.namespace, scope=scope)

    def _verify_secret_deleted(self, key: str, *, scope: OAuthStorageScope) -> None:
        """Verify that a scoped credential is gone after deletion."""
        scoped_value = self._get_secret_from_scope(key, scope=scope)
        if scoped_value is not None:
            raise OAuthStorageError(
                f"OAuth credential '{key}' was not deleted from {scope} storage."
            )

    def _get_secret_from_scope(
        self,
        key: str,
        *,
        scope: OAuthStorageScope,
    ) -> str | None:
        get_from_scope = getattr(self.secrets, "get_from_scope", None)
        if get_from_scope:
            if self.namespace == "titan":
                return get_from_scope(key, scope=scope)
            return get_from_scope(key, namespace=self.namespace, scope=scope)

        resolved_secret = self._get_secret_with_scope(key)
        if resolved_secret and resolved_secret.storage_scope == scope:
            return resolved_secret.value
        return None


def _normalize_resolved_secret(value: object) -> ResolvedOAuthSecret | None:
    """Normalize SecretManager-compatible scoped secret results."""
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2:
        secret_value, secret_origin = value
        if isinstance(secret_value, str) and secret_origin in {
            "env",
            "project",
            "keyring",
        }:
            return ResolvedOAuthSecret(
                secret_value,
                cast(OAuthSecretOrigin, secret_origin),
                _storage_scope_for_origin(secret_origin),
            )
        return None
    secret_value = getattr(value, "value", None)
    secret_origin = getattr(value, "origin", None)
    secret_storage_scope = getattr(value, "storage_scope", None)
    if isinstance(secret_value, str) and secret_origin in {
        "env",
        "project",
        "keyring",
    }:
        storage_scope = (
            _validate_scope(secret_storage_scope)
            if secret_storage_scope is not None
            else _storage_scope_for_origin(secret_origin)
        )
        return ResolvedOAuthSecret(
            secret_value,
            cast(OAuthSecretOrigin, secret_origin),
            storage_scope,
        )

    secret_scope = getattr(value, "scope", None)
    if isinstance(secret_value, str) and secret_scope in {"env", "project", "user"}:
        origin = "keyring" if secret_scope == "user" else secret_scope
        return ResolvedOAuthSecret(
            secret_value,
            cast(OAuthSecretOrigin, origin),
            None if secret_scope == "env" else cast(OAuthStorageScope, secret_scope),
        )
    return None


def _storage_scope_for_origin(origin: object) -> OAuthStorageScope | None:
    if origin == "project":
        return "project"
    if origin == "keyring":
        return "user"
    return None


def _validate_scope(scope: object) -> OAuthStorageScope:
    """Validate runtime storage scopes before delegating to SecretManager."""
    if scope not in _VALID_STORAGE_SCOPES:
        allowed = ", ".join(sorted(_VALID_STORAGE_SCOPES))
        raise ValueError(f"OAuth storage scope must be one of: {allowed}.")
    return cast(OAuthStorageScope, scope)
