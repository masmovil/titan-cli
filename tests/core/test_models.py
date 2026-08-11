import pytest
from pydantic import ValidationError

from titan_cli.core.models import (
    AIConfig,
    AIConnectionConfig,
    AIConnectionType,
    AIDirectProvider,
    AIGatewayBackend,
)


def test_aiconnectionconfig_direct_provider_full_fields():
    """Test a direct provider connection with all supported fields."""
    config = AIConnectionConfig(
        name="Test Provider",
        connection_type=AIConnectionType.DIRECT_PROVIDER,
        provider="anthropic",
        default_model="claude-sonnet",
        base_url="https://api.example.com",
        temperature=0.5,
        max_tokens=1024,
    )
    assert config.name == "Test Provider"
    assert config.connection_type == AIConnectionType.DIRECT_PROVIDER
    assert config.provider == "anthropic"
    assert config.default_model == "claude-sonnet"
    assert config.model == "claude-sonnet"
    assert config.base_url == "https://api.example.com"
    assert config.temperature == 0.5
    assert config.max_tokens == 1024


def test_aiconnectionconfig_gateway_required_fields():
    """Test a gateway connection with only its required fields."""
    config = AIConnectionConfig(
        name="OpenAI Compatible Gateway",
        connection_type=AIConnectionType.GATEWAY,
        gateway_backend=AIGatewayBackend.OPENAI_COMPATIBLE,
        base_url="https://gateway.example.com",
    )
    assert config.name == "OpenAI Compatible Gateway"
    assert config.connection_type == AIConnectionType.GATEWAY
    assert config.gateway_backend == AIGatewayBackend.OPENAI_COMPATIBLE
    assert config.base_url == "https://gateway.example.com"
    assert config.provider is None
    assert config.default_model is None
    assert config.temperature == 0.7
    assert config.max_tokens == 4096


def test_aiconnectionconfig_missing_required_fields():
    """Test AIConnectionConfig raises ValidationError for missing required fields."""
    with pytest.raises(ValidationError, match="name"):
        AIConnectionConfig(
            connection_type=AIConnectionType.DIRECT_PROVIDER,
            provider="anthropic",
            default_model="claude-sonnet",
        )
    with pytest.raises(ValidationError, match="connection_type"):
        AIConnectionConfig(
            name="Bad Provider",
            provider="anthropic",
            default_model="claude-sonnet",
        )
    with pytest.raises(ValidationError, match="provider"):
        AIConnectionConfig(
            name="Bad Provider",
            connection_type=AIConnectionType.DIRECT_PROVIDER,
            default_model="claude-sonnet",
        )


def test_aiconnectionconfig_gateway_rejects_provider():
    """Test gateway connections reject direct provider configuration."""
    with pytest.raises(
        ValidationError, match="gateway connections must not define 'provider'"
    ):
        AIConnectionConfig(
            name="Bad Gateway",
            connection_type=AIConnectionType.GATEWAY,
            gateway_backend=AIGatewayBackend.OPENAI_COMPATIBLE,
            provider=AIDirectProvider.ANTHROPIC,
            base_url="https://gateway.example.com",
        )


def test_aiconnectionconfig_gateway_requires_base_url():
    """Test gateway connections require a base URL."""
    with pytest.raises(
        ValidationError, match="gateway connections require 'base_url'"
    ):
        AIConnectionConfig(
            name="Bad Gateway",
            connection_type=AIConnectionType.GATEWAY,
            gateway_backend=AIGatewayBackend.OPENAI_COMPATIBLE,
            default_model="llama-2-7b",
        )


def test_aiconfig_multiple_connections_and_default():
    """Test AIConfig with multiple connections and a default."""
    config = AIConfig(
        default_connection="corp-gemini",
        connections={
            "corp-gemini": AIConnectionConfig(
                name="Corporate Gemini",
                connection_type=AIConnectionType.DIRECT_PROVIDER,
                provider="gemini",
                default_model="gemini-2.0",
                temperature=0.8,
            ),
            "personal-claude": AIConnectionConfig(
                name="Personal Claude",
                connection_type=AIConnectionType.DIRECT_PROVIDER,
                provider="anthropic",
                default_model="claude-3",
                max_tokens=4096,
            ),
        },
    )
    assert config.default_connection == "corp-gemini"
    assert config.default == "corp-gemini"
    assert "corp-gemini" in config.connections
    assert "personal-claude" in config.providers

    corp_gemini = config.connections["corp-gemini"]
    assert corp_gemini.name == "Corporate Gemini"
    assert corp_gemini.provider == "gemini"
    assert corp_gemini.temperature == 0.8

    personal_claude = config.providers["personal-claude"]
    assert personal_claude.name == "Personal Claude"
    assert personal_claude.provider == "anthropic"
    assert personal_claude.max_tokens == 4096


def test_aiconfig_no_connections():
    """Test AIConfig with no connections."""
    config = AIConfig(connections={})
    assert config.default_connection is None
    assert config.default is None
    assert not config.connections
    assert not config.providers


def test_aiconfig_default_not_in_connections_still_loads():
    """
    A default pointing at a connection that no longer exists - renamed by hand, say - must
    not stop the config from loading. Refusing here makes the application unstartable, and
    the only screen that could repair the value lives inside it. Resolution reports it
    instead, by name, with the app running.
    """
    config = AIConfig(
        default_connection="non-existent",
        connections={
            "corp-gemini": AIConnectionConfig(
                name="Corporate Gemini",
                connection_type=AIConnectionType.DIRECT_PROVIDER,
                provider="gemini",
                default_model="gemini-2.0",
            )
        },
    )

    assert config.default_connection == "non-existent"
    assert "non-existent" not in config.connections


def test_aiconfig_empty_connections_with_default_still_loads():
    config = AIConfig(default_connection="some-default", connections={})

    assert config.default_connection == "some-default"
