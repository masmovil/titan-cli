# tests/core/test_discovery.py
from pathlib import Path
from titan_cli.core.discovery import discover_projects

def test_discover_projects(tmp_path: Path):
    """
    Test that discover_projects correctly identifies configured and unconfigured projects.
    """
    # 1. Create a mock directory structure for testing
    # Configured project
    (tmp_path / "project-alpha" / ".titan").mkdir(parents=True)
    (tmp_path / "project-alpha" / ".titan" / "config.toml").touch()
    (tmp_path / "project-alpha" / ".git").mkdir()

    # Another configured project
    (tmp_path / "project-gamma" / ".titan").mkdir(parents=True)
    (tmp_path / "project-gamma" / ".titan" / "config.toml").touch()
    (tmp_path / "project-gamma" / ".git").mkdir()

    # Unconfigured project (git only)
    (tmp_path / "project-beta" / ".git").mkdir(parents=True)

    # A non-project directory
    (tmp_path / "docs").mkdir()

    # A file at the root
    (tmp_path / "README.md").touch()
    
    # An empty directory
    (tmp_path / "empty_dir").mkdir()

    # A directory that is a git repo but has an empty .titan folder (unconfigured)
    (tmp_path / "project-delta" / ".git").mkdir(parents=True)
    (tmp_path / "project-delta" / ".titan").mkdir()


    # 2. Run the discovery function
    configured, unconfigured = discover_projects(str(tmp_path))

    # 3. Assert the results
    
    # Check configured projects
    assert len(configured) == 2
    configured_names = {p.name for p in configured}
    assert "project-alpha" in configured_names
    assert "project-gamma" in configured_names

    # Check unconfigured projects
    assert len(unconfigured) == 2
    unconfigured_names = {p.name for p in unconfigured}
    assert "project-beta" in unconfigured_names
    assert "project-delta" in unconfigured_names

    # Check that non-project directories are ignored
    assert "docs" not in configured_names
    assert "docs" not in unconfigured_names
    assert "empty_dir" not in configured_names
    assert "empty_dir" not in unconfigured_names
