import pytest
from unittest.mock import MagicMock, patch
import requests # Import requests
from titan_cli.ai.models import AIMessage, AIRequest, AIResponse
from titan_cli.ai.providers import GeminiProvider
from titan_cli.ai.exceptions import AIProviderError, AIProviderAPIError

# Mock for the actual client library (e.g., Google's genai)
class MockGenerativeModel:
    def __init__(self, model_name, generation_config):
        self.model_name = model_name
        self.generation_config = generation_config

    def generate_content(self, messages_parts, generation_config):
        # Check for our specific error trigger
        if any("error_mock_google" in p for p in messages_parts):
            raise RuntimeError("Mock Gemini GenerativeModel Error") 
        return MagicMock(text="Mocked Gemini Response Text")

    def start_chat(self, history):
        # Mock for chat functionality if needed
        return MagicMock(send_message=lambda parts: MagicMock(text="Mocked Chat Response Text"))

@pytest.fixture
def mock_gemini_client_lib(mocker):
    """Mocks the google.generativeai client library components."""
    # Patch genai.configure globally
    mock_genai_configure = mocker.patch("google.generativeai.configure")

    # Patch GenerativeModel constructor to return a new mock instance each time
    mock_generative_model_class = mocker.patch("google.generativeai.GenerativeModel")
    
    mock_generative_model_instance = MagicMock(spec=MockGenerativeModel)
    mock_generative_model_instance.generate_content.side_effect = MockGenerativeModel("mock", {}).generate_content
    mock_generative_model_instance.start_chat.side_effect = MockGenerativeModel("mock", {}).start_chat
    
    mock_generative_model_class.return_value = mock_generative_model_instance

    return {
        "configure": mock_genai_configure,
        "GenerativeModel": mock_generative_model_class,
        "GenerativeModel_instance": mock_generative_model_instance # For directly checking instance methods
    }


@pytest.fixture
def mock_requests_post(mocker):
    """Mocks requests.post for custom endpoint tests."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"text": "Mocked Custom Endpoint Response Text"}],
        "model": "claude-sonnet", 
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "stop_reason": "end_turn"
    }
    mock_post_patch = mocker.patch("requests.post", return_value=mock_response)
    return mock_post_patch # Return the mocked patch object


@pytest.fixture
def mock_gemini_provider_config():
    """Returns a basic configuration for GeminiProvider."""
    return {
        "api_key": "test_api_key",
        "model": "gemini-pro",
    }

def test_gemini_base_url_normalization(mock_gemini_client_lib, mock_gemini_provider_config, mocker):
    """Test that base_url automatically removes trailing slashes."""
    config_with_slash = {**mock_gemini_provider_config, "base_url": "https://custom.gemini.com/"}
    provider = GeminiProvider(**config_with_slash)
    assert provider.base_url == "https://custom.gemini.com"
    
    # Ensure genai.configure is NOT called when a custom endpoint is used
    mock_gemini_client_lib["configure"].assert_not_called()


def test_gemini_custom_endpoint_usage(mock_gemini_client_lib, mock_gemini_provider_config, mock_requests_post):
    """Test that the Gemini client uses a custom endpoint when provided."""
    custom_base_url = "https://my.private.gemini.org"
    config = {**mock_gemini_provider_config, "base_url": custom_base_url}
    provider = GeminiProvider(**config)

    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
    response = provider.generate(request)

    assert provider.use_custom_endpoint is True
    mock_requests_post.assert_called_once()
    assert mock_requests_post.call_args[0][0] == f"{custom_base_url}/v1/messages"

    # Ensure genai.configure is NOT called when a custom endpoint is used
    mock_gemini_client_lib["configure"].assert_not_called()


def test_gemini_official_endpoint_usage(mock_gemini_client_lib, mock_gemini_provider_config):
    """Test that the Gemini client uses the official endpoint by default (no custom base_url)."""
    provider = GeminiProvider(**mock_gemini_provider_config)

    assert provider.use_custom_endpoint is False
    
    # Ensure genai.configure IS called when official endpoint is used
    mock_gemini_client_lib["configure"].assert_called_once_with(api_key="test_api_key")

    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
    response = provider.generate(request) 

    mock_gemini_client_lib["GenerativeModel_instance"].generate_content.assert_called_once()


def test_gemini_generate_response_with_custom_endpoint(mock_gemini_client_lib, mock_gemini_provider_config, mock_requests_post):
    """Test response generation using a custom endpoint."""
    custom_base_url = "https://my.private.gemini.org"
    config = {**mock_gemini_provider_config, "base_url": custom_base_url}
    provider = GeminiProvider(**config)

    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
    response = provider.generate(request)

    assert isinstance(response, AIResponse)
    assert response.content == "Mocked Custom Endpoint Response Text"
    mock_requests_post.assert_called_once()
    mock_gemini_client_lib["GenerativeModel_instance"].generate_content.assert_not_called()


def test_gemini_generate_error_handling_google_endpoint(mock_gemini_client_lib, mock_gemini_provider_config):
    """Test error handling during response generation for Google endpoint."""
    provider = GeminiProvider(**mock_gemini_provider_config)
    
    # Configure mock to raise a specific error that GeminiProvider's except block will catch
    mock_gemini_client_lib["GenerativeModel_instance"].generate_content.side_effect = RuntimeError("Google API is down")

    request = AIRequest(messages=[AIMessage(role="user", content="error_mock_google")])

    with pytest.raises(AIProviderAPIError, match="Gemini API error: Google API is down"):
        provider.generate(request)

    mock_gemini_client_lib["GenerativeModel_instance"].generate_content.assert_called_once()


def test_gemini_generate_error_handling_custom_endpoint(mock_gemini_provider_config, mock_requests_post):
    """Test error handling during response generation for custom endpoint."""
    custom_base_url = "https://my.private.gemini.org"
    config = {**mock_gemini_provider_config, "base_url": custom_base_url}
    provider = GeminiProvider(**config)

    # Configure mock_requests_post to raise an exception
    mock_requests_post.side_effect = requests.exceptions.RequestException("Network is unreachable")

    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])

    with pytest.raises(AIProviderAPIError, match="Custom endpoint request failed: Network is unreachable"):
        provider.generate(request)

    mock_requests_post.assert_called_once()
