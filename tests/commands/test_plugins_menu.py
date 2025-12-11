import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
import tomli
import tomli_w

from titan_cli.cli import _show_plugin_management_menu
from titan_cli.core.config import TitanConfig
from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.views.prompts import PromptsRenderer

# Mock KNOWN_PLUGINS to isolate the test from the actual file
MOCK_KNOWN_PLUGINS = [
    {
        "name": "git",
        "description": "Git plugin",
        "package_name": "titan-plugin-git"
    },
    {
        "name": "github",
        "description": "GitHub plugin",
        "package_name": "titan-plugin-github"
    },
]

@pytest.fixture
def mock_ui():
    """Fixture for mocking UI components."""
    mock_text = MagicMock(spec=TextRenderer)
    mock_prompts = MagicMock(spec=PromptsRenderer)
    return mock_text, mock_prompts

@pytest.fixture
def mock_config(tmp_path):
    """Fixture for a mock TitanConfig."""
    # Create dummy global and project config files
    global_dir = tmp_path / ".titan"
    global_dir.mkdir()
    global_config_path = global_dir / "config.toml"
    with open(global_config_path, "wb") as f:
        tomli_w.dump({"core": {"project_root": str(tmp_path), "active_project": "test-project"}}, f)

    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_titan_dir = project_dir / ".titan"
    project_titan_dir.mkdir()
    project_config_path = project_titan_dir / "config.toml"
    with open(project_config_path, "wb") as f:
        tomli_w.dump({"project": {"name": "test-project"}, "plugins": {}}, f) # Add empty plugins dict

    # Mock PluginRegistry that finds no plugins initially
    mock_registry = MagicMock(spec=PluginRegistry)
    mock_registry.list_installed.return_value = []
    
    config = TitanConfig(registry=mock_registry)
    # Force paths to our tmp_path
    config._project_root = tmp_path
    config._active_project_path = project_dir
    config.project_config_path = project_config_path
    config.load() # Reload to pick up all settings

    return config

@patch('titan_cli.cli.KNOWN_PLUGINS', MOCK_KNOWN_PLUGINS)
def test_install_plugin_flow(mock_config, mock_ui):
    """Test the plugin installation flow."""
    mock_text, mock_prompts = mock_ui
    
    # --- Setup Mocks ---
    # 1. User chooses 'install' from the main plugin menu
    # 2. In the install menu, user chooses 'git'
    # 3. Then user chooses 'back'
    mock_install_choice = MagicMock()
    mock_install_choice.action = "install"
    
    mock_git_choice = MagicMock()
    mock_git_choice.action = "titan-plugin-git" # Action is the package name

    mock_back_choice = MagicMock()
    mock_back_choice.action = "back"

    mock_prompts.ask_menu.side_effect = [
        mock_install_choice, # User selects 'Install'
        mock_git_choice,     # User selects 'git' plugin
        mock_back_choice,    # User selects 'Back'
        MagicMock(action="back") # Exit main loop
    ]
    
    # Mock the shell command
    with patch('subprocess.run') as mock_run_shell:
        mock_run_shell.return_value = MagicMock(returncode=0)

        # --- Act ---
        _show_plugin_management_menu(mock_prompts, mock_text, mock_config)

        # --- Assert ---
        # Check that pipx inject was called correctly
        assert mock_run_shell.called
        call_args = mock_run_shell.call_args[0][0]
        assert call_args[0] == "pipx"
        assert call_args[1] == "inject"
        assert call_args[2] == "--editable" # Check for editable flag
        assert call_args[3] == "titan-cli"
        assert call_args[4].endswith("plugins/titan-plugin-git")

        # Check for success message
        mock_text.success.assert_any_call("Successfully installed titan-plugin-git.")

