# tests/core/test_project_init.py
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

from titan_cli.core.project_init import initialize_project
from titan_cli.messages import msg
from titan_cli.core.plugins.plugin_registry import PluginRegistry


@pytest.fixture
def mock_ui_components():
    """Fixture to mock UI components used in initialize_project."""
    with patch('titan_cli.core.project_init.TextRenderer') as mock_text, \
         patch('titan_cli.core.project_init.PromptsRenderer') as mock_prompts:
        
        mock_prompts_instance = MagicMock()
        mock_prompts.return_value = mock_prompts_instance
        
        yield mock_text.return_value, mock_prompts_instance


@pytest.fixture
def mock_registry():
    """Fixture to mock PluginRegistry."""
    # We patch the class to avoid actual discovery
    with patch('titan_cli.core.project_init.PluginRegistry') as mock_registry_class:
        mock_registry_instance = MagicMock(spec=PluginRegistry)
        mock_registry_instance.list_discovered.return_value = ['git', 'github']
        # The class constructor returns our instance
        mock_registry_class.return_value = mock_registry_instance
        yield mock_registry_instance


def test_initialize_project_success(mock_ui_components, mock_registry):
    """
    Test successful project initialization.
    """
    mock_text, mock_prompts = mock_ui_components
    
    # Simulate user input
    mock_prompts.ask_text.return_value = "test-project"
    mock_prompts.ask_choice.return_value = "fullstack"
    
    project_path = Path("/fake/dir/test-project")
    
    # Mock filesystem operations
    with patch('pathlib.Path.mkdir') as mock_mkdir, \
         patch('builtins.open', mock_open()) as mock_file, \
         patch('tomli_w.dump') as mock_tomli_dump:
        
        # We need to mock the registry passed to the function now
        result = initialize_project(project_path, mock_registry)
        
        # Assertions
        assert result is True
        mock_text.title.assert_called_with(msg.Interactive.INIT_PROJECT_TITLE.format(project_name=project_path.name))
        
        # Check prompts
        mock_prompts.ask_text.assert_called_once_with(msg.Prompts.ENTER_NAME, default="test-project")
        mock_prompts.ask_choice.assert_called_once()

        # Check filesystem
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_file.assert_called_once_with(project_path / ".titan" / "config.toml", "wb")
        
        # Check config content for the new plugins table
        expected_config = {
            "project": {
                "name": "test-project",
                "type": "fullstack"
            },
            "plugins": {
                "git": {"enabled": False},
                "github": {"enabled": False}
            }
        }
        mock_tomli_dump.assert_called_once_with(expected_config, mock_file())

        # Check success message
        mock_text.success.assert_called_once_with(msg.Projects.INIT_SUCCESS.format(project_name="test-project", config_path=project_path / ".titan" / "config.toml"))


def test_initialize_project_other_type(mock_ui_components, mock_registry):
    """
    Test successful project initialization with a custom 'other' type.
    """
    mock_text, mock_prompts = mock_ui_components

    # Simulate user input
    mock_prompts.ask_choice.return_value = "other"
    # Set up different return values for multiple calls to ask_text
    mock_prompts.ask_text.side_effect = ["my-custom-project", "super-custom-type"]

    project_path = Path("/fake/dir/my-custom-project")

    with patch('pathlib.Path.mkdir') as mock_mkdir, \
         patch('builtins.open', mock_open()) as mock_file, \
         patch('tomli_w.dump') as mock_tomli_dump:
        
        result = initialize_project(project_path, mock_registry)

        assert result is True
        
        # Check that ask_text was called twice: once for name, once for custom type
        assert mock_prompts.ask_text.call_count == 2
        mock_prompts.ask_text.assert_any_call(msg.Prompts.ENTER_CUSTOM_PROJECT_TYPE)

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

        expected_config = {
            "project": {
                "name": "my-custom-project",
                "type": "super-custom-type"
            },
            "plugins": {
                "git": {"enabled": False},
                "github": {"enabled": False}
            }
        }
        mock_tomli_dump.assert_called_once_with(expected_config, mock_file())


def test_initialize_project_cancelled(mock_ui_components, mock_registry):
    """
    Test project initialization when the user cancels.
    """
    mock_text, mock_prompts = mock_ui_components
    
    # Simulate user cancellation (Ctrl+C)
    mock_prompts.ask_text.side_effect = KeyboardInterrupt
    
    project_path = Path("/fake/dir/cancellable")
    
    result = initialize_project(project_path, mock_registry)
    
    assert result is False
    mock_text.warning.assert_called_with(msg.Projects.INIT_CANCELLED)
