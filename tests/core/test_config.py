# tests/core/test_config.py
import hashlib
import os
import re
import subprocess
import tomli
import tomli_w
from pathlib import Path
import pytest
from titan_cli.core.config import TitanConfig


def _git_init(path: Path) -> None:
    """Initialize a git repository at the given path."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)


def _project_scope_key(path: Path) -> str:
    """Match TitanConfig's project-scoped override key generation."""
    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", path.name).strip("_").lower() or "project"
    return f"p_{safe_name}_{hashlib.sha256(str(path.resolve()).encode('utf-8')).hexdigest()[:8]}"

def test_config_project_overrides_global(tmp_path: Path, monkeypatch, mocker):
    """
    Test that project-specific config correctly overrides the global config.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create a mock global config
    global_config_dir = tmp_path / "home" / ".titan"
    global_config_dir.mkdir(parents=True)
    global_config_path = global_config_dir / "config.toml"
    global_config_data = {
        "ai": {
            "default_connection": "anthropic",
            "connections": {
                "anthropic": {
                    "connection_type": "direct_provider",
                    "provider": "anthropic",
                    "default_model": "claude-3-5-sonnet",
                    "name": "Global Claude",
                    "temperature": 0.7,
                    "max_tokens": 4096
                }
            }
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 2. Create a mock project config
    project_dir = tmp_path / "my_project"
    project_titan_dir = project_dir / ".titan"
    project_titan_dir.mkdir(parents=True)
    project_config_path = project_titan_dir / "config.toml"
    project_config_data = {
        "project": {"name": "My Specific Project"},
        "ai": {
            "default_connection": "gemini",
            "connections": {
                "gemini": {
                    "connection_type": "direct_provider",
                    "provider": "gemini",
                    "default_model": "gemini-1.5-pro",
                    "name": "Project Gemini",
                    "temperature": 0.7,
                    "max_tokens": 4096
                }
            }
        },
        "plugins": {
            "github": {"enabled": True, "config": {"org": "project-org"}},
            "git": {"enabled": True, "config": {}}
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    # 3. Patch global config path and project config path
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    # Change to project directory so it finds the project config
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        # 4. Assert that the merge was successful
        # Project name is from project config
        assert config_instance.config.project.name == "My Specific Project"
        # AI provider is overridden by project config
        assert config_instance.config.ai.default_connection == "gemini"
        assert (
            config_instance.config.ai.connections["gemini"].default_model
            == "gemini-1.5-pro"
        )
        assert config_instance.config.ai.connections["gemini"].name == "Project Gemini"
        # Plugin configs are from project
        assert config_instance.config.plugins["github"].enabled is True
        assert config_instance.config.plugins["github"].config["org"] == "project-org"
        assert config_instance.config.plugins["git"].enabled is True
    finally:
        os.chdir(original_cwd)


def test_config_dependency_injection(mocker, monkeypatch):
    """
    Test that the PluginRegistry is correctly injected into TitanConfig.
    """
    # Mock PluginRegistry to ensure it's called
    mock_registry = mocker.MagicMock()
    mocker.patch('titan_cli.core.config.PluginRegistry', return_value=mock_registry)

    # Patch config paths to nonexistent files
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", Path("/nonexistent/config.toml"))
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    config_instance = TitanConfig()

    # Assert that the registry was injected
    assert config_instance.registry is mock_registry


def test_load_toml_handles_decode_error(tmp_path: Path, capsys, monkeypatch, mocker):
    """
    Test that _load_toml handles TOMLDecodeError gracefully.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # Create an invalid TOML file
    invalid_toml_path = tmp_path / "invalid.toml"
    invalid_toml_path.write_text("this is not valid toml ][")

    # Patch config paths
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", invalid_toml_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    # This should not raise an exception
    config_instance = TitanConfig()

    # Should have empty config
    assert config_instance.global_config == {}


