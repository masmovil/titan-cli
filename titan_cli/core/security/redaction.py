"""
Global redaction registry for secret values.

Every time the vault dereferences a secret, the value lands here so that any
outbound text (logs, UI, command echoes, subprocess output) can be filtered
through `redact()`. This is defense in depth, not a security boundary: code
that never receives a secret cannot leak it, redaction only covers the paths
where a secret legitimately flows (e.g. a subprocess that echoes its input).
"""

import threading

REDACTED = "[REDACTED]"

# Values shorter than this are not registered: redacting a 1-3 char fragment
# would shred unrelated text far more often than it would hide a real secret.
_MIN_LENGTH = 4

_lock = threading.Lock()
_secrets: set[str] = set()


def register_secret(value: str) -> None:
    """Record a secret value so `redact()` masks it from now on."""
    if not value or len(value) < _MIN_LENGTH:
        return
    with _lock:
        _secrets.add(value)


def redact(text: str) -> str:
    """Return `text` with every registered secret replaced by a marker."""
    if not text:
        return text
    with _lock:
        # Longest first, so a secret that contains another is masked whole.
        known = sorted(_secrets, key=len, reverse=True)
    for value in known:
        if value in text:
            text = text.replace(value, REDACTED)
    return text


def clear_registry() -> None:
    """Empty the registry. For tests only."""
    with _lock:
        _secrets.clear()
