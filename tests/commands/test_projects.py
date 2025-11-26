# tests/commands/test_projects.py
import tomli_w
from pathlib import Path
from typer.testing import CliRunner
from titan_cli.cli import app
from titan_cli.core.config import TitanConfig # Import TitanConfig to patch it

runner = CliRunner()

def test_projects_list_no_root_config(monkeypatch, tmp_path):
    """
    Test that 'titan projects list' shows an error if project_root is not configured.
    """
    # 1. Patch home to an empty directory, so no global config is found
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: mock_home)

    # 2. Run the 'projects list' command
    result = runner.invoke(app, ["projects", "list"])

    # 3. Assertions
    assert result.exit_code == 1 # Should exit with an error
    assert "Project root not configured" in result.stdout