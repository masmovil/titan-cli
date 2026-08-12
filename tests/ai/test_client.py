import pytest
from unittest.mock import MagicMock

from titan_cli.ai.client import AIClient
from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.core.models import AIConfig, AIConnectionType, AIProviderConfig
from titan_cli.core.secrets import SecretManager


@pytest.fixture
def mock_ai_config_single_connection():
    """Returns an AIConfig with one connection and it as default."""
    return AIConfig(
        default_connection="test_connection",
        connections={
            "test_connection": AIProviderConfig(
                name="Test Connection",
                connection_type=AIConnectionType.DIRECT_PROVIDER,
                provider="anthropic",
                default_model="claude-sonnet",
            )
        },
    )


@pytest.fixture
def mock_ai_config_multiple_connections():
    """Returns an AIConfig with multiple connections and a default."""
    return AIConfig(
        default_connection="default_gemini",
        connections={
            "default_gemini": AIProviderConfig(
                name="Default Gemini",
                connection_type=AIConnectionType.DIRECT_PROVIDER,
                provider="gemini",
                default_model="gemini-pro",
            ),
            "secondary_anthropic": AIProviderConfig(
                name="Secondary Anthropic",
                connection_type=AIConnectionType.DIRECT_PROVIDER,
                provider="anthropic",
                default_model="claude-3",
            ),
        },
    )


@pytest.fixture
def mock_secret_manager():
    """Returns a mock SecretManager."""
    sm = MagicMock(spec=SecretManager)
    sm.get.return_value = "mock_api_key"
    return sm


def test_aiclient_init_specific_connection(
    mock_ai_config_multiple_connections, mock_secret_manager
):
    """Test AIClient initializes with a specific connection_id."""
    client = AIClient(
        ai_config=mock_ai_config_multiple_connections,
        secrets=mock_secret_manager,
        connection_id="secondary_anthropic",
    )
    current_connection_cfg = client.ai_config.connections.get(client.connection_id)
    assert current_connection_cfg.name == "Secondary Anthropic"
    assert current_connection_cfg.provider == "anthropic"


def test_aiclient_init_default_connection(
    mock_ai_config_multiple_connections, mock_secret_manager
):
    """Test AIClient initializes with the default connection when no connection_id is given."""
    client = AIClient(
        ai_config=mock_ai_config_multiple_connections,
        secrets=mock_secret_manager,
    )
    current_connection_cfg = client.ai_config.connections.get(client.connection_id)
    assert current_connection_cfg.name == "Default Gemini"
    assert current_connection_cfg.provider == "gemini"


def test_aiclient_init_fallback_default_not_exist_fails():
    """
    A default connection that does not exist is reported when something tries to use it,
    not when the config loads - loading must never be what stops Titan from starting.
    """
    ai_config = AIConfig(
        default_connection="non_existent",
        connections={
            "some_connection": AIProviderConfig(
                name="Some Connection",
                connection_type=AIConnectionType.DIRECT_PROVIDER,
                provider="openai",
                default_model="gpt-3.5",
            )
        },
    )

    with pytest.raises(AIConfigurationError):
        AIClient(ai_config, MagicMock())


def test_aiclient_init_invalid_connection_id_is_refused_by_name(
    mock_ai_config_multiple_connections, mock_secret_manager
):
    """
    Asking for a connection that does not exist must say so, not quietly answer with a
    different one - the prompts would go somewhere the user never chose, unnoticed.
    """
    with pytest.raises(AIConfigurationError, match="non_existent_connection"):
        AIClient(
            ai_config=mock_ai_config_multiple_connections,
            secrets=mock_secret_manager,
            connection_id="non_existent_connection",
        )


def test_aiclient_no_connections_configured():
    """Test AIClient raises AIConfigurationError if no connections are configured."""
    ai_config_no_connections = AIConfig(connections={})
    with pytest.raises(AIConfigurationError, match="No AI connections configured."):
        AIClient(
            ai_config=ai_config_no_connections,
            secrets=MagicMock(spec=SecretManager),
        )