def test_config_deep_merges_plugins(tmp_path: Path, monkeypatch, mocker):
    """
    Test that the plugin configuration is deep-merged, not just overridden.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create project directory structure
    project_dir = tmp_path / "test_project"
    project_titan_dir = project_dir / ".titan"
    project_titan_dir.mkdir(parents=True)

    # 2. Global config defines a plugin with 'enabled' and a nested 'config' key
    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    global_config_data = {
        "plugins": {
            "github": {"enabled": True, "config": {"user": "global-user", "repo": "global-repo"}}
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 3. Project config overrides only the nested 'user' key
    project_config_path = project_titan_dir / "config.toml"
    project_config_data = {
        "project": {"name": "Test Project"},
        "plugins": {
            "github": {"config": {"user": "project-user"}}
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    # 4. Patch config paths and initialize from project directory
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        # 5. Assert that the 'enabled' key from global is preserved
        #    and the nested 'user' key is overridden, but 'repo' is preserved
        github_plugin_config = config_instance.config.plugins.get("github")
        assert github_plugin_config is not None
        assert github_plugin_config.enabled is True  # This should be preserved from global
        assert github_plugin_config.config["user"] == "project-user"  # This should be overridden by project
        assert github_plugin_config.config["repo"] == "global-repo"  # This should be preserved from global
    finally:
        os.chdir(original_cwd)


def test_config_uses_git_root_as_project_root(tmp_path: Path, monkeypatch, mocker):
    """
    Monorepo scenario: when running from a subdirectory, project_root should be
    the git root, not the current working directory.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # Setup: git repo at tmp_path/monorepo, .titan config at monorepo root
    git_root = tmp_path / "monorepo"
    git_root.mkdir()
    _git_init(git_root)

    titan_dir = git_root / ".titan"
    titan_dir.mkdir()
    project_config_path = titan_dir / "config.toml"
    project_config_data = {"project": {"name": "My Monorepo"}}
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    # Global config (empty)
    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    # Run from a subdirectory (simulating working in /monorepo/app)
    app_dir = git_root / "app"
    app_dir.mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(app_dir)
        config_instance = TitanConfig()

        assert config_instance.project_root == git_root.resolve()
        assert config_instance.config.project.name == "My Monorepo"
    finally:
        os.chdir(original_cwd)


