"""
Global redaction registry for secret values.

Every time the vault dereferences a secret, the value lands here so that any
outbound text (logs, UI, command echoes, subprocess output) can be filtered
through `redact()`. This is defense in depth, not a security boundary: code
that never receives a secret cannot leak it, redaction only covers the paths
where a secret legitimately flows (e.g. a subprocess that echoes its input).
"""

import re
import threading
from typing import Optional

REDACTED = "[REDACTED]"

# Values shorter than this are not SUBSTITUTED by redact(): replacing a 1-3
# char fragment would shred unrelated text far more often than it would hide
# a real secret. Detection (`contains_secret`/`find_secret_in`) keeps every
# registered value regardless — a short secret is exactly the cheapest one
# to leak, so the leak check must not lose it to a display heuristic.
_MIN_LENGTH = 4

_lock = threading.Lock()
_secrets: set[str] = set()


def register_secret(value: str) -> None:
    """Record a secret value for detection, and for masking if long enough."""
    # Whitespace-only "values" are never secrets; registering one would make
    # redact() rewrite every matching whitespace run in all output.
    if not value or not value.strip():
        return
    with _lock:
        _secrets.add(value)


def redact(text: str) -> str:
    """Return `text` with every registered secret replaced by a marker."""
    if not text:
        return text
    with _lock:
        # Longest first, so a secret that contains another is masked whole.
        known = sorted(
            (s for s in _secrets if len(s) >= _MIN_LENGTH), key=len, reverse=True
        )
    for value in known:
        if value in text:
            text = text.replace(value, REDACTED)
    return text


# Below this length, bare substring matching over-triggers (a short id like
# "1234" appears inside branch names, versions, hashes), so short values must
# stand alone as a token to count as a hit. Long values keep plain substring
# matching — embedding is exactly the leak being looked for.
_BOUNDARY_MATCH_MAX = 8


def contains_secret(text: str) -> bool:
    """Whether `text` embeds any registered secret value."""
    if not text:
        return False
    with _lock:
        known = tuple(_secrets)
    for value in known:
        if len(value) >= _BOUNDARY_MATCH_MAX:
            if value in text:
                return True
        elif re.search(
            rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])", text
        ):
            return True
    return False


def find_secret_in(obj, _path: str = "", _seen: Optional[set] = None) -> Optional[str]:
    """
    Walk a plain-data structure (dicts/lists/tuples/sets/strings) and return
    the path of the first value embedding a registered secret, or None.

    Opaque containers (`SensitiveValue`, `SecretRef`) are fine wherever they
    appear — they are how sensitive material is *supposed* to travel — so
    anything that isn't plain data is skipped, not inspected. Containers are
    tracked by identity so a self-referencing structure terminates instead of
    turning this guard into a `RecursionError`.
    """
    if isinstance(obj, str):
        return _path or "<value>" if contains_secret(obj) else None
    if isinstance(obj, bytes):
        try:
            return _path or "<value>" if contains_secret(obj.decode("utf-8")) else None
        except UnicodeDecodeError:
            return None
    if isinstance(obj, dict):
        if _seen is None:
            _seen = set()
        if id(obj) in _seen:
            return None
        _seen.add(id(obj))
        for key, value in obj.items():
            # Keys are values too: metadata keyed by a token would otherwise
            # pass the leak check silently. The reported path deliberately
            # omits the key text — the key IS the secret here, and the path
            # ends up in an exception message.
            if isinstance(key, (str, bytes)):
                if find_secret_in(key, "k"):
                    return f"{_path}.<dict key>" if _path else "<dict key>"
            key_path = f"{_path}.{key}" if _path else str(key)
            found = find_secret_in(value, key_path, _seen)
            if found:
                return found
        return None
    if isinstance(obj, (list, tuple, set)):
        if _seen is None:
            _seen = set()
        if id(obj) in _seen:
            return None
        _seen.add(id(obj))
        for i, value in enumerate(obj):
            found = find_secret_in(value, f"{_path}[{i}]", _seen)
            if found:
                return found
        return None

    # Plain objects (dataclasses, Pydantic models, the UI models step
    # metadata usually carries) are walked through their attributes — a raw
    # token inside a model field must not pass just because it is wrapped in
    # an object. The intentionally opaque types (SensitiveValue, SecretRef)
    # use __slots__ and therefore have no __dict__: they stay exempt by
    # construction, not by an allowlist someone must remember to update.
    attrs = getattr(obj, "__dict__", None)
    if isinstance(attrs, dict) and attrs:
        if _seen is None:
            _seen = set()
        if id(obj) in _seen:
            return None
        _seen.add(id(obj))
        type_name = type(obj).__name__
        for name, value in attrs.items():
            attr_path = f"{_path}.{name}" if _path else f"{type_name}.{name}"
            found = find_secret_in(value, attr_path, _seen)
            if found:
                return found
    return None


def clear_registry() -> None:
    """Empty the registry. For tests only."""
    with _lock:
        _secrets.clear()
