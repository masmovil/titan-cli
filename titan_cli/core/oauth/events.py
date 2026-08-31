"""Provider-neutral OAuth events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from threading import Lock
from types import MappingProxyType
from typing import Any, Protocol

REDACTED_METADATA_VALUE = "<redacted>"
SAFE_EVENT_MESSAGES = frozenset(
    {
        "",
        "Resolving OAuth credential.",
        "OAuth credential resolved.",
        "OAuth refresh provider is not registered.",
        "OAuth authorization provider is not registered.",
        "OAuth authentication is required.",
        "OAuth credential lock acquired.",
        "Refreshing OAuth credential.",
        "OAuth refresh failed.",
        "Stale OAuth credential could not be deleted.",
        "Deleted stale OAuth credential after refresh failure.",
        "OAuth refreshed credential could not be saved.",
        "Starting OAuth authorization.",
        "OAuth authorization failed.",
        "OAuth authorized credential could not be saved.",
        "OAuth credential could not be saved.",
        "OAuth credential saved.",
    }
)
SAFE_METADATA_KEYS = frozenset({"source", "phase", "secret_key"})
SENSITIVE_METADATA_KEYS = frozenset(
    {
        "access_token",
        "authorization",
        "client_secret",
        "credential",
        "id_token",
        "refresh_token",
        "secret",
        "token",
    }
)


@dataclass(frozen=True)
class OAuthEvent:
    """A safe OAuth lifecycle event.

    Events must never include raw access tokens or refresh tokens.
    """

    type: str
    operation_id: str
    credential_key: str | None = None
    provider: str | None = None
    connection_id: str | None = None
    message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _sanitize_event_text(self.type))
        object.__setattr__(
            self,
            "operation_id",
            _sanitize_event_text(self.operation_id),
        )
        object.__setattr__(
            self,
            "credential_key",
            _sanitize_optional_event_text(self.credential_key),
        )
        object.__setattr__(
            self,
            "provider",
            _sanitize_optional_event_text(self.provider),
        )
        object.__setattr__(
            self,
            "connection_id",
            _sanitize_optional_event_text(self.connection_id),
        )
        object.__setattr__(self, "message", _sanitize_event_message(self.message))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


class OAuthEventSink(Protocol):
    """Receives OAuth lifecycle events."""

    def emit(self, event: OAuthEvent) -> None:
        """Handle an OAuth event."""


class NullOAuthEventSink:
    """Event sink that intentionally discards every OAuth event."""

    def emit(self, event: OAuthEvent) -> None:
        """Discard an OAuth event."""


class CollectingOAuthEventSink:
    """Event sink useful for tests and headless callers."""

    def __init__(self) -> None:
        self.events: list[OAuthEvent] = []

    def emit(self, event: OAuthEvent) -> None:
        """Record an OAuth event."""
        self.events.append(event)


class QueuedOAuthEventSink:
    """Thread-safe queue-backed sink for runtime event dispatchers."""

    def __init__(self, maxsize: int = 0) -> None:
        self.queue: Queue[OAuthEvent] = Queue(maxsize=maxsize)
        self._dropped_count = 0
        self._dropped_count_lock = Lock()

    def emit(self, event: OAuthEvent) -> None:
        """Queue an OAuth event without allowing overflow to abort OAuth."""
        try:
            self.queue.put_nowait(event)
        except Full:
            self._record_dropped_event()

    @property
    def dropped_count(self) -> int:
        """Return how many events were dropped because the queue was full."""
        with self._dropped_count_lock:
            return self._dropped_count

    def get(
        self,
        *,
        block: bool = True,
        timeout: float | None = None,
    ) -> OAuthEvent | None:
        """Return the next queued event, or None when no event is available."""
        try:
            if not block:
                return self.queue.get(block=False)
            return self.queue.get(block=block, timeout=timeout)
        except Empty:
            return None

    def drain(self) -> list[OAuthEvent]:
        """Return all currently queued events."""
        events = []
        while True:
            event = self.get(block=False)
            if event is None:
                return events
            events.append(event)

    def _record_dropped_event(self) -> None:
        """Record a dropped event without blocking the OAuth flow."""
        with self._dropped_count_lock:
            self._dropped_count += 1


def _freeze_metadata(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return an immutable metadata snapshot for emitted events."""
    if not value:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("OAuth event metadata must be a mapping.")

    safe_metadata = {}
    for key, item in value.items():
        key_label = str(key)
        if key_label in SAFE_METADATA_KEYS:
            safe_metadata[key_label] = _freeze_safe_metadata_value(key_label, item)
            continue
        if _is_sensitive_metadata_key(key_label):
            safe_metadata[key_label] = REDACTED_METADATA_VALUE
            continue
    return MappingProxyType(safe_metadata)


def _freeze_safe_metadata_value(key: str, value: Any) -> Any:
    """Freeze a whitelisted metadata value after key-specific validation."""
    if key == "source":
        return value if _is_safe_source_value(value) else REDACTED_METADATA_VALUE
    if key == "phase":
        return value if value == "storage" else REDACTED_METADATA_VALUE
    if key == "secret_key":
        return value if _is_safe_secret_key_value(value) else REDACTED_METADATA_VALUE
    return REDACTED_METADATA_VALUE


def _sanitize_event_message(value: Any) -> str:
    """Return a lifecycle-safe event message."""
    if not isinstance(value, str):
        raise ValueError("OAuth event message must be a string.")
    stripped = value.strip()
    if stripped in SAFE_EVENT_MESSAGES:
        return stripped
    return REDACTED_METADATA_VALUE


def _sanitize_optional_event_text(value: Any) -> str | None:
    """Sanitize an optional event field."""
    if value is None:
        return None
    return _sanitize_event_text(value)


def _sanitize_event_text(value: Any) -> str:
    """Sanitize a required event field."""
    if not isinstance(value, str):
        raise ValueError("OAuth event fields must be strings.")
    stripped = value.strip()
    if _contains_sensitive_text(stripped):
        return REDACTED_METADATA_VALUE
    return stripped


def _contains_sensitive_text(value: str) -> bool:
    """Return whether text advertises token or authorization material."""
    lowered = value.lower()
    return any(marker in lowered for marker in SENSITIVE_METADATA_KEYS)


def _is_safe_source_value(value: Any) -> bool:
    """Return whether a source metadata value is a non-secret source label."""
    if not isinstance(value, str):
        return False
    if value in {"oauth-cache", "oauth-refresh", "oauth-login"}:
        return True
    for prefix in ("env:", "project:", "keyring:"):
        if not value.startswith(prefix):
            continue
        label = value.removeprefix(prefix)
        return _is_safe_identifier(label)
    return _is_env_var_name(value)


def _is_safe_secret_key_value(value: Any) -> bool:
    """Return whether a stored secret key label is safe to expose."""
    return isinstance(value, str) and value.startswith("oauth_") and _is_safe_identifier(
        value
    )


def _is_env_var_name(value: str) -> bool:
    """Return whether a value looks like an environment variable name."""
    return bool(value) and all(
        char.isupper() or char.isdigit() or char == "_" for char in value
    )


def _is_safe_identifier(value: str) -> bool:
    """Return whether a label contains only non-structural identifier characters."""
    return bool(value) and all(
        char.isalnum() or char in {"_", "-", ".", ":"} for char in value
    )


def _is_sensitive_metadata_key(key: object) -> bool:
    """Return whether a metadata key may carry OAuth token material."""
    lowered = str(key).lower()
    return any(marker in lowered for marker in SENSITIVE_METADATA_KEYS)
