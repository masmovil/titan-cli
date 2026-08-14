"""Session/provider factories: the caller gets the constructed object, never the key."""

from unittest.mock import patch

import pytest

from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.core.models import (
    AIConnectionConfig,
    AIConnectionType,
    AIDirectProvider,
    AIGatewayBackend,
)
from titan_cli.core.security import (
    AuthScheme,
    SecretRef,
    create_ai_provider,
    create_authenticated_session,
    redaction,
)


@pytest.fixture(autouse=True)
def clean_redaction_registry():
    redaction.clear_registry()
    yield
    redaction.clear_registry()


@pytest.fixture
def keyring_store():
    store = {}
    with patch('keyring.get_password', side_effect=lambda ns, k: store.get((ns, k))), \
         patch('keyring.set_password', side_effect=lambda ns, k, v: store.__setitem__((ns, k), v)), \
         patch('keyring.delete_password', side_effect=lambda ns, k: store.pop((ns, k), None)):
        yield store


class FakeProvider:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def fake_provider_registry():
    with patch('titan_cli.ai.client.get_provider_classes') as direct, \
         patch('titan_cli.ai.client.get_gateway_classes') as gateway:
        direct.return_value = {"anthropic": FakeProvider}
        gateway.return_value = {"openai_compatible": FakeProvider}
        yield


def _direct_cfg():
    return AIConnectionConfig(
        name="Work",
        connection_type=AIConnectionType.DIRECT_PROVIDER,
        provider=AIDirectProvider.ANTHROPIC,
        default_model="claude-sonnet-4-5",
    )


def _gateway_cfg(base_url="https://llm.example.com"):
    return AIConnectionConfig(
        name="Gateway",
        connection_type=AIConnectionType.GATEWAY,
        gateway_backend=AIGatewayBackend.OPENAI_COMPATIBLE,
        base_url=base_url,
        default_model="gpt-5",
    )


# --- create_ai_provider ---

def test_direct_provider_built_with_dereferenced_key(keyring_store, fake_provider_registry, tmp_path):
    keyring_store[("titan", "work_api_key")] = "sk-real-key-value"

    provider = create_ai_provider("work", _direct_cfg(), project_path=tmp_path)

    assert isinstance(provider, FakeProvider)
    assert provider.kwargs["api_key"] == "sk-real-key-value"
    assert provider.kwargs["model"] == "claude-sonnet-4-5"
    # The dereference registered the key for redaction.
    assert redaction.redact("x sk-real-key-value y") == f"x {redaction.REDACTED} y"


def test_direct_provider_missing_key_raises(keyring_store, fake_provider_registry, tmp_path):
    with pytest.raises(AIConfigurationError, match="API key for connection 'work'"):
        create_ai_provider("work", _direct_cfg(), project_path=tmp_path)


def test_gateway_without_key_is_allowed(keyring_store, fake_provider_registry, tmp_path):
    provider = create_ai_provider("gw", _gateway_cfg(), project_path=tmp_path)

    assert isinstance(provider, FakeProvider)
    assert "api_key" not in provider.kwargs
    assert provider.kwargs["base_url"] == "https://llm.example.com"


def test_gateway_requires_base_url(keyring_store, fake_provider_registry, tmp_path):
    cfg = _gateway_cfg()
    cfg.base_url = None
    with pytest.raises(AIConfigurationError, match="base_url is required"):
        create_ai_provider("gw", cfg, project_path=tmp_path)


# --- create_authenticated_session ---

def test_session_carries_bearer_auth(keyring_store, tmp_path):
    keyring_store[("titan.core", "gateway_token")] = "tok_session_value"
    ref = SecretRef("titan.core", "gateway_token")

    session = create_authenticated_session(ref, project_path=tmp_path)

    assert session.headers["Authorization"] == "Bearer tok_session_value"


def test_session_token_scheme(keyring_store, tmp_path):
    keyring_store[("titan.core", "gh_token")] = "ghp_value"
    ref = SecretRef("titan.core", "gh_token")

    session = create_authenticated_session(ref, scheme=AuthScheme.TOKEN, project_path=tmp_path)

    assert session.headers["Authorization"] == "token ghp_value"


def test_session_unresolvable_ref_raises(keyring_store, tmp_path):
    ref = SecretRef("titan.core", "missing")
    with pytest.raises(KeyError, match="titan.core:missing"):
        create_authenticated_session(ref, project_path=tmp_path)


# --- Fixes from the PR #261 review round ---

def test_auth_scheme_accepts_case_insensitive_string(monkeypatch):
    from titan_cli.core.security.sessions import create_authenticated_session
    from titan_cli.core.security.broker import SecretRef
    from unittest.mock import patch

    with patch('keyring.get_password', return_value="tok-value"):
        session = create_authenticated_session(SecretRef("titan.core", "t"), scheme="Bearer")
    assert session.headers["Authorization"] == "Bearer tok-value"


def test_auth_scheme_rejects_unknown_value():
    from titan_cli.core.security.sessions import create_authenticated_session
    from titan_cli.core.security.broker import SecretRef

    with pytest.raises(ValueError):
        create_authenticated_session(SecretRef("titan.core", "t"), scheme="basic")
