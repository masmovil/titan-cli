"""
Opaque wrapper for sensitive material a plugin derives itself.

The broker's use-primitives protect secrets Titan custodies (keyring/env
values). But a plugin can *derive* new sensitive material from them — a GPG
passphrase decrypts a service-account JSON, for example — and that derived
material never passed through the vault, so nothing registers or guards it.
Protecting the passphrase does not protect what the passphrase unlocked.

`SensitiveValue` is the container for that material: it cannot be pickled,
deep-copied, or JSON-serialized (so it cannot leak into persisted state or
result metadata by accident), its `repr` never shows the payload, and string
payloads are registered for redaction. Access is explicit and greppable:
`.reveal()`.

Honest limits, same class as the rest of this package: this guards against
*accidental* exposure. Code that calls `.reveal()` holds the real value and
can do anything with it — and for container payloads (dicts, lists), only
long string leaves are registered for redaction (registering short generic
fragments like ``"service_account"`` would shred unrelated log output).
"""

from typing import Any, Optional

from .redaction import register_secret

# Container string leaves shorter than this are not registered for
# redaction: below it live generic JSON values ("service_account", brand
# names) whose global redaction would mangle unrelated text.
_CONTAINER_LEAF_MIN_LENGTH = 16


def _register_payload(value: Any, _seen: Optional[set] = None) -> None:
    # A direct str/bytes payload is registered WITHOUT the container length
    # threshold, deliberately: wrapping a bare value in SensitiveValue is an
    # explicit declaration that this exact string is sensitive (a PIN, a
    # short token), so global masking is the requested behavior. The
    # threshold exists for containers, whose leaves are mixed data the
    # caller never individually vouched for.
    if isinstance(value, str):
        register_secret(value)
    elif isinstance(value, bytes):
        text = _decode(value)
        if text is not None:
            register_secret(text)
    elif isinstance(value, dict):
        if _seen is None:
            _seen = set()
        if id(value) in _seen:
            return
        _seen.add(id(value))
        for leaf in value.values():
            _register_container_leaf(leaf, _seen)
    elif isinstance(value, (list, tuple, set)):
        if _seen is None:
            _seen = set()
        if id(value) in _seen:
            return
        _seen.add(id(value))
        for leaf in value:
            _register_container_leaf(leaf, _seen)


def _register_container_leaf(leaf: Any, _seen: set) -> None:
    # The length threshold applies to every container leaf, str or bytes
    # alike — a short generic value must not enter the redaction registry
    # just because it arrived as bytes.
    if isinstance(leaf, str):
        if len(leaf) >= _CONTAINER_LEAF_MIN_LENGTH:
            register_secret(leaf)
    elif isinstance(leaf, bytes):
        text = _decode(leaf)
        if text is not None and len(text) >= _CONTAINER_LEAF_MIN_LENGTH:
            register_secret(text)
    else:
        _register_payload(leaf, _seen)


def _decode(value: bytes) -> Optional[str]:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


class SensitiveValue:
    """
    Opaque handle to sensitive material the holder derived (not vault-stored).

    Safe to keep in `ctx.data` or pass between a plugin's own layers: its
    repr is redacted, and serialization of any kind raises instead of
    leaking. The payload comes back out only through `.reveal()`.
    """

    __slots__ = ("_value",)

    def __init__(self, value: Any):
        object.__setattr__(self, "_value", value)
        _register_payload(value)

    def reveal(self) -> Any:
        """Return the wrapped payload. Deliberate, explicit, greppable."""
        return self._value

    def __setattr__(self, name, attr_value):
        raise AttributeError("SensitiveValue is immutable")

    def __delattr__(self, name):
        raise AttributeError("SensitiveValue is immutable")

    def __repr__(self) -> str:
        return "SensitiveValue([REDACTED])"

    def __str__(self) -> str:
        return self.__repr__()

    def __getstate__(self):
        raise TypeError("SensitiveValue is not serializable")

    def __reduce__(self):
        raise TypeError("SensitiveValue is not serializable")
