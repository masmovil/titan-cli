"""
Public secrets API for everything outside the trust boundary.

`SecretBroker` is what steps, plugins, and screens receive. It is created by
core with a namespace derived from the registered plugin/step identity — the
caller never chooses its own namespace — and it deliberately has no read
method: a secret can be stored, checked, or deleted, but the value itself
only ever leaves the boundary as an *effect* (an authenticated session, a
subprocess stdin, a scoped tempfile — see sessions.py and the use-primitives).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from .redaction import register_secret

if TYPE_CHECKING:
    from ._vault import SecretManager

# Asks the user for a secret (the argument is the prompt to display) and
# returns what they typed, or None if they cancelled. Wired by core to the
# active UI; kept as a plain callable so this module stays UI-free.
Prompter = Callable[[str], Optional[str]]


def derive_namespace(plugin_name: Optional[str]) -> str:
    """
    Keyring namespace for a registered plugin/step identity.

    Derived here, inside the boundary, from the identity the executor read
    off the workflow definition — never accepted as free input from the
    code that will use the broker.
    """
    if not plugin_name or plugin_name == "core":
        return "titan.core"
    if plugin_name in ("project", "user"):
        return f"titan.{plugin_name}"
    return f"titan.plugins.{plugin_name}"


class SecretRef:
    """
    Opaque handle to a stored secret.

    Carries only the namespace and key — never the value. It cannot be
    pickled, deep-copied, or JSON-serialized, so it cannot end up in
    `ctx.data`, result metadata, logs, or any persisted state by accident.
    """

    __slots__ = ("namespace", "key")

    def __init__(self, namespace: str, key: str):
        self.namespace = namespace
        self.key = key

    def __repr__(self) -> str:
        return f"SecretRef({self.namespace}:{self.key})"

    def __str__(self) -> str:
        return self.__repr__()

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, SecretRef)
            and self.namespace == other.namespace
            and self.key == other.key
        )

    def __hash__(self) -> int:
        return hash((self.namespace, self.key))

    def __getstate__(self):
        raise TypeError("SecretRef is not serializable")

    def __reduce__(self):
        raise TypeError("SecretRef is not serializable")


class SecretBroker:
    """
    Namespace-scoped secret management without read access.

    Created by core with the namespace already derived from the plugin/step
    identity. There is deliberately no `get()`/`list()` — consumers that need
    the value use a session factory or a use-primitive instead.
    """

    def __init__(
        self,
        vault: "SecretManager",
        namespace: str,
        prompter: Optional[Prompter] = None,
    ):
        self._vault = vault
        self._namespace = namespace
        self._prompter = prompter

    @property
    def namespace(self) -> str:
        return self._namespace

    def exists(self, key: str) -> bool:
        """Whether a value for `key` is resolvable in this namespace."""
        return self._vault.get(key, namespace=self._namespace) is not None

    def prompt_and_store(self, key: str, prompt: str) -> Optional[SecretRef]:
        """
        Ask the user for a secret, store it in the user keyring, and return
        an opaque ref. Returns None if the user cancelled the prompt.
        """
        if self._prompter is None:
            raise RuntimeError(
                "This SecretBroker has no prompter wired; it cannot ask the "
                "user for a secret here."
            )
        value = self._prompter(prompt)
        if not value:
            return None
        self._vault.set(key, value, namespace=self._namespace, scope="user")
        register_secret(value)
        return SecretRef(self._namespace, key)

    def delete(self, key: str) -> None:
        """Delete `key` from the user keyring in this namespace."""
        self._vault.delete(key, namespace=self._namespace, scope="user")


class SecretBrokerFactory:
    """
    Mints namespace-scoped brokers for the workflow executor.

    Holds the vault privately so callers outside the boundary can hand out
    brokers without ever holding the vault themselves. Create one via
    `create_broker_factory()`.
    """

    def __init__(self, vault: "SecretManager", prompter: Optional[Prompter] = None):
        self._vault = vault
        self._prompter = prompter

    def for_plugin(self, plugin_name: Optional[str]) -> SecretBroker:
        """Broker scoped to the namespace derived from `plugin_name`."""
        return SecretBroker(self._vault, derive_namespace(plugin_name), self._prompter)


def create_broker_factory(
    project_path: Optional[Path] = None,
    prompter: Optional[Prompter] = None,
) -> SecretBrokerFactory:
    """
    Build the vault internally and return a factory of scoped brokers.

    This is the only way code outside `core/security/` obtains secret
    capabilities: it receives the factory, never the vault.
    """
    from ._vault import SecretManager

    return SecretBrokerFactory(SecretManager(project_path=project_path), prompter)
