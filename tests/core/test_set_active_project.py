# tests/core/test_set_active_project.py
"""
Tests for set_active_project to ensure it preserves global config sections.

This prevents the bug where switching projects would delete [ai] and [plugins]
sections from ~/.titan/config.toml
"""
import pytest
import tomli_w
import tomllib
from pathlib import Path
from titan_cli.core.config import TitanConfig


def test_set_active_project_preserves_ai_config(tmp_path: Path, monkeypatch, mocker):
    """
    Test that set_active_project() preserves [ai] section in global config.

    This is a regression test for the bug where switching projects would
    overwrite the entire global config with only [core], losing [ai] and [plugins].
    """
    # Mock PluginRegistry to prevent discovery
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create global config with AI and plugins configuration
    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"

    original_global_config = {
        "core": {
            "project_root": str(tmp_path),
            "active_project": "project-a"
        },
        "ai": {
            "default": "anthropic-corp",
            "providers": {
                "anthropic-corp": {
                    "name": "Corporate Claude",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "base_url": "https://api.company.com/llm",
                    "type": "corporate"
                }
            }
        },
        "plugins": {
            "github": {
                "enabled": True,
                "config": {
                    "repo_owner": "test-org"
                }
            }
        }
    }

    with open(global_config_path, "wb") as f:
        tomli_w.dump(original_global_config, f)

    # 2. Create two projects
    project_a_dir = tmp_path / "project-a" / ".titan"
    project_a_dir.mkdir(parents=True)
    (project_a_dir / "config.toml").write_text("[plugins]")

    project_b_dir = tmp_path / "project-b" / ".titan"
    project_b_dir.mkdir(parents=True)
    (project_b_dir / "config.toml").write_text("[plugins]")

    # 3. Initialize TitanConfig (starts with project-a active)
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    config_instance = TitanConfig()

    # 4. Verify initial state
    assert config_instance.get_active_project() == "project-a"
    assert config_instance.config.ai is not None
    assert config_instance.config.ai.default == "anthropic-corp"

    # 5. Switch to project-b
    config_instance.set_active_project("project-b")

    # 6. CRITICAL: Verify that global config file still has [ai] and [plugins]
    with open(global_config_path, "rb") as f:
        saved_global_config = tomllib.load(f)

    # Verify [core] was updated
    assert saved_global_config["core"]["active_project"] == "project-b"

    # REGRESSION TEST: Verify [ai] section was NOT deleted
    assert "ai" in saved_global_config
    assert saved_global_config["ai"]["default"] == "anthropic-corp"
    assert "anthropic-corp" in saved_global_config["ai"]["providers"]

    # REGRESSION TEST: Verify [plugins] section was NOT deleted
    assert "plugins" in saved_global_config
    assert "github" in saved_global_config["plugins"]
    assert saved_global_config["plugins"]["github"]["enabled"] is True


def test_set_active_project_preserves_all_global_sections(tmp_path: Path, monkeypatch, mocker):
    """
    Test that set_active_project() preserves ALL sections in global config,
    not just [ai] and [plugins].
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"

    # Include multiple sections to test preservation
    original_global_config = {
        "core": {
            "project_root": str(tmp_path),
            "active_project": "project-a"
        },
        "ai": {
            "default": "claude",
            "providers": {
                "claude": {
                    "name": "Claude Default",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "type": "individual"
                }
            }
        },
        "plugins": {
            "git": {"enabled": True}
        },
        "custom_section": {
            "some_key": "some_value"
        }
    }

    with open(global_config_path, "wb") as f:
        tomli_w.dump(original_global_config, f)

    project_dir = tmp_path / "project-a" / ".titan"
    project_dir.mkdir(parents=True)
    (project_dir / "config.toml").write_text("[plugins]")

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    config_instance = TitanConfig()

    # Switch project (trigger save)
    config_instance.set_active_project("project-b")

    # Verify ALL sections preserved
    with open(global_config_path, "rb") as f:
        saved_config = tomllib.load(f)

    assert "core" in saved_config
    assert "ai" in saved_config
    assert "plugins" in saved_config
    assert "custom_section" in saved_config
    assert saved_config["custom_section"]["some_key"] == "some_value"


def test_set_active_project_works_when_global_config_only_has_core(tmp_path: Path, monkeypatch, mocker):
    """
    Test that set_active_project() works even when global config only has [core].
    This ensures we don't break when there's no existing [ai] or [plugins] to preserve.
    """
    mocker.patch('titan_cli.core.config.PluginRegistry')

    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"

    # Minimal config with only [core]
    minimal_config = {
        "core": {
            "project_root": str(tmp_path),
            "active_project": "project-a"
        }
    }

    with open(global_config_path, "wb") as f:
        tomli_w.dump(minimal_config, f)

    project_dir = tmp_path / "project-a" / ".titan"
    project_dir.mkdir(parents=True)
    (project_dir / "config.toml").write_text("")

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    config_instance = TitanConfig()

    # Should not crash
    config_instance.set_active_project("project-b")

    # Verify it saved correctly
    with open(global_config_path, "rb") as f:
        saved_config = tomllib.load(f)

    assert saved_config["core"]["active_project"] == "project-b"
