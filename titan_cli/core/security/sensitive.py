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

from typing import Any

from .redaction import register_secret

# Container string leaves shorter than this are not registered for
# redaction: below it live generic JSON values ("service_account", brand
# names) whose global redaction would mangle unrelated text.
_CONTAINER_LEAF_MIN_LENGTH = 16


def _register_payload(value: Any) -> None:
    if isinstance(value, str):
        register_secret(value)
    elif isinstance(value, bytes):
        try:
            register_secret(value.decode("utf-8"))
        except UnicodeDecodeError:
            pass
    elif isinstance(value, dict):
        for leaf in value.values():
            _register_container_leaf(leaf)
    elif isinstance(value, (list, tuple, set)):
        for leaf in value:
            _register_container_leaf(leaf)


def _register_container_leaf(leaf: Any) -> None:
    if isinstance(leaf, str):
        if len(leaf) >= _CONTAINER_LEAF_MIN_LENGTH:
            register_secret(leaf)
    else:
        _register_payload(leaf)


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

    def __repr__(self) -> str:
        return "SensitiveValue([REDACTED])"

    def __str__(self) -> str:
        return self.__repr__()

    def __getstate__(self):
        raise TypeError("SensitiveValue is not serializable")

    def __reduce__(self):
        raise TypeError("SensitiveValue is not serializable")