def test_config_uses_cwd_as_project_root_when_no_git(tmp_path: Path, monkeypatch, mocker):
    """
    When not inside a git repo, project_root falls back to the current
    working directory.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    titan_dir = project_dir / ".titan"
    titan_dir.mkdir()
    project_config_path = titan_dir / "config.toml"
    with open(project_config_path, "wb") as f:
        tomli_w.dump({"project": {"name": "No Git Project"}}, f)

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        assert config_instance.project_root == project_dir.resolve()
        assert config_instance.config.project.name == "No Git Project"
    finally:
        os.chdir(original_cwd)


def test_update_ai_connection_updates_only_requested_fields(
    tmp_path: Path, monkeypatch, mocker
):
    mocker.patch("titan_cli.core.config.PluginRegistry")

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    global_config_data = {
        "config_version": "1.0",
        "ai": {
            "default_connection": "work-gateway",
            "connections": {
                "work-gateway": {
                    "name": "Work Gateway",
                    "connection_type": "gateway",
                    "gateway_backend": "openai_compatible",
                    "base_url": "http://localhost:4000",
                    "default_model": "gpt-5",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                }
            },
        },
    }

    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    config_instance = TitanConfig()
    config_instance.update_ai_connection(
        "work-gateway",
        {"default_model": "claude-sonnet-4"},
    )

    config_instance.load()
    connection = config_instance.config.ai.connections["work-gateway"]
    assert connection.default_model == "claude-sonnet-4"
    assert connection.base_url == "http://localhost:4000"
    assert connection.temperature == 0.7


def test_update_ai_connection_raises_when_connection_not_found(
    tmp_path: Path, monkeypatch, mocker
):
    mocker.patch("titan_cli.core.config.PluginRegistry")

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({"config_version": "1.0", "ai": {"connections": {}}}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    config_instance = TitanConfig()

    with pytest.raises(ValueError, match="AI connection 'missing' not found."):
        config_instance.update_ai_connection("missing", {"default_model": "gpt-5"})


def test_load_rewrites_legacy_global_config_after_migration(
    tmp_path: Path, monkeypatch, mocker
):
    mocker.patch("titan_cli.core.config.PluginRegistry")

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(
            {
                "version": "1.0",
                "ai": {
                    "default": "corp-gemini",
                    "providers": {
                        "corp-claude": {
                            "name": "Corp Claude",
                            "type": "corporate",
                            "provider": "anthropic",
                            "model": "claude-sonnet-4-5",
                            "base_url": "https://llm.company.com/",
                        },
                        "corp-gemini": {
                            "name": "Corp Gemini",
                            "type": "corporate",
                            "provider": "gemini",
                            "model": "gemini-2.5-pro",
                            "base_url": "https://llm.company.com/",
                        },
                    },
                },
            },
            f,
        )

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    TitanConfig()

    with open(global_config_path, "rb") as f:
        migrated = tomli.load(f)

    assert "version" not in migrated
    assert migrated["config_version"] == "1.0"
    assert migrated["ai"]["default_connection"] == "corp-gemini"
    assert list(migrated["ai"]["connections"].keys()) == ["corp-gemini"]


def test_load_does_not_rewrite_legacy_project_config(
    tmp_path: Path, monkeypatch, mocker
):
    mocker.patch("titan_cli.core.config.PluginRegistry")

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({"config_version": "1.0"}, f)

    project_root = tmp_path / "project"
    project_config_path = project_root / ".titan" / "config.toml"
    project_config_path.parent.mkdir(parents=True)
    legacy_project_data = {
        "version": "1.0",
        "project": {"name": "demo-project"},
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(legacy_project_data, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(
        TitanConfig,
        "_find_project_config",
        lambda self, path: project_config_path,
    )
    monkeypatch.setattr("titan_cli.core.config.find_project_root", lambda: project_root)

    TitanConfig()

    with open(project_config_path, "rb") as f:
        loaded_project = tomli.load(f)

    assert loaded_project == legacy_project_data


def test_load_accepts_already_migrated_project_config(
    tmp_path: Path, monkeypatch, mocker
):
    mocker.patch("titan_cli.core.config.PluginRegistry")

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({"config_version": "1.0"}, f)

    project_root = tmp_path / "project"
    project_config_path = project_root / ".titan" / "config.toml"
    project_config_path.parent.mkdir(parents=True)
    project_config_data = {
        "config_version": "1.0",
        "project": {"name": "demo-project"},
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(
        TitanConfig,
        "_find_project_config",
        lambda self, path: project_config_path,
    )
    monkeypatch.setattr("titan_cli.core.config.find_project_root", lambda: project_root)

    config = TitanConfig()

    with open(project_config_path, "rb") as f:
        loaded_project = tomli.load(f)

    assert config.config.project.name == "demo-project"
    assert loaded_project == project_config_data


def test_config_finds_titan_at_git_root_not_subdir(tmp_path: Path, monkeypatch, mocker):
    """
    When running from /monorepo/app with .titan only at /monorepo,
    the wizard should NOT trigger (config is found at git root).
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    git_root = tmp_path / "monorepo"
    git_root.mkdir()
    _git_init(git_root)

    titan_dir = git_root / ".titan"
    titan_dir.mkdir()
    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump({"project": {"name": "Monorepo"}}, f)

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    # Running from a nested package dir — no .titan here
    pkg_dir = git_root / "packages" / "backend"
    pkg_dir.mkdir(parents=True)

    original_cwd = os.getcwd()
    try:
        os.chdir(pkg_dir)
        config_instance = TitanConfig()

        # Config should be found — no wizard needed
        assert config_instance.project_config_path == titan_dir / "config.toml"
        assert config_instance.config.project.name == "Monorepo"
    finally:
        os.chdir(original_cwd)


