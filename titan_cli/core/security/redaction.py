"""
Global redaction registry for secret values.

Every time the vault dereferences a secret, the value lands here so that any
outbound text (logs, UI, command echoes, subprocess output) can be filtered
through `redact()`. This is defense in depth, not a security boundary: code
that never receives a secret cannot leak it, redaction only covers the paths
where a secret legitimately flows (e.g. a subprocess that echoes its input).
"""

import threading
from typing import Optional

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


def contains_secret(text: str) -> bool:
    """Whether `text` embeds any registered secret value."""
    if not text:
        return False
    with _lock:
        known = tuple(_secrets)
    return any(value in text for value in known)


def find_secret_in(obj, _path: str = "") -> Optional[str]:
    """
    Walk a plain-data structure (dicts/lists/tuples/sets/strings) and return
    the path of the first value embedding a registered secret, or None.

    Opaque containers (`SensitiveValue`, `SecretRef`) are fine wherever they
    appear — they are how sensitive material is *supposed* to travel — so
    anything that isn't plain data is skipped, not inspected.
    """
    if isinstance(obj, str):
        return _path or "<value>" if contains_secret(obj) else None
    if isinstance(obj, bytes):
        try:
            return _path or "<value>" if contains_secret(obj.decode("utf-8")) else None
        except UnicodeDecodeError:
            return None
    if isinstance(obj, dict):
        for key, value in obj.items():
            # Keys are values too: metadata keyed by a token would otherwise
            # pass the leak check silently. The reported path deliberately
            # omits the key text — the key IS the secret here, and the path
            # ends up in an exception message.
            if isinstance(key, (str, bytes)):
                if find_secret_in(key, "k"):
                    return f"{_path}.<dict key>" if _path else "<dict key>"
            key_path = f"{_path}.{key}" if _path else str(key)
            found = find_secret_in(value, key_path)
            if found:
                return found
        return None
    if isinstance(obj, (list, tuple, set)):
        for i, value in enumerate(obj):
            found = find_secret_in(value, f"{_path}[{i}]")
            if found:
                return found
        return None
    return None


def clear_registry() -> None:
    """Empty the registry. For tests only."""
    with _lock:
        _secrets.clear()
