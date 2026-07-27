"""Provider-neutral OAuth data models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import time
from typing import Any


def _normalize_optional(value: Any, *, field_name: str = "value") -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string when present.")
    stripped = value.strip()
    return stripped or None


def _normalize_token_type(value: Any, *, field_name: str = "token_type") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value.strip() or "Bearer"


def _normalize_optional_int(value: Any, *, field_name: str = "value") -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-boolean integer when present.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(
                f"{field_name} must be a non-boolean integer when present."
            )
        try:
            return int(stripped, 10)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be a non-boolean integer when present."
            ) from exc
    raise ValueError(f"{field_name} must be a non-boolean integer when present.")


def _normalize_values(
    values: Sequence[str] | str | None,
    *,
    field_name: str = "values",
    sort: bool = True,
) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    elif not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a string or sequence of strings.")

    normalized_values = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise ValueError(f"{field_name}[{index}] must be a string.")
        stripped = value.strip()
        if stripped:
            normalized_values.append(stripped)
    deduplicated_values = tuple(dict.fromkeys(normalized_values))
    if sort:
        return tuple(sorted(deduplicated_values))
    return deduplicated_values


def _normalize_mapping(
    value: Any,
    *,
    field_name: str = "metadata",
    allow_none: bool = True,
) -> dict[str, Any]:
    if value is None and allow_none:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping when present.")
    return dict(value)


@dataclass(frozen=True)
class OAuthRequest:
    """A provider-neutral request for an OAuth credential."""

    provider: str
    connection_id: str
    scopes: Sequence[str] = field(default_factory=tuple)
    interactive: bool = False
    access_token_env_var: str | None = None
    legacy_secret_keys: Sequence[str] = field(default_factory=tuple)
    subject: str | None = None
    storage_context: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", self.provider.strip().lower())
        object.__setattr__(self, "connection_id", self.connection_id.strip())
        object.__setattr__(
            self,
            "scopes",
            _normalize_values(self.scopes, field_name="scopes"),
        )
        object.__setattr__(
            self,
            "legacy_secret_keys",
            _normalize_values(
                self.legacy_secret_keys,
                field_name="legacy_secret_keys",
                sort=False,
            ),
        )
        object.__setattr__(
            self,
            "access_token_env_var",
            _normalize_optional(
                self.access_token_env_var,
                field_name="access_token_env_var",
            ),
        )
        object.__setattr__(
            self,
            "subject",
            _normalize_optional(self.subject, field_name="subject"),
        )
        object.__setattr__(
            self,
            "storage_context",
            _normalize_optional(
                self.storage_context,
                field_name="storage_context",
            ),
        )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

        if not self.provider:
            raise ValueError("OAuth provider is required.")
        if not self.connection_id:
            raise ValueError("OAuth connection_id is required.")


@dataclass(frozen=True)
class OAuthTokenSet:
    """Stored OAuth token data."""

    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None
    token_type: str = "Bearer"
    scopes: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.access_token, str):
            raise ValueError("OAuth access_token must be a string.")
        access_token = self.access_token.strip()
        if not access_token:
            raise ValueError("OAuth access_token is required.")
        object.__setattr__(self, "access_token", access_token)
        object.__setattr__(
            self,
            "refresh_token",
            _normalize_optional(self.refresh_token, field_name="refresh_token"),
        )
        object.__setattr__(
            self,
            "expires_at",
            _normalize_optional_int(self.expires_at, field_name="expires_at"),
        )
        object.__setattr__(
            self,
            "token_type",
            _normalize_token_type(self.token_type, field_name="token_type"),
        )
        object.__setattr__(
            self,
            "scopes",
            _normalize_values(self.scopes, field_name="scopes"),
        )
        object.__setattr__(
            self,
            "metadata",
            _normalize_mapping(self.metadata, field_name="metadata"),
        )

    def is_valid(
        self,
        *,
        now: int | None = None,
        refresh_margin_seconds: int = 300,
    ) -> bool:
        """Return whether the access token can be used without refresh."""
        if not self.access_token:
            return False
        if self.expires_at is None:
            return True
        current_time = int(time.time()) if now is None else now
        return self.expires_at > current_time + refresh_margin_seconds

    def to_dict(self) -> dict[str, Any]:
        """Serialize token data for SecretManager storage."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "scopes": list(self.scopes),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OAuthTokenSet":
        """Build a token set from SecretManager storage."""
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("Stored OAuth token set is missing access_token.")

        expires_at = _normalize_optional_int(
            payload.get("expires_at"),
            field_name="Stored OAuth token set expires_at",
        )

        refresh_token = _normalize_optional(
            payload.get("refresh_token"),
            field_name="Stored OAuth token set refresh_token",
        )

        try:
            scopes = _normalize_values(
                payload.get("scopes"),
                field_name="Stored OAuth token set scopes",
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        metadata = {}
        if "metadata" in payload:
            metadata = _normalize_mapping(
                payload["metadata"],
                field_name="Stored OAuth token set metadata",
                allow_none=False,
            )

        token_type = "Bearer"
        if "token_type" in payload:
            token_type = _normalize_token_type(
                payload["token_type"],
                field_name="Stored OAuth token set token_type",
            )

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_type=token_type,
            scopes=scopes,
            metadata=metadata,
        )


@dataclass(frozen=True)
class OAuthCredential:
    """Resolved credential returned to callers."""

    access_token: str
    provider: str
    connection_id: str
    credential_key: str
    source: str
    token_type: str = "Bearer"
    expires_at: int | None = None
    scopes: Sequence[str] = field(default_factory=tuple)


def build_oauth_credential_key(request: OAuthRequest) -> str:
    """Build a stable, non-secret credential key for an OAuth request."""
    provider_label = "".join(
        char if char.isalnum() else "_"
        for char in request.provider.lower()
    ).strip("_") or "oauth"
    material = {
        "provider": request.provider,
        "connection_id": request.connection_id,
        "scopes": list(request.scopes),
        "subject": request.subject,
        "storage_context": request.storage_context,
    }
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:32]
    return f"{provider_label}_{digest}"