def test_config_no_titan_in_subdir_triggers_wizard_scenario(tmp_path: Path, monkeypatch, mocker):
    """
    .titan only exists in a subdirectory (/monorepo/app/.titan) but NOT at git root (/monorepo).
    Running from /monorepo/app should NOT find the config — project_root is the git root,
    and _find_project_config searches from there upward, missing the subdir config.
    This documents the intentional behavior: configs must live at the git root.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    git_root = tmp_path / "monorepo"
    git_root.mkdir()
    _git_init(git_root)

    # .titan is in the app subdir, NOT at git root
    app_dir = git_root / "app"
    app_dir.mkdir()
    app_titan_dir = app_dir / ".titan"
    app_titan_dir.mkdir()
    with open(app_titan_dir / "config.toml", "wb") as f:
        tomli_w.dump({"project": {"name": "App Only"}}, f)

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(app_dir)
        config_instance = TitanConfig()

        # Config at subdir is NOT found — project_root is git root, not app_dir
        assert config_instance.project_root == git_root.resolve()
        assert config_instance.project_config_path is None
    finally:
        os.chdir(original_cwd)


def test_config_workflow_registry_uses_git_root(tmp_path: Path, monkeypatch, mocker):
    """
    WorkflowRegistry should be initialized with the git root as project_root,
    so workflows defined at the monorepo level are discoverable from any subdirectory.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')
    mock_registry_cls = mocker.patch('titan_cli.core.config.WorkflowRegistry')

    git_root = tmp_path / "monorepo"
    git_root.mkdir()
    _git_init(git_root)

    titan_dir = git_root / ".titan"
    titan_dir.mkdir()
    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump({"project": {"name": "Monorepo"}}, f)

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    app_dir = git_root / "app"
    app_dir.mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(app_dir)
        TitanConfig()

        # WorkflowRegistry must be initialized with git root, not app_dir
        call_kwargs = mock_registry_cls.call_args
        assert call_kwargs.kwargs["project_root"] == git_root.resolve()
    finally:
        os.chdir(original_cwd)


def test_get_plugin_source_defaults_to_stable_and_no_path(mocker, monkeypatch):
    """
    Plugins without an explicit source override should use the stable channel.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", Path("/nonexistent/config.toml"))
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    config_instance = TitanConfig()

    assert config_instance.get_plugin_source_channel("github") == "stable"
    assert config_instance.get_plugin_source_path("github") is None


def test_get_plugin_source_reads_project_override(tmp_path: Path, monkeypatch, mocker):
    """
    Source override metadata should be available through TitanConfig helpers.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    titan_dir = project_dir / ".titan"
    titan_dir.mkdir()

    plugin_repo = tmp_path / "plugins" / "local-github"
    plugin_repo.mkdir(parents=True)

    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump(
            {
                "project": {"name": "Project"},
                "plugins": {
                    "github": {
                        "enabled": True,
                        "source": {
                            "channel": "dev_local",
                            "path": str(plugin_repo),
                        },
                    }
                },
            },
            f,
        )

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        assert config_instance.get_plugin_source_channel("github") == "dev_local"
        assert config_instance.get_plugin_source_path("github") == plugin_repo.resolve()
    finally:
        os.chdir(original_cwd)


def test_get_plugin_source_prefers_global_override_over_project(tmp_path: Path, monkeypatch, mocker):
    """
    Plugin source selection is user-local and global source overrides must win
    over project-level source metadata.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    titan_dir = project_dir / ".titan"
    titan_dir.mkdir()

    global_plugin_repo = tmp_path / "plugins" / "global-github"
    global_plugin_repo.mkdir(parents=True)
    project_plugin_repo = tmp_path / "plugins" / "project-github"
    project_plugin_repo.mkdir(parents=True)

    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump(
            {
                "project": {"name": "Project"},
                "plugins": {
                    "github": {
                        "enabled": True,
                        "source": {
                            "channel": "stable",
                            "path": str(project_plugin_repo),
                        },
                    }
                },
            },
            f,
        )

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(
            {
                "plugins": {
                    "github": {
                        "source": {
                            "channel": "dev_local",
                            "path": str(global_plugin_repo),
                        }
                    }
                }
            },
            f,
        )

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        assert config_instance.get_plugin_source_channel("github") == "dev_local"
        assert config_instance.get_plugin_source_path("github") == global_plugin_repo.resolve()
    finally:
        os.chdir(original_cwd)


def test_project_stable_source_helpers_return_shared_pin_metadata(tmp_path: Path, monkeypatch, mocker):
    """Project helpers should expose the shared stable pin metadata."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    titan_dir = project_dir / ".titan"
    titan_dir.mkdir()

    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump(
            {
                "project": {"name": "Project"},
                "plugins": {
                    "sample": {
                        "enabled": True,
                        "source": {
                            "channel": "stable",
                            "repo_url": "https://github.com/example/sample-plugin",
                            "requested_ref": "v1.2.3",
                            "resolved_commit": "a" * 40,
                        },
                    }
                },
            },
            f,
        )

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        assert config_instance.get_plugin_source_channel("sample") == "stable"
        assert config_instance.get_project_plugin_repo_url("sample") == "https://github.com/example/sample-plugin"
        assert config_instance.get_project_plugin_requested_ref("sample") == "v1.2.3"
        assert config_instance.get_project_plugin_resolved_commit("sample") == "a" * 40
        assert config_instance.get_effective_plugin_source("sample") == {
            "channel": "stable",
            "repo_url": "https://github.com/example/sample-plugin",
            "requested_ref": "v1.2.3",
            "resolved_commit": "a" * 40,
        }
    finally:
        os.chdir(original_cwd)


