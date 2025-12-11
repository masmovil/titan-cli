import pytest
from unittest.mock import MagicMock
from titan_cli.ai.models import AIMessage, AIRequest, AIResponse
from titan_cli.ai.providers import AnthropicProvider
from titan_cli.ai.exceptions import AIProviderError

# Mock for the actual client library (e.g., Anthropic's client)
class MockAnthropicClient:
    def __init__(self, base_url="https://api.anthropic.com"):
        self.base_url = base_url
        self.messages = MagicMock() # Make messages an object

        # Define the create method on the messages mock object
        def mock_create(**kwargs):
            # Check for error condition within the messages passed to create
            for msg in kwargs.get("messages", []):
                if "error" in msg.get("content", "").lower():
                    raise Exception("Mock Anthropic Error")

            # Simulate messages.create response structure
            mock_message = MagicMock()
            mock_message.content = [MagicMock(text="Mocked Anthropic Response")]
            mock_message.model = kwargs.get("model", "claude-sonnet")
            mock_message.usage = MagicMock(input_tokens=10, output_tokens=20)
            mock_message.stop_reason = "end_turn"
            return mock_message
        
        self.messages.create.side_effect = mock_create

@pytest.fixture
def mock_anthropic_client_lib(mocker):
    """Mocks the anthropic client library."""
    # Mock the Anthropic client constructor
    mock_client_class = mocker.patch("anthropic.Anthropic")
    mock_client_instance = MockAnthropicClient()
    mock_client_class.return_value = mock_client_instance
    return mock_client_class

@pytest.fixture
def mock_anthropic_provider_config():
    """Returns a basic configuration for AnthropicProvider."""
    return {
        "api_key": "test_api_key",
        "model": "claude-sonnet",
    }

def test_anthropic_base_url_normalization(mock_anthropic_client_lib, mock_anthropic_provider_config):
    """Test that base_url automatically removes trailing slashes."""
    config_with_slash = {**mock_anthropic_provider_config, "base_url": "https://custom.anthropic.com/"}
    provider_with_slash = AnthropicProvider(**config_with_slash)
    mock_anthropic_client_lib.assert_called_with(api_key="test_api_key", base_url="https://custom.anthropic.com")

    config_no_slash = {**mock_anthropic_provider_config, "base_url": "https://custom.anthropic.com"}
    provider_no_slash = AnthropicProvider(**config_no_slash)
    mock_anthropic_client_lib.assert_called_with(api_key="test_api_key", base_url="https://custom.anthropic.com")


def test_anthropic_custom_endpoint_usage(mock_anthropic_client_lib, mock_anthropic_provider_config):
    """Test that the Anthropic client uses a custom endpoint when provided."""
    custom_base_url = "https://my.private.anthropic.org"
    config = {**mock_anthropic_provider_config, "base_url": custom_base_url}
    provider = AnthropicProvider(**config)
    mock_anthropic_client_lib.assert_called_once_with(api_key="test_api_key", base_url=custom_base_url)


def test_anthropic_official_endpoint_usage(mock_anthropic_client_lib, mock_anthropic_provider_config):
    """Test that the Anthropic client uses the official endpoint by default (no custom base_url)."""
    provider = AnthropicProvider(**mock_anthropic_provider_config)
    # When no base_url is provided, it should only pass api_key
    mock_anthropic_client_lib.assert_called_once_with(api_key="test_api_key")


def test_anthropic_generate_response_with_custom_endpoint(mock_anthropic_client_lib, mock_anthropic_provider_config):
    """Test response generation using a custom endpoint."""
    custom_base_url = "https://my.private.anthropic.org"
    config = {**mock_anthropic_provider_config, "base_url": custom_base_url}
    provider = AnthropicProvider(**config)

    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
    response = provider.generate(request)

    assert isinstance(response, AIResponse)
    assert response.content == "Mocked Anthropic Response"
    mock_anthropic_client_lib.return_value.messages.create.assert_called_once()


def test_anthropic_generate_error_handling(mock_anthropic_client_lib, mock_anthropic_provider_config):
    """Test error handling during response generation."""
    provider = AnthropicProvider(**mock_anthropic_provider_config)
    request = AIRequest(messages=[AIMessage(role="user", content="error")])

    with pytest.raises(AIProviderError, match="Anthropic API error: Mock Anthropic Error"):
        provider.generate(request)
