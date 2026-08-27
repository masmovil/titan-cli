"""Tests for AIClient integration with the LiteLLM provider.

AIClient delegates provider construction to the injected factory; these tests
wire the real `create_ai_provider` with a patched vault so they exercise the
same path production uses (key dereference included) without a real keyring.
"""

from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from titan_cli.ai.client import AIClient, get_gateway_classes
from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.core.models import AIConfig, AIConnectionType, AIProviderConfig
from titan_cli.core.security import create_ai_provider


@contextmanager
def stored_api_key(value):
    """Patch the vault inside the security boundary to return `value`."""
    with patch("titan_cli.core.security.sessions.SecretManager") as manager_class:
        manager_class.return_value.get.return_value = value
        yield


def _gateway_config(connection_id, model, base_url):
    return AIConfig(
        default_connection=connection_id,
        connections={
            connection_id: AIProviderConfig(
                name=connection_id,
                connection_type=AIConnectionType.GATEWAY,
                gateway_backend="openai_compatible",
                default_model=model,
                base_url=base_url,
            )
        },
    )


class TestAIClientLiteLLMProvider:
    """Test suite for AIClient with LiteLLM provider."""

    def test_litellm_provider_with_api_key(self):
        """Test LiteLLM provider initialization with API key."""
        ai_config = _gateway_config("custom-llm", "llama-2-7b", "http://localhost:4000")

        client = AIClient(ai_config, create_ai_provider)

        with stored_api_key("test-api-key"), patch(
            "titan_cli.ai.client.LiteLLMProvider"
        ) as mock_provider_class:
            mock_provider = Mock()
            mock_provider_class.return_value = mock_provider

            provider = client.provider

            mock_provider_class.assert_called_once_with(
                model="llama-2-7b",
                api_key="test-api-key",
                base_url="http://localhost:4000",
            )
            assert provider is mock_provider

    def test_litellm_provider_without_api_key(self):
        """Test LiteLLM provider initialization without API key (allowed)."""
        ai_config = _gateway_config("local-llm", "mistral-7b", "http://localhost:8000")

        client = AIClient(ai_config, create_ai_provider)

        with stored_api_key(None), patch(
            "titan_cli.ai.client.LiteLLMProvider"
        ) as mock_provider_class:
            mock_provider = Mock()
            mock_provider_class.return_value = mock_provider

            provider = client.provider

            mock_provider_class.assert_called_once_with(
                model="mistral-7b",
                base_url="http://localhost:8000",
            )
            assert provider is mock_provider

    def test_litellm_provider_missing_base_url(self):
        """Test gateway connection validation fails without base_url."""
        with pytest.raises(
            ValidationError, match="gateway connections require 'base_url'"
        ):
            AIConfig(
                default_connection="bad-gateway",
                connections={
                    "bad-gateway": AIProviderConfig(
                        name="Bad Gateway",
                        connection_type=AIConnectionType.GATEWAY,
                        gateway_backend="openai_compatible",
                        default_model="llama-2-7b",
                    )
                },
            )

    def test_litellm_provider_with_litellm_url(self):
        """Test LiteLLM provider with LiteLLM proxy URL."""
        ai_config = _gateway_config("litellm", "gpt-3.5-turbo", "http://litellm-proxy:4000")

        client = AIClient(ai_config, create_ai_provider)

        with stored_api_key("litellm-master-key"), patch(
            "titan_cli.ai.client.LiteLLMProvider"
        ) as mock_provider_class:
            mock_provider = Mock()
            mock_provider_class.return_value = mock_provider

            provider = client.provider

            mock_provider_class.assert_called_once_with(
                model="gpt-3.5-turbo",
                api_key="litellm-master-key",
                base_url="http://litellm-proxy:4000",
            )
            assert provider is mock_provider

    def test_litellm_provider_registered_in_gateway_classes(self):
        """Test that LiteLLM provider is registered in gateway classes."""
        from titan_cli.ai.providers.litellm import LiteLLMProvider

        assert "openai_compatible" in get_gateway_classes()
        assert get_gateway_classes()["openai_compatible"] == LiteLLMProvider

    def test_litellm_provider_generate(self):
        """Test generate method with LiteLLM provider."""
        ai_config = _gateway_config("gateway", "test-model", "http://localhost:4000")

        client = AIClient(ai_config, create_ai_provider)

        with stored_api_key("test-key"), patch(
            "titan_cli.ai.client.LiteLLMProvider"
        ) as mock_provider_class:
            mock_provider = Mock()
            mock_response = Mock()
            mock_response.content = "Generated text"
            mock_provider.generate.return_value = mock_response
            mock_provider_class.return_value = mock_provider

            from titan_cli.ai.models import AIMessage

            response = client.generate([AIMessage(role="user", content="Hello")])

            assert mock_provider.generate.called
            assert response.content == "Generated text"

    def test_litellm_provider_generate_omits_default_sampling_params(self):
        """Test AIClient does not inject default max_tokens/temperature for gateways."""
        ai_config = _gateway_config("gateway", "test-model", "http://localhost:4000")

        client = AIClient(ai_config, create_ai_provider)

        with stored_api_key("test-key"), patch(
            "titan_cli.ai.client.LiteLLMProvider"
        ) as mock_provider_class:
            mock_provider = Mock()
            mock_response = Mock()
            mock_response.content = "Generated text"
            mock_provider.generate.return_value = mock_response
            mock_provider_class.return_value = mock_provider

            from titan_cli.ai.models import AIMessage

            client.generate([AIMessage(role="user", content="Hello")])

            request_arg = mock_provider.generate.call_args.args[0]
            assert request_arg.max_tokens is None
            assert request_arg.temperature is None

    def test_litellm_provider_missing_dependency_shows_install_command(self):
        """Test missing LiteLLM dependency surfaces an install command."""
        ai_config = _gateway_config("gateway", "test-model", "http://localhost:4000")

        client = AIClient(ai_config, create_ai_provider)

        with stored_api_key("test-key"), patch(
            "titan_cli.ai.client.LiteLLMProvider",
            side_effect=ImportError("No module named 'openai'"),
        ):
            with pytest.raises(AIConfigurationError, match="Install with:"):
                _ = client.provider