def test_effective_plugin_source_keeps_global_dev_path_as_stable_memory(tmp_path: Path, monkeypatch, mocker):
    """Stable mode should preserve the remembered local dev path without activating it."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    titan_dir = project_dir / ".titan"
    titan_dir.mkdir()
    remembered_path = tmp_path / "plugins" / "sample"
    remembered_path.mkdir(parents=True)

    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump(
            {
                "project": {"name": "Project"},
                "plugins": {
                    "sample": {
                        "enabled": True,
                        "source": {
                            "channel": "stable",
                            "repo_url": "https://github.com/example/sample-plugin",
                            "requested_ref": "v1.2.3",
                            "resolved_commit": "b" * 40,
                        },
                    }
                },
            },
            f,
        )

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(
            {
                "plugins": {
                    "sample": {
                        "source": {
                            "channel": "stable",
                            "path": str(remembered_path),
                        }
                    }
                }
            },
            f,
        )

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        assert config_instance.get_plugin_source_channel("sample") == "stable"
        assert config_instance.get_plugin_source_path("sample") == remembered_path.resolve()
        assert config_instance.get_effective_plugin_source("sample") == {
            "channel": "stable",
            "repo_url": "https://github.com/example/sample-plugin",
            "requested_ref": "v1.2.3",
            "resolved_commit": "b" * 40,
            "path": str(remembered_path),
        }
    finally:
        os.chdir(original_cwd)


def test_set_global_plugin_source_writes_user_config(tmp_path: Path, monkeypatch, mocker):
    """Global plugin source overrides should be written to user config."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()
        config_instance.set_global_plugin_source("github", "dev_local", "/tmp/local-github")
    finally:
        os.chdir(original_cwd)

    with open(global_config_path, "rb") as f:
        import tomli
        data = tomli.load(f)

    project_key = config_instance._get_project_source_scope_key()
    assert data["project_sources"][project_key]["plugins"]["github"]["source"]["channel"] == "dev_local"
    assert data["project_sources"][project_key]["plugins"]["github"]["source"]["path"] == "/tmp/local-github"
    assert data["project_sources"][project_key]["project_path"] == str(project_dir.resolve())
    assert "plugins" not in data


