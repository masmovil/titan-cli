"""
Public secrets API for everything outside the trust boundary.

`SecretBroker` is what steps, plugins, and screens receive. It is created by
core with a namespace derived from the registered plugin/step identity — the
caller never chooses its own namespace — and it deliberately has no read
method: a secret can be stored, checked, or deleted, but the value itself
only ever leaves the boundary as an *effect* (an authenticated session, a
subprocess stdin, a scoped tempfile — see sessions.py and the use-primitives).
"""

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, TypeVar

from .execution import (
    CANCELLED_RESULT,
    SecureCommandResult,
    build_minimal_env,
    run_redacted,
)
from .redaction import register_secret

if TYPE_CHECKING:
    from ._vault import SecretManager

T = TypeVar("T")

# Asks the user for a secret (the argument is the prompt to display) and
# returns what they typed, or None if they cancelled. Wired by core to the
# active UI; kept as a plain callable so this module stays UI-free.
Prompter = Callable[[str], Optional[str]]


class SecretLeakError(RuntimeError):
    """A use-primitive detected the secret value on its way back out."""


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

    def store(self, key: str, value: str) -> SecretRef:
        """
        Store a value the caller already holds (e.g. typed into a form) and
        return an opaque ref. This is the safe direction — the value flows
        into the boundary; there is still no way to read it back out.

        Raises:
            ValueError: If `value` is empty or whitespace — the vault treats
                a falsy stored value as absent, so accepting it here would
                return a "success" ref that `exists()` then contradicts.
        """
        if not value or not value.strip():
            raise ValueError(f"Refusing to store an empty secret for {self._namespace}:{key}")
        self._vault.set(key, value, namespace=self._namespace, scope="user")
        register_secret(value)
        return SecretRef(self._namespace, key)

    def delete(self, key: str) -> None:
        """Delete `key` from the user keyring in this namespace."""
        self._vault.delete(key, namespace=self._namespace, scope="user")

    def create_client(
        self,
        key: str,
        builder: Callable[[Optional[str]], T],
        required: bool = True,
    ) -> T:
        """
        Build an authenticated client by passing the secret behind `key` to
        `builder`, and return the constructed object — never the value.

        This is how a consumer whose SDK demands the credential at
        construction time (a Slack `WebClient`, a Jira client) gets an
        authenticated instance: the string crosses into the constructor
        inside this call and is registered for redaction on the way. Honest
        limit, same as the session factories: the constructed client retains
        the credential in its own memory.

        The builder's result is checked on the way out: returning the value
        itself, or a str/bytes embedding it, raises instead of leaking. That
        is a guard against sloppy builders (and the trivial identity
        smuggle), not a sandbox — a builder can still hide the value inside
        a container on purpose.

        Args:
            key: The secret to dereference, in this broker's namespace.
            builder: Constructor/callable receiving the value.
            required: When False and the key is unresolvable, `builder`
                is called with None instead of raising.

        Raises:
            KeyError: If `required` and the key does not resolve.
            SecretLeakError: If the builder's result is the value itself or
                a str/bytes containing it.
        """
        value = self._vault.get(key, namespace=self._namespace)
        if value is None and required:
            raise KeyError(f"No secret stored for {self._namespace}:{key}")
        result = builder(value)
        if value is not None:
            leaked = (
                result is value
                or (isinstance(result, str) and value in result)
                or (isinstance(result, bytes) and value.encode() in result)
            )
            if leaked:
                raise SecretLeakError(
                    f"create_client builder for {self._namespace}:{key} returned "
                    "the secret value (or a string containing it) instead of a "
                    "constructed client."
                )
        return result

    # --- Use-primitives: the value crosses into an effect, never back to the
    # --- caller. Output comes back redacted.

    def run_with_secret_stdin(
        self,
        key: str,
        prompt: str,
        command: list[str],
        retry_on_failure: bool = True,
    ) -> SecureCommandResult:
        """
        Run `command` with the secret fed on stdin (e.g. gpg --passphrase-fd 0).

        If the secret is missing, the user is prompted and the value stored.
        If a STORED secret makes the command fail, it is assumed stale: the
        key is deleted, the user re-prompted, and the command retried once
        (`retry_on_failure`). Exit codes 126/127 mean the command itself
        could not run (not found / not executable) — that failure says
        nothing about the credential, so the stored value is kept.
        """
        stored_value = self._vault.get(key, namespace=self._namespace)
        value = stored_value if stored_value is not None else self._prompt_and_save(key, prompt)
        if value is None:
            return CANCELLED_RESULT

        result = run_redacted(command, stdin_value=value)

        if result.exit_code in (126, 127):
            return result

        if not result.succeeded and stored_value is not None and retry_on_failure:
            self.delete(key)
            fresh = self._prompt_and_save(key, prompt)
            if fresh is None:
                return result
            result = run_redacted(command, stdin_value=fresh)

        return result

    def run_with_secret_env(
        self,
        key: str,
        env_var: str,
        command: list[str],
        env_allowlist: Optional[list[str]] = None,
        prompt: Optional[str] = None,
    ) -> SecureCommandResult:
        """
        Run `command` with the secret injected as `env_var` in a MINIMAL
        environment (base allowlist + `env_allowlist`), so the injected
        variable is the only sensitive thing the subprocess can see or dump.
        """
        value = self._resolve(key, prompt)
        if value is None:
            return CANCELLED_RESULT

        env = build_minimal_env(env_allowlist)
        env[env_var] = value
        return run_redacted(command, env=env)

    def with_secret_tempfile(
        self,
        key: str,
        callback: Callable[[Path], T],
        prompt: Optional[str] = None,
    ) -> Optional[T]:
        """
        Write the secret to a 0600 tempfile, call `callback(path)`, and
        delete the file no matter what. For tools that only take key files
        (e.g. gcloud service accounts). Returns the callback's result, or
        None if no secret could be resolved.
        """
        value = self._resolve(key, prompt)
        if value is None:
            return None

        fd, raw_path = tempfile.mkstemp(prefix="titan-secret-")  # mkstemp is 0600
        path = Path(raw_path)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(value)
            return callback(path)
        finally:
            path.unlink(missing_ok=True)

    def _resolve(self, key: str, prompt: Optional[str]) -> Optional[str]:
        """Stored value, or prompt-and-store when a prompt was given."""
        value = self._vault.get(key, namespace=self._namespace)
        if value is not None:
            return value
        if prompt is None:
            return None
        return self._prompt_and_save(key, prompt)

    def _prompt_and_save(self, key: str, prompt: str) -> Optional[str]:
        if self._prompter is None:
            return None
        value = self._prompter(prompt)
        if not value:
            return None
        self._vault.set(key, value, namespace=self._namespace, scope="user")
        register_secret(value)
        return value


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

    def set_prompter(self, prompter: Optional[Prompter]) -> None:
        """
        Wire the UI prompt late. The executor creates this factory before the
        TUI components exist, and gives it the real ask-password once a
        workflow run has a screen to ask on.
        """
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
