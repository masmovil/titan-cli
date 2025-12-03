# tests/core/test_config.py
import pytest
import tomli_w
from pathlib import Path
from titan_cli.core.config import TitanConfig
from titan_cli.core.models import TitanConfigModel
from titan_cli.core.plugin_registry import PluginRegistry # Import PluginRegistry for mocking
from titan_cli.core.errors import ConfigParseError # Import custom error

def test_config_initialization_no_files(monkeypatch, mocker):
    """
    Test that TitanConfig initializes with default values when no config files are present.
    """
    # Mock PluginRegistry to prevent it from running discovery
    mocker.patch('titan_cli.core.config.PluginRegistry')
    
    # Use monkeypatch to prevent it from finding any real config files
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", Path("/nonexistent/config.toml"))
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    # Initialize TitanConfig
    config_instance = TitanConfig()

    # Assert that the resulting config is the default Pydantic model
    assert config_instance.config.project is None # Project is optional now
    assert config_instance.config.core is None
    assert config_instance.config.ai is None
    assert config_instance.project_config == {}
    assert config_instance.global_config == {}

def test_config_loads_global_config(tmp_path: Path, monkeypatch, mocker):
    """
    Test that TitanConfig correctly loads a global config file.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # Create a mock global config file
    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"
    global_config_data = {
        "core": {"project_root": str(tmp_path)},
        "ai": {"provider": "openai", "model": "gpt-4"}
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)
    
    # Patch the GLOBAL_CONFIG path to point to our mock file
    # and disable project config finding
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    config_instance = TitanConfig()

    assert config_instance.global_config["core"]["project_root"] == str(tmp_path)
    assert config_instance.config.core.project_root == str(tmp_path)
    assert config_instance.config.ai.provider == "openai"
    assert config_instance.config.ai.model == "gpt-4"
    
def test_config_project_overrides_global(tmp_path: Path, monkeypatch, mocker):
    """
    Test that project-specific config correctly overrides the global config.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create a mock global config
    global_config_dir = tmp_path / "global" / ".titan"
    global_config_dir.mkdir(parents=True)
    global_config_path = global_config_dir / "config.toml"
    global_config_data = {
        "project": {"name": "Global Project"}, # This will be ignored due to project config
        "ai": {"provider": "anthropic"},
        "plugins": {
            "github": {"enabled": True, "config": {"org": "global-org"}},
            "jira": {"enabled": False}
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 2. Create a mock project config in a subdirectory
    project_dir = tmp_path / "my_project"
    project_titan_dir = project_dir / ".titan"
    project_titan_dir.mkdir(parents=True)
    project_config_path = project_titan_dir / "config.toml"
    project_config_data = {
        "project": {"name": "My Specific Project"},
        "ai": {"provider": "openai"}, # Override provider
        "plugins": {
            "github": {"config": {"org": "project-org"}}, # Override nested value
            "git": {"enabled": True} # Add a new plugin
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)
    
    # 3. Patch global config and initialize from the project directory
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    
    config_instance = TitanConfig(project_path=project_dir)

    # 4. Assert that the merge was successful
    # Project name is from project config
    assert config_instance.config.project.name == "My Specific Project"
    # AI provider is overridden by project config
    assert config_instance.config.ai.provider == "openai"
    # Plugin configs are merged correctly
    assert config_instance.config.plugins["github"].enabled is True # from global
    assert config_instance.config.plugins["github"].config["org"] == "project-org" # from project
    assert config_instance.config.plugins["jira"].enabled is False # from global
    assert config_instance.config.plugins["git"].enabled is True # from project


def test_find_project_config_walks_up_tree(tmp_path: Path, monkeypatch, mocker):
    """
    Test that _find_project_config correctly finds config in parent directory.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')
    
    # Create project root and config
    project_root = tmp_path / "my_real_project"
    project_titan_dir = project_root / ".titan"
    project_titan_dir.mkdir(parents=True)
    config_path = project_titan_dir / "config.toml"
    config_path.touch()

    # Create a deep subdirectory to start the search from
    deep_subdir = project_root / "src" / "app" / "components"
    deep_subdir.mkdir(parents=True)

    # Initialize TitanConfig without patching _find_project_config
    # but patch the global config to isolate the test
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", Path("/nonexistent/config.toml"))

    config_instance = TitanConfig(project_path=deep_subdir)
    
    # Assert that it found the correct config file
    assert config_instance.project_config_path == config_path

def test_config_dependency_injection(mocker, monkeypatch):
    """
    Test that a custom PluginRegistry instance can be injected into TitanConfig.
    """
    # 1. Create a mock PluginRegistry instance
    mock_registry = mocker.MagicMock()

    # 2. Prevent file I/O to isolate the test from the filesystem
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", Path("/nonexistent/config.toml"))
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)
    
    # 3. Initialize TitanConfig, injecting the mock registry
    config_instance = TitanConfig(registry=mock_registry)
    
    # 4. Assert that the TitanConfig instance is using our injected mock object
    #    instead of creating its own.
    assert config_instance.registry is mock_registry

def test_load_toml_handles_decode_error(tmp_path: Path, capsys, monkeypatch, mocker):
    """
    Test that _load_toml returns an empty dict and prints a warning for a malformed file.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create a malformed TOML file
    malformed_toml_path = tmp_path / "invalid.toml"
    malformed_toml_path.write_text("this is not valid toml = ")

    # Patch global config to use this malformed file
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", malformed_toml_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None) # Disable project config for this test

    # 2. Instantiate TitanConfig, which will call _load_toml internally
    config_instance = TitanConfig()

    # 3. Assert that the global config is empty (because of the error)
    assert config_instance.global_config == {}

    # 4. Assert that a warning was NOT printed, as this is now handled by the UI layer
    captured = capsys.readouterr()
    output = captured.err + captured.out
    assert "Warning: Failed to parse configuration file" not in output

def test_config_deep_merges_plugins(tmp_path: Path, monkeypatch, mocker):
    """
    Test that the plugin configuration is deep-merged, not just overridden.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')
    
    # 1. Global config defines a plugin with 'enabled' and a nested 'config' key
    global_config_path = tmp_path / "global_config.toml"
    global_config_data = {
        "plugins": {
            "github": {"enabled": True, "config": {"user": "global-user"}}
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 2. Project config overrides only the nested 'user' key
    project_config_path = tmp_path / "project_config.toml"
    project_config_data = {
        "project": {"name": "Test Project"},
        "plugins": {
            "github": {"config": {"user": "project-user"}}
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)
    
    # 3. Patch config paths and initialize
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    # Mock _find_project_config to return our specific project config
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: project_config_path)
    
    config_instance = TitanConfig()

    # 4. Assert that the 'enabled' key from global is preserved
    #    and the nested 'user' key is overridden.
    github_plugin_config = config_instance.config.plugins.get("github")
    assert github_plugin_config is not None
    assert github_plugin_config.enabled is True  # This should be preserved from global
    assert github_plugin_config.config["user"] == "project-user" # This should be overridden by project