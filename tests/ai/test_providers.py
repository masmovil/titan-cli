import pytest
from unittest.mock import patch, MagicMock

# Import the classes to be tested
from titan_cli.ai.providers import AnthropicProvider, GeminiProvider, OpenAIProvider
from titan_cli.ai.models import AIRequest, AIMessage
from titan_cli.ai.exceptions import AIProviderAPIError

# --- Tests for AnthropicProvider ---

@patch('anthropic.Anthropic')
def test_anthropic_provider_generate_success(MockAnthropic):
    """
    Test successful generation with AnthropicProvider.
    """
    # Setup mock
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello from Claude")]
    mock_response.model = "claude-3-5-sonnet-20241022"
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 20
    mock_response.stop_reason = "end_turn"
    mock_client.messages.create.return_value = mock_response
    MockAnthropic.return_value = mock_client

    # Initialize provider
    provider = AnthropicProvider(api_key="test_key")
    
    # Create request
    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
    
    # Generate response
    response = provider.generate(request)
    
    # Assertions
    mock_client.messages.create.assert_called_once()
    assert response.content == "Hello from Claude"
    assert response.model == "claude-3-5-sonnet-20241022"
    assert response.usage["input_tokens"] == 10
    assert response.usage["output_tokens"] == 20

@patch('anthropic.Anthropic')
def test_anthropic_provider_system_prompt(MockAnthropic):
    """
    Test that system prompts are correctly handled by AnthropicProvider.
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Yes, I am a system.")]
    mock_client.messages.create.return_value = mock_response
    MockAnthropic.return_value = mock_client

    provider = AnthropicProvider(api_key="test_key")
    request = AIRequest(messages=[
        AIMessage(role="system", content="You are a helpful assistant."),
        AIMessage(role="user", content="Are you a system?")
    ])
    
    provider.generate(request)
    
    # Assert that 'system' parameter was passed to the API
    called_kwargs = mock_client.messages.create.call_args.kwargs
    assert "system" in called_kwargs
    assert called_kwargs["system"] == "You are a helpful assistant."
    # Assert that the system message is NOT in the 'messages' list
    assert not any(msg.get("role") == "system" for msg in called_kwargs["messages"])

# --- Tests for GeminiProvider ---

@patch('titan_cli.ai.providers.gemini.genai')
@patch('titan_cli.ai.providers.gemini.google.auth')
def test_gemini_provider_generate_success(mock_google_auth, mock_genai):
    """
    Test successful generation with GeminiProvider using an API key.
    """
    # Setup mock
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Hello from Gemini"
    mock_response.usage_metadata = MagicMock(prompt_token_count=15, candidates_token_count=25)
    mock_model.generate_content.return_value = mock_response
    mock_genai.GenerativeModel.return_value = mock_model

    # Initialize provider
    provider = GeminiProvider(api_key="test_key")
    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
    
    # Generate response
    response = provider.generate(request)
    
    # Assertions
    mock_genai.configure.assert_called_with(api_key="test_key")
    mock_model.generate_content.assert_called_once()
    assert response.content == "Hello from Gemini"
    assert response.usage["input_tokens"] == 15
    assert response.usage["output_tokens"] == 25

# --- Tests for OpenAIProvider (Stub) ---

def test_openai_provider_is_stub():
    """
    Test that the OpenAIProvider is a stub and raises an error.
    """
    provider = OpenAIProvider(api_key="test_key")
    request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
    
    with pytest.raises(AIProviderAPIError, match="OpenAI provider is not implemented yet"):
        provider.generate(request)
