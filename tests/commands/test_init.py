# tests/commands/test_init.py
import tomli
import tomli_w # Needed to write initial global config for some tests
from pathlib import Path
from typer.testing import CliRunner
from titan_cli.cli import app # Import the main app
from titan_cli.core.config import TitanConfig # Import TitanConfig to patch GLOBAL_CONFIG

runner = CliRunner()

def test_init_creates_global_config(mocker, monkeypatch, tmp_path):
    """
    Test that 'titan init' correctly creates and populates the global config file.
    """
    # 1. Setup mock paths and inputs
    mock_global_config_path = tmp_path / "global_config.toml"
    mock_project_root_path = tmp_path / "my_projects"
    
    # Patch TitanConfig.GLOBAL_CONFIG to point to our mock file
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", mock_global_config_path)
    
    # Patch the ask_text method on the PromptsRenderer class used within the command
    mocker.patch("titan_cli.commands.init.PromptsRenderer.ask_text", return_value=str(mock_project_root_path))

    # 2. Run the 'init' command
    result = runner.invoke(app, ["init"])

    # 3. Assertions
    assert result.exception is None # Check for unexpected exceptions
    assert result.exit_code == 0
    assert "Global configuration updated" in result.stdout
    # Don't check for exact path in stdout due to line wrapping in terminal output
    # Instead verify the TOML file content below

    # Verify the content of the created config file
    assert mock_global_config_path.exists()
    with open(mock_global_config_path, "rb") as f:
        config_data = tomli.load(f)

    # This is the key assertion - verify the actual config value
    assert config_data["core"]["project_root"] == str(mock_project_root_path)

def test_init_handles_non_interactive_env(mocker, monkeypatch, tmp_path):
    """
    Test that 'titan init' handles non-interactive environments gracefully.
    """
    # 1. Setup mock paths
    mock_global_config_path = tmp_path / "global_config.toml"
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", mock_global_config_path)
    
    # 2. Patch ask_text to simulate a non-interactive environment by raising EOFError
    mocker.patch("titan_cli.commands.init.PromptsRenderer.ask_text", side_effect=EOFError())

    # 3. Run the 'init' command
    result = runner.invoke(app, ["init"])

    # 4. Assertions
    assert result.exit_code == 0 # Should exit gracefully
    assert "Operation cancelled. No changes were made." in result.stdout
    
    # Ensure no config file was created or modified
    assert not mock_global_config_path.exists()