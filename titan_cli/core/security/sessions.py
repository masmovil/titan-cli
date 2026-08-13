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
from .broker import SecretRef


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
        project_path: Where project secrets are read from, defaults to cwd.

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

    vault = SecretManager(project_path=project_path)
    api_key = vault.get(f"{connection_id}_api_key")

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
        KeyError: If the ref does not resolve to a stored secret.
    """
    vault = SecretManager(project_path=project_path)
    value = vault.get(ref.key, namespace=ref.namespace)
    if value is None:
        raise KeyError(f"No secret stored for {ref}")

    prefix = "Bearer" if scheme == AuthScheme.BEARER else "token"
    session = requests.Session()
    session.headers["Authorization"] = f"{prefix} {value}"
    return session
