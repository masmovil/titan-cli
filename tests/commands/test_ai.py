
import pytest
from unittest.mock import MagicMock, patch
from titan_cli.commands.ai import list_providers, set_default_provider, _test_ai_connection_by_id, configure_ai_interactive
from titan_cli.core.models import TitanConfigModel, AIConfig, AIProviderConfig
from titan_cli.core.config import TitanConfig
from titan_cli.ui.views.prompts import PromptsRenderer

@pytest.fixture
def mock_titan_config(mocker):
    """Mocks the TitanConfig and its nested models."""
    mock_config = MagicMock(spec=TitanConfig)
    mock_config.config = TitanConfigModel(
        ai=AIConfig(
            default="personal-claude",
            providers={
                "personal-claude": AIProviderConfig(
                    name="Personal Claude",
                    type="individual",
                    provider="anthropic",
                    model="claude-3-5-sonnet-20241022",
                ),
                "corporate-gemini": AIProviderConfig(
                    name="Corporate Gemini",
                    type="corporate",
                    provider="gemini",
                    model="gemini-2.0-flash-exp",
                )
            }
        )
    )
    mocker.patch('titan_cli.commands.ai.TitanConfig', return_value=mock_config)
    return mock_config

@pytest.fixture
def mock_prompts(mocker):
    """Mocks the PromptsRenderer."""
    mock_prompts_renderer = MagicMock(spec=PromptsRenderer)
    mocker.patch('titan_cli.commands.ai.PromptsRenderer', return_value=mock_prompts_renderer)
    return mock_prompts_renderer

def test_list_providers(mock_titan_config, capsys):
    """Test the list_providers function."""
    list_providers()
    captured = capsys.readouterr()
    assert "Personal Claude" in captured.out
    assert "Corporate Gemini" in captured.out
    assert "⭐" in captured.out

import tomli
import tomli_w
from typer.testing import CliRunner

# ... (other imports)

@pytest.fixture
def runner():
    return CliRunner()

# ... (other fixtures)

@patch('titan_cli.commands.ai.TitanConfig')
@patch('builtins.open', create=True)
@patch('tomli.load')
@patch('tomli_w.dump')
def test_set_default_provider(mock_dump, mock_load, mock_open, mock_titan_config_class, runner):
    """Test the set_default_provider function."""
    # Setup mock config
    mock_config = mock_titan_config_class.return_value
    mock_config.config = TitanConfigModel(
        ai=AIConfig(
            default="personal-claude",
            providers={
                "personal-claude": AIProviderConfig(name="Personal Claude", type="individual", provider="anthropic", model="claude-3-5-sonnet-20241022"),
                "corporate-gemini": AIProviderConfig(name="Corporate Gemini", type="corporate", provider="gemini", model="gemini-2.0-flash-exp"),
            }
        )
    )

    # Mock the TOML file content
    mock_load.return_value = {
        "ai": {
            "default": "personal-claude",
            "providers": {
                "personal-claude": {"name": "Personal Claude", "type": "individual", "provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
                "corporate-gemini": {"name": "Corporate Gemini", "type": "corporate", "provider": "gemini", "model": "gemini-2.0-flash-exp"},
            }
        }
    }

    # WHEN the command is run non-interactively
    set_default_provider(provider_id="corporate-gemini")

    # THEN the config file should be updated
    mock_dump.assert_called_once()
    saved_config = mock_dump.call_args[0][0]
    assert saved_config["ai"]["default"] == "corporate-gemini"

@patch('titan_cli.commands.ai.AIClient')
def test_test_ai_connection_by_id(mock_ai_client, mock_titan_config, capsys):
    """Test the _test_ai_connection_by_id function."""
    mock_ai_instance = mock_ai_client.return_value
    mock_ai_instance.is_available.return_value = True
    # Simulate a successful connection test
    mock_response = MagicMock()
    mock_response.model = 'claude-3-5-sonnet-20241022'
    mock_response.content = "Hello!"
    mock_ai_instance.generate.return_value = mock_response

    # Prepare arguments for _test_ai_connection_by_id
    secrets = MagicMock()
    ai_config = mock_titan_config.config.ai
    provider_cfg = ai_config.providers["personal-claude"]

    _test_ai_connection_by_id("personal-claude", secrets, ai_config, provider_cfg)

    captured = capsys.readouterr()
    assert "Connection successful" in captured.out
    assert "Model:" in captured.out
    assert "Response:" in captured.out

@patch('titan_cli.commands.ai.TextRenderer')
@patch('titan_cli.commands.ai.SecretManager')
@patch('builtins.open', create=True)
@patch('titan_cli.commands.ai.tomli_w.dump')
@patch('titan_cli.commands.ai.tomli.load')
@patch('titan_cli.commands.ai.PromptsRenderer')
@patch('titan_cli.core.config.TitanConfig')
def test_configure_ai_interactive_duplicate_provider(mock_config_class, mock_prompts_class, mock_load, mock_dump, mock_open, mock_secrets, mock_text_class, capsys):
    """Test configure_ai_interactive with a duplicate provider name."""

    # Setup mocks
    mock_prompts = MagicMock()
    mock_prompts_class.return_value = mock_prompts

    mock_text = MagicMock()
    mock_text_class.return_value = mock_text

    # Mock TitanConfig.GLOBAL_CONFIG to be a Path that exists
    mock_config_path = MagicMock()
    mock_config_path.exists.return_value = True
    mock_config_class.GLOBAL_CONFIG = mock_config_path

    # Mock existing config with a provider
    mock_load.return_value = {
        "ai": {
            "default": "personal-claude",
            "providers": {
                "personal-claude": {
                    "name": "Personal Claude",
                    "type": "individual",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022"
                }
            }
        }
    }

    # User enters a duplicate provider name
    mock_prompts.ask_menu.side_effect = [
        MagicMock(action="individual"),  # Step 1: Type of config
        MagicMock(action="anthropic"),   # Step 3: Provider
    ]

    mock_prompts.ask_text.side_effect = [
        "test-api-key",      # Step 4: API Key
        "claude-3-5-sonnet", # Step 5: Model (inside _select_model)
        "Personal Claude",   # Step 6: Provider name (will generate 'personal-claude' - duplicate!)
    ]

    # Prevent test connection from running
    mock_prompts.ask_confirm.return_value = False

    # WHEN running the interactive configuration
    configure_ai_interactive()

    # THEN an error about the duplicate ID should be shown via TextRenderer
    # Check that text.error was called
    assert mock_text.error.called, "text.error should have been called for duplicate provider"

    # Check the error message contains information about the duplicate
    error_message = mock_text.error.call_args[0][0]
    assert "personal-claude" in error_message and "exists" in error_message.lower(), \
        f"Expected error message about 'personal-claude' existing, got: {error_message}"

    # AND no configuration should be saved (dump should not be called)
    mock_dump.assert_not_called()