def test_clear_global_plugin_source_removes_only_source_block(tmp_path: Path, monkeypatch, mocker):
    """Clearing a global plugin source should preserve other global plugin settings."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    project_key = _project_scope_key(project_dir)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(
            {
                "project_sources": {
                    project_key: {
                        "project_path": str(project_dir.resolve()),
                        "plugins": {
                            "github": {
                                "enabled": True,
                                "config": {"org": "acme"},
                                "source": {
                                    "channel": "dev_local",
                                    "path": "/tmp/local-github",
                                },
                            }
                        }
                    }
                }
            },
            f,
        )

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()
        config_instance.clear_global_plugin_source("github")
    finally:
        os.chdir(original_cwd)

    with open(global_config_path, "rb") as f:
        import tomli
        data = tomli.load(f)

    assert "source" not in data["project_sources"][project_key]["plugins"]["github"]
    assert data["project_sources"][project_key]["plugins"]["github"]["enabled"] is True
    assert data["project_sources"][project_key]["plugins"]["github"]["config"]["org"] == "acme"


def test_save_global_config_preserves_existing_plugin_source(tmp_path: Path, monkeypatch, mocker):
    """Saving AI config should not erase existing global plugin source overrides."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    project_key = _project_scope_key(project_dir)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(
            {
                "project_sources": {
                    project_key: {
                        "project_path": str(project_dir.resolve()),
                        "plugins": {
                            "github": {
                                "source": {
                                    "channel": "dev_local",
                                    "path": "/tmp/local-github",
                                }
                            }
                        }
                    }
                }
            },
            f,
        )

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.setattr(TitanConfig, "_find_project_config", lambda self, path: None)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig(skip_plugin_init=True)
        config_instance.config.ai = None
        config_instance._save_global_config()
    finally:
        os.chdir(original_cwd)

    with open(global_config_path, "rb") as f:
        import tomli
        data = tomli.load(f)

    assert data["project_sources"][project_key]["plugins"]["github"]["source"]["channel"] == "dev_local"
    assert data["project_sources"][project_key]["plugins"]["github"]["source"]["path"] == "/tmp/local-github"


def test_global_plugin_source_is_scoped_to_active_project(tmp_path: Path, monkeypatch, mocker):
    """A dev_local override in one project must not affect another project."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    for project_dir in (project_a, project_b):
        project_dir.mkdir()
        titan_dir = project_dir / ".titan"
        titan_dir.mkdir()
        with open(titan_dir / "config.toml", "wb") as f:
            tomli_w.dump(
                {
                    "project": {"name": project_dir.name},
                    "plugins": {
                        "sample": {
                            "enabled": True,
                            "source": {
                                "channel": "stable",
                                "repo_url": "https://github.com/example/sample-plugin",
                                "requested_ref": "v1.0.0",
                                "resolved_commit": "a" * 40,
                            },
                        }
                    },
                },
                f,
            )

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_b)
        config_b = TitanConfig()
        config_b.set_global_plugin_source("sample", "dev_local", "/tmp/sample-dev")

        config_b.load(skip_plugin_init=True)
        assert config_b.get_plugin_source_channel("sample") == "dev_local"
        assert config_b.get_plugin_source_path("sample") == Path("/tmp/sample-dev").resolve()

        os.chdir(project_a)
        config_a = TitanConfig(skip_plugin_init=True)
        assert config_a.get_plugin_source_channel("sample") == "stable"
        assert config_a.get_plugin_source_path("sample") is None
    finally:
        os.chdir(original_cwd)


def test_global_source_override_does_not_enable_plugin_in_other_projects(tmp_path: Path, monkeypatch, mocker):
    """A global source-only override must not implicitly enable the plugin."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    titan_dir = project_dir / ".titan"
    titan_dir.mkdir()
    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump({"project": {"name": "Project"}}, f)

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(
            {
                "plugins": {
                    "ragnarok": {
                        "source": {
                            "channel": "stable",
                            "path": "/tmp/ragnarok-plugin",
                        }
                    }
                }
            },
            f,
        )

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        assert config_instance.is_plugin_enabled("ragnarok") is False
        assert "ragnarok" not in config_instance.get_enabled_plugins()
    finally:
        os.chdir(original_cwd)


def test_project_must_explicitly_enable_plugin(tmp_path: Path, monkeypatch, mocker):
    """A plugin remains disabled unless the current project explicitly enables it."""
    mocker.patch('titan_cli.core.config.PluginRegistry')

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    titan_dir = project_dir / ".titan"
    titan_dir.mkdir()
    with open(titan_dir / "config.toml", "wb") as f:
        tomli_w.dump({"project": {"name": "Project"}}, f)

    global_config_path = tmp_path / "home" / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump(
            {
                "plugins": {
                    "ragnarok": {
                        "config": {"platform": "android"},
                        "source": {
                            "channel": "stable",
                            "path": "/tmp/ragnarok-plugin",
                        },
                    }
                }
            },
            f,
        )

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)
        config_instance = TitanConfig()

        assert config_instance.is_plugin_enabled("ragnarok") is False
        assert "ragnarok" not in config_instance.get_enabled_plugins()
    finally:
        os.chdir(original_cwd)
