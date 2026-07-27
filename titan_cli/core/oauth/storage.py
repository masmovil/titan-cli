"""SecretManager-backed OAuth token storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, cast

from titan_cli.core.secrets import ResolvedSecret, ScopeType, SecretManager

from .exceptions import OAuthStorageError
from .models import OAuthRequest, OAuthTokenSet, build_oauth_credential_key

_VALID_STORAGE_SCOPES: Final[frozenset[str]] = frozenset({"env", "project", "user"})


@dataclass(frozen=True)
class StoredOAuthTokenSet:
    """Stored OAuth token set with its SecretManager scope."""

    token_set: OAuthTokenSet
    scope: ScopeType


class OAuthTokenStore:
    """Stores one JSON token-set blob per OAuth credential."""

    def __init__(
        self,
        secrets: SecretManager,
        *,
        namespace: str = "titan",
        secret_prefix: str = "oauth",
    ) -> None:
        self.secrets = secrets
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
                scope=resolved_secret.scope,
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
        scope: ScopeType = "user",
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

    def delete(self, request: OAuthRequest, *, scope: ScopeType = "user") -> None:
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

    def _get_secret_with_scope(self, key: str) -> ResolvedSecret | None:
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
        return ResolvedSecret(raw_value, "user") if raw_value else None

    def _get_secret_legacy(self, key: str) -> str | None:
        if self.namespace == "titan":
            return self.secrets.get(key)
        return self.secrets.get(key, namespace=self.namespace)

    def _set_secret(self, key: str, value: str, *, scope: ScopeType) -> None:
        if self.namespace == "titan":
            self.secrets.set(key, value, scope=scope)
            return
        self.secrets.set(key, value, namespace=self.namespace, scope=scope)

    def _delete_secret(self, key: str, *, scope: ScopeType) -> None:
        if self.namespace == "titan":
            self.secrets.delete(key, scope=scope)
            return
        self.secrets.delete(key, namespace=self.namespace, scope=scope)

    def _verify_secret_deleted(self, key: str, *, scope: ScopeType) -> None:
        """Verify that a scoped credential is gone after deletion."""
        scoped_value = self._get_secret_from_scope(key, scope=scope)
        if scoped_value is not None:
            raise OAuthStorageError(
                f"OAuth credential '{key}' was not deleted from {scope} storage."
            )

    def _get_secret_from_scope(self, key: str, *, scope: ScopeType) -> str | None:
        get_from_scope = getattr(self.secrets, "get_from_scope", None)
        if get_from_scope:
            if self.namespace == "titan":
                return get_from_scope(key, scope=scope)
            return get_from_scope(key, namespace=self.namespace, scope=scope)

        resolved_secret = self._get_secret_with_scope(key)
        if resolved_secret and resolved_secret.scope == scope:
            return resolved_secret.value
        return None


def _normalize_resolved_secret(value: object) -> ResolvedSecret | None:
    """Normalize SecretManager-compatible scoped secret results."""
    if value is None:
        return None
    secret_value = getattr(value, "value", None)
    secret_scope = getattr(value, "scope", None)
    if isinstance(secret_value, str) and secret_scope in {"env", "project", "user"}:
        return ResolvedSecret(secret_value, secret_scope)
    return None


def _validate_scope(scope: object) -> ScopeType:
    """Validate runtime storage scopes before delegating to SecretManager."""
    if scope not in _VALID_STORAGE_SCOPES:
        allowed = ", ".join(sorted(_VALID_STORAGE_SCOPES))
        raise ValueError(f"OAuth storage scope must be one of: {allowed}.")
    return cast(ScopeType, scope)
