"""Tests for LiteLLM/OpenAI-compatible provider."""

import httpx
import pytest
from unittest.mock import Mock, patch

pytest.importorskip("openai")

from openai import APIError, AuthenticationError, RateLimitError

from titan_cli.ai.providers.litellm import LiteLLMProvider
from titan_cli.ai.models import AIMessage, AIRequest
from titan_cli.ai.exceptions import (
    AIProviderAuthenticationError,
    AIProviderRateLimitError,
    AIProviderAPIError,
)


class TestLiteLLMProvider:
    """Test suite for LiteLLMProvider."""

    @staticmethod
    def _make_gateway_client(
        *,
        base_url: str = "http://localhost:4000/v1",
        api_key: str = "sk-placeholder",
        client: Mock | None = None,
    ) -> Mock:
        gateway_client = Mock()
        gateway_client.base_url = base_url
        gateway_client.api_key = api_key
        gateway_client._http_client = httpx.Client(http2=True)
        gateway_client._client = client or Mock()
        gateway_client._client.api_key = api_key
        return gateway_client

    def test_init_with_valid_params(self):
        """Test initialization with valid parameters."""
        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
            api_key="test-key",
        )

        assert provider._base_url == "http://localhost:4000/v1"
        assert provider._model == "gpt-3.5-turbo"
        assert str(provider._client.base_url) == "http://localhost:4000/v1/"

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_init_configures_http2_client(self, mock_litellm_client):
        """Test initialization injects an HTTP/2-capable client."""
        gateway_client = self._make_gateway_client(api_key="test-key")
        mock_litellm_client.return_value = gateway_client

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
            api_key="test-key",
        )

        assert provider._http_client is not None
        assert provider._http_client._transport._pool._http2 is True
        mock_litellm_client.assert_called_once_with(
            base_url="http://localhost:4000",
            api_key="test-key",
        )

    def test_init_without_api_key(self):
        """Test initialization without API key (some endpoints don't need auth)."""
        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="llama-2-7b",
        )

        assert provider._base_url == "http://localhost:4000/v1"
        assert provider._model == "llama-2-7b"
        assert provider._client.api_key == "sk-placeholder"

    def test_init_preserves_existing_path(self):
        """Test initialization preserves explicit API paths."""
        provider = LiteLLMProvider(
            base_url="https://llm.company.com/api/openai",
            model="gpt-3.5-turbo",
        )

        assert provider._base_url == "https://llm.company.com/api/openai"

    def test_init_missing_base_url(self):
        """Test initialization fails without base_url."""
        with pytest.raises(ValueError, match="base_url is required"):
            LiteLLMProvider(
                base_url="",
                model="gpt-3.5-turbo",
            )

    def test_init_missing_model(self):
        """Test initialization fails without model."""
        with pytest.raises(ValueError, match="model is required"):
            LiteLLMProvider(
                base_url="http://localhost:4000",
                model="",
            )

    def test_name_property(self):
        """Test provider name includes base URL."""
        provider = LiteLLMProvider(
            base_url="http://llm.company.com",
            model="custom-model",
        )

        assert "http://llm.company.com" in provider.name

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_generate_success(self, mock_litellm_client):
        """Test successful generation."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        choice = Mock()
        choice.message.content = "Generated response"
        choice.finish_reason = "stop"

        response = Mock()
        response.choices = [choice]
        response.model = "gpt-3.5-turbo"
        response.usage = Mock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

        mock_client.chat.completions.create.return_value = response

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
        )

        request = AIRequest(
            messages=[AIMessage(role="user", content="Hello")],
            max_tokens=100,
            temperature=0.7,
        )

        response = provider.generate(request)

        assert response.content == "Generated response"
        assert response.model == "gpt-3.5-turbo"
        assert response.usage["input_tokens"] == 10
        assert response.usage["output_tokens"] == 20
        assert response.finish_reason == "stop"
        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100,
            temperature=0.7,
            stream=False,
        )

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_generate_includes_optional_params_when_provided(self, mock_litellm_client):
        """Test provider only sends optional params when explicitly provided."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        choice = Mock()
        choice.message.content = "ok"
        choice.finish_reason = "stop"

        response = Mock()
        response.choices = [choice]
        response.model = "gpt-3.5-turbo"
        response.usage = None
        mock_client.chat.completions.create.return_value = response

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
        )

        request = AIRequest(
            messages=[AIMessage(role="user", content="Hello")],
            max_tokens=100,
            temperature=0.7,
        )

        provider.generate(request)

        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100,
            temperature=0.7,
            stream=False,
        )

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_generate_extracts_content_from_structured_message_payload(self, mock_litellm_client):
        """Test gateways that return structured content instead of plain message.content."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        message = Mock()
        message.content = ""
        message.model_dump.return_value = {
            "content": [
                {"type": "text", "text": "Structured response"},
            ]
        }

        choice = Mock()
        choice.message = message
        choice.finish_reason = "stop"
        choice.model_dump.return_value = {"message": message.model_dump.return_value}

        response = Mock()
        response.choices = [choice]
        response.model = "gpt-3.5-turbo"
        response.usage = None

        mock_client.chat.completions.create.return_value = response

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
        )

        request = AIRequest(messages=[AIMessage(role="user", content="Hello")])

        result = provider.generate(request)

        assert result.content == "Structured response"

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_generate_authentication_error(self, mock_litellm_client):
        """Test handling of authentication errors."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        mock_client.chat.completions.create.side_effect = AuthenticationError(
            "Invalid API key",
            response=Mock(),
            body=None,
        )

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
        )

        request = AIRequest(messages=[AIMessage(role="user", content="Hello")])

        with pytest.raises(AIProviderAuthenticationError, match="Authentication failed"):
            provider.generate(request)

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_generate_rate_limit_error(self, mock_litellm_client):
        """Test handling of rate limit errors."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        mock_client.chat.completions.create.side_effect = RateLimitError(
            "Rate limit exceeded",
            response=Mock(),
            body=None,
        )

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
        )

        request = AIRequest(messages=[AIMessage(role="user", content="Hello")])

        with pytest.raises(AIProviderRateLimitError, match="Rate limit exceeded"):
            provider.generate(request)

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_generate_api_error(self, mock_litellm_client):
        """Test handling of general API errors."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        mock_client.chat.completions.create.side_effect = APIError(
            "Server error",
            request=Mock(),
            body=None,
        )

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
        )

        request = AIRequest(messages=[AIMessage(role="user", content="Hello")])

        with pytest.raises(AIProviderAPIError, match="API error"):
            provider.generate(request)

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_validate_api_key_success(self, mock_litellm_client):
        """Test successful API key validation."""
        gateway_client = self._make_gateway_client(api_key="test-key")
        validation_client = self._make_gateway_client(api_key="test-key")
        validation_client.test_connection.return_value = True
        mock_litellm_client.side_effect = [gateway_client, validation_client]

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
            api_key="test-key",
        )

        assert provider.validate_api_key() is True
        assert validation_client.test_connection.called
        assert mock_litellm_client.call_args_list[-1].kwargs == {
            "base_url": "http://localhost:4000/v1",
            "api_key": "test-key",
        }

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_validate_api_key_failure(self, mock_litellm_client):
        """Test failed API key validation."""
        gateway_client = self._make_gateway_client(api_key="bad-key")
        validation_client = self._make_gateway_client(api_key="bad-key")
        validation_client.test_connection.side_effect = AuthenticationError(
            "Invalid API key",
            response=Mock(),
            body=None,
        )
        mock_litellm_client.side_effect = [gateway_client, validation_client]

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
            api_key="bad-key",
        )

        assert provider.validate_api_key() is False

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_validate_api_key_other_error_returns_true(self, mock_litellm_client):
        """Test that non-auth errors in validation still return True."""
        gateway_client = self._make_gateway_client(api_key="test-key")
        validation_client = self._make_gateway_client(api_key="test-key")
        validation_client.test_connection.side_effect = RateLimitError(
            "Rate limit",
            response=Mock(),
            body=None,
        )
        mock_litellm_client.side_effect = [gateway_client, validation_client]

        provider = LiteLLMProvider(
            base_url="http://localhost:4000",
            model="gpt-3.5-turbo",
            api_key="test-key",
        )

        assert provider.validate_api_key() is True

    @staticmethod
    def _successful_completion(model: str = "claude-opus-5"):
        choice = Mock()
        choice.message.content = "Generated response"
        choice.finish_reason = "stop"
        response = Mock()
        response.choices = [choice]
        response.model = model
        response.usage = Mock(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        return response

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_model_refusing_temperature_is_retried_without_it(self, mock_litellm_client):
        """A model that rejects `temperature` still gets its answer, minus the parameter."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        mock_client.chat.completions.create.side_effect = [
            APIError(
                "litellm.BadRequestError: AnthropicException - "
                '{"message":"`temperature` is deprecated for this model."}',
                request=Mock(),
                body=None,
            ),
            self._successful_completion("temp-refuser-1"),
        ]

        provider = LiteLLMProvider(base_url="http://localhost:4000", model="temp-refuser-1")
        request = AIRequest(
            messages=[AIMessage(role="user", content="Hello")],
            temperature=0.7,
        )

        response = provider.generate(request)

        assert response.content == "Generated response"
        assert mock_client.chat.completions.create.call_count == 2
        first, second = mock_client.chat.completions.create.call_args_list
        assert first.kwargs["temperature"] == 0.7
        assert "temperature" not in second.kwargs

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_refusal_is_remembered_so_later_calls_skip_temperature(self, mock_litellm_client):
        """The wasted round trip happens once per model, not once per call."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        mock_client.chat.completions.create.side_effect = [
            APIError(
                "`temperature` is deprecated for this model.", request=Mock(), body=None
            ),
            self._successful_completion("temp-refuser-2"),
            self._successful_completion("temp-refuser-2"),
        ]

        provider = LiteLLMProvider(base_url="http://localhost:4000", model="temp-refuser-2")
        request = AIRequest(
            messages=[AIMessage(role="user", content="Hello")],
            temperature=0.7,
        )

        provider.generate(request)
        provider.generate(request)

        assert mock_client.chat.completions.create.call_count == 3
        assert "temperature" not in mock_client.chat.completions.create.call_args_list[2].kwargs

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_unrelated_bad_request_is_not_retried(self, mock_litellm_client):
        """Only a refusal of `temperature` is retried - anything else surfaces as-is."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)

        mock_client.chat.completions.create.side_effect = APIError(
            "context length exceeded", request=Mock(), body=None
        )

        provider = LiteLLMProvider(base_url="http://localhost:4000", model="temp-refuser-3")
        request = AIRequest(
            messages=[AIMessage(role="user", content="Hello")],
            temperature=0.7,
        )

        with pytest.raises(AIProviderAPIError):
            provider.generate(request)

        assert mock_client.chat.completions.create.call_count == 1

    @patch("titan_cli.ai.providers.litellm.LiteLLMClient")
    def test_known_family_never_sends_temperature(self, mock_litellm_client):
        """A recognized model skips the parameter outright - no failed first call."""
        mock_client = Mock()
        mock_litellm_client.return_value = self._make_gateway_client(client=mock_client)
        mock_client.chat.completions.create.return_value = self._successful_completion()

        provider = LiteLLMProvider(base_url="http://localhost:4000", model="claude-opus-5")
        request = AIRequest(
            messages=[AIMessage(role="user", content="Hello")],
            temperature=0.7,
        )

        provider.generate(request)

        mock_client.chat.completions.create.assert_called_once()
        assert "temperature" not in mock_client.chat.completions.create.call_args.kwargs
