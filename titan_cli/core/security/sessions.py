"""
Authenticated session and provider factories.

The consumer receives a fully constructed, already-authenticated object (an
`AIProvider`, a `requests.Session`) and keeps that; the secret string lives
only inside the factory call. Honest limit, documented in the domain's threat
model: the constructed SDK/session retains the key in its own memory — these
factories remove every Titan-side path to the value, they cannot reach into
an SDK's internals.
"""

from enum import Enum
from pathlib import Path
from typing import Optional

import requests

from ._vault import SecretManager
from .broker import SecretRef, derive_namespace


def _vault_for(project_path: Optional[Path]) -> SecretManager:
    """Vault anchored at the project root when no explicit path is given."""
    from titan_cli.core.utils import find_project_root

    return SecretManager(project_path=project_path or find_project_root())

# The AI subsystem is app-level, not a plugin: its keys live under the core
# scope. Reads that miss here fall back to the legacy service names inside
# the vault and migrate lazily.
_AI_NAMESPACE = derive_namespace("core")


def create_ai_provider(
    connection_id: str,
    connection_cfg,
    project_path: Optional[Path] = None,
):
    """
    Build the `AIProvider` for an AI connection, dereferencing its API key
    inside the boundary.

    Drop-in for the key-handling half of `AIClient.provider`: same key naming
    (`{connection_id}_api_key`), same gateway/direct rules, same
    `AIConfigurationError` contract.

    Args:
        connection_id: The connection whose key is read.
        connection_cfg: The connection's `AIConnectionConfig`.
        project_path: Where project secrets are read from; defaults to the
            detected project root (git root, cwd fallback).

    Raises:
        AIConfigurationError: Unknown source type, missing key for a direct
            provider, missing base_url for a gateway, or missing SDK.
    """
    # Imported lazily: titan_cli.ai imports back into core, and this module
    # loads as part of the core.security package.
    from titan_cli.ai.client import get_gateway_classes, get_provider_classes
    from titan_cli.ai.dependencies import get_install_command
    from titan_cli.ai.exceptions import AIConfigurationError
    from titan_cli.core.models import AIConnectionType

    if connection_cfg.connection_type == AIConnectionType.GATEWAY:
        source_name = connection_cfg.gateway_backend.value
        provider_class = get_gateway_classes().get(source_name)
    else:
        source_name = connection_cfg.provider.value
        provider_class = get_provider_classes().get(source_name)

    if not provider_class:
        raise AIConfigurationError(f"Unknown AI source type: {source_name}")

    vault = _vault_for(project_path)
    api_key = vault.get(f"{connection_id}_api_key", namespace=_AI_NAMESPACE)
    # Env vars and .titan/secrets.env can legitimately hold "": a blank key
    # reaching the SDK surfaces as an opaque 401 much later, so treat it as
    # absent here — same rule as create_authenticated_session.
    if api_key is not None and not api_key.strip():
        api_key = None

    if not api_key and connection_cfg.connection_type != AIConnectionType.GATEWAY:
        raise AIConfigurationError(
            f"API key for connection '{connection_id}' ({source_name}) not found."
        )

    if (
        connection_cfg.connection_type == AIConnectionType.GATEWAY
        and not connection_cfg.base_url
    ):
        raise AIConfigurationError(
            f"base_url is required for gateway connection '{connection_id}'"
        )

    if not connection_cfg.default_model or not connection_cfg.default_model.strip():
        # The SDKs fail on a missing model with generic errors that don't
        # name the connection; fail here with the actionable one.
        raise AIConfigurationError(
            f"default_model is required for connection '{connection_id}'"
        )

    kwargs = {"model": connection_cfg.default_model}
    if api_key:
        kwargs["api_key"] = api_key
    if connection_cfg.base_url:
        kwargs["base_url"] = connection_cfg.base_url

    try:
        return provider_class(**kwargs)
    except ImportError as exc:
        install_command = get_install_command(source_name)
        error_message = str(exc).strip()
        install_command_str = " ".join(install_command) if install_command else None
        if install_command_str and install_command_str not in error_message:
            error_message = f"{error_message}\nInstall with: {install_command_str}"
        raise AIConfigurationError(error_message) from exc


class AuthScheme(str, Enum):
    """How the token is presented in the Authorization header."""

    BEARER = "bearer"  # Authorization: Bearer <token>
    TOKEN = "token"    # Authorization: token <token>  (GitHub style)


def create_authenticated_session(
    ref: SecretRef,
    scheme: AuthScheme = AuthScheme.BEARER,
    project_path: Optional[Path] = None,
) -> requests.Session:
    """
    A `requests.Session` pre-authenticated with the secret behind `ref`.

    The caller holds the session, never the token.

    Raises:
        KeyError: If the ref does not resolve to a usable secret (missing,
            empty, or whitespace-only).
        ValueError: If `scheme` is not a recognized auth scheme.
    """
    # AuthScheme is a str enum, so a raw string comparison would silently
    # fall through to "token" for any unrecognized spelling ("Bearer",
    # "BEARER") and send the credential under the wrong scheme. Normalize
    # case, then reject anything unrecognized explicitly.
    if not isinstance(scheme, AuthScheme):
        try:
            scheme = AuthScheme(str(scheme).lower())
        except ValueError as exc:
            raise ValueError(f"Unknown auth scheme: {scheme!r}") from exc

    vault = _vault_for(project_path)
    value = vault.get(ref.key, namespace=ref.namespace)
    if value is None or not value.strip():
        # An empty value would build a session with a bare "Authorization:
        # Bearer " header that looks authenticated and fails as an opaque
        # 401 much later. Only the keyring level filters falsy values; an
        # env var or project-file entry can legitimately be "".
        raise KeyError(f"No secret stored for {ref}")

    prefix = "Bearer" if scheme == AuthScheme.BEARER else "token"
    session = requests.Session()
    session.headers["Authorization"] = f"{prefix} {value}"
    return session
