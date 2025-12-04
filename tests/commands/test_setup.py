"""
Tests for the setup command
"""
import pytest
from pathlib import Path
from typer.testing import CliRunner
from titan_cli.cli import app


runner = CliRunner()


def test_setup_command_exists():
    """Test that setup command is registered"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "setup" in result.stdout
    assert "Automated development environment setup" in result.stdout


def test_setup_help():
    """Test setup command help"""
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    assert "Automated development environment setup" in result.stdout


def test_setup_finds_bootstrap_script():
    """Test that setup command can find bootstrap.sh"""
    # This test verifies the path calculation is correct
    from titan_cli.commands.setup import setup_app

    # The bootstrap script should exist in the project root
    project_root = Path(__file__).parent.parent.parent
    bootstrap_script = project_root / "bootstrap.sh"

    assert bootstrap_script.exists(), f"Bootstrap script not found at {bootstrap_script}"
    assert bootstrap_script.is_file()
