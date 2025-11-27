# tests/commands/test_projects.py
import tomli_w
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import MagicMock # Import MagicMock

from titan_cli.cli import app
from titan_cli.core.config import TitanConfig # Import TitanConfig to patch it
from titan_cli.core.models import TitanConfigModel, CoreConfig # Import models for structured mock

runner = CliRunner()

def test_projects_list_no_root_config(monkeypatch, tmp_path):
    """
    Test that 'titan projects list' shows an error if project_root is not configured.
    """
    # 1. Patch home to an empty directory, so no global config is found
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: mock_home)

    # Mock TitanConfig to return a config where project_root is None
    mock_core_config = CoreConfig(project_root=None)
    mock_titan_config_model = TitanConfigModel(core=mock_core_config)
    
    mock_titan_config_instance = MagicMock(spec=TitanConfig)
    mock_titan_config_instance.config = mock_titan_config_model
    
    monkeypatch.setattr("titan_cli.commands.projects.TitanConfig", MagicMock(return_value=mock_titan_config_instance))

    # 2. Run the 'projects list' command
    result = runner.invoke(app, ["projects", "list"])

    # 3. Assertions
    assert result.exit_code == 1 # Should exit with an error
    assert "Project root not configured or does not exist." in result.stdout