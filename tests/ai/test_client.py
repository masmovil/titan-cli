import pytest
from unittest.mock import MagicMock

from titan_cli.core.models import AIConfig, AIProviderConfig
from titan_cli.ai.client import AIClient
from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.core.secrets import SecretManager
from pydantic import ValidationError # Import ValidationError

@pytest.fixture
def mock_ai_config_single_provider():
    """Returns an AIConfig with one provider and it as default."""
    return AIConfig(
        default="test_provider",
        providers={
            "test_provider": AIProviderConfig(
                name="Test Provider",
                type="individual",
                provider="anthropic",
                model="claude-sonnet",
            )
        },
    )

@pytest.fixture
def mock_ai_config_multiple_providers():
    """Returns an AIConfig with multiple providers and a default."""
    return AIConfig(
        default="default_gemini",
        providers={
            "default_gemini": AIProviderConfig(
                name="Default Gemini",
                type="corporate",
                provider="gemini",
                model="gemini-pro",
            ),
            "secondary_anthropic": AIProviderConfig(
                name="Secondary Anthropic",
                type="individual",
                provider="anthropic",
                model="claude-3",
            ),
        },
    )

@pytest.fixture
def mock_secret_manager():
    """Returns a mock SecretManager."""
    sm = MagicMock(spec=SecretManager)
    sm.get.return_value = "mock_api_key"
    return sm

def test_aiclient_init_specific_provider(mock_ai_config_multiple_providers, mock_secret_manager):
    """Test AIClient initializes with a specific provider_id."""
    client = AIClient(
        ai_config=mock_ai_config_multiple_providers,
        secrets=mock_secret_manager,
        provider_id="secondary_anthropic",
    )
    current_provider_cfg = client.ai_config.providers.get(client.provider_id)
    assert current_provider_cfg.name == "Secondary Anthropic"
    assert current_provider_cfg.provider == "anthropic"

def test_aiclient_init_default_provider(mock_ai_config_multiple_providers, mock_secret_manager):
    """Test AIClient initializes with the default provider when no provider_id is given."""
    client = AIClient(
        ai_config=mock_ai_config_multiple_providers,
        secrets=mock_secret_manager,
    )
    current_provider_cfg = client.ai_config.providers.get(client.provider_id)
    assert current_provider_cfg.name == "Default Gemini"
    assert current_provider_cfg.provider == "gemini"

def test_aiclient_init_fallback_default_not_exist_fails():
    """Test AIConfig raises ValidationError if default provider does not exist."""
    with pytest.raises(ValidationError, match="Default provider 'non_existent' not found in configured providers."):
        AIConfig(
            default="non_existent",
            providers={
                "some_provider": AIProviderConfig(
                    name="Some Provider",
                    type="individual",
                    provider="openai",
                    model="gpt-3.5",
                )
            },
        )

def test_aiclient_init_invalid_provider_id_falls_back(mock_ai_config_multiple_providers, mock_secret_manager):
    """Test AIClient falls back to the first available provider when initializing with a non-existent provider_id."""
    client = AIClient(
        ai_config=mock_ai_config_multiple_providers,
        secrets=mock_secret_manager,
        provider_id="non_existent_provider",
    )
    # Expect it to fall back to the first provider (Python 3.7+ dicts maintain insertion order)
    first_provider_id = list(mock_ai_config_multiple_providers.providers.keys())[0]
    assert client.provider_id == first_provider_id
    assert client.provider_id in mock_ai_config_multiple_providers.providers


def test_aiclient_no_providers_configured():
    """Test AIClient raises AIConfigurationError if no providers are configured."""
    ai_config_no_providers = AIConfig(providers={})
    with pytest.raises(AIConfigurationError, match="No AI providers configured."):
        AIClient(ai_config=ai_config_no_providers, secrets=MagicMock(spec=SecretManager))

