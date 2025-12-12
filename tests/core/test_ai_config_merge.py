# tests/core/test_ai_config_merge.py
"""
Tests for AI configuration merging between global and project configs.

This ensures that global AI configuration is preserved when switching between
projects that don't have their own AI configuration.
"""
import pytest
import tomli_w
from pathlib import Path
from titan_cli.core.config import TitanConfig


def test_ai_config_preserved_when_project_has_no_ai_config(tmp_path: Path, monkeypatch, mocker):
    """
    Test that global AI config is preserved when project config has no [ai] section.

    This is the main fix: when a user configures AI globally and switches to a project
    without AI configuration, the global AI settings should still be available.
    """
    # Mock PluginRegistry to prevent discovery
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create global config with AI configuration
    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"
    global_config_data = {
        "core": {
            "project_root": str(tmp_path),
            "active_project": "test-project"
        },
        "ai": {
            "default": "anthropic-corp",
            "providers": {
                "anthropic-corp": {
                    "name": "Corporate Claude",
                    "type": "corporate",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "base_url": "https://api.company.com/llm"
                }
            }
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 2. Create project config WITHOUT AI section
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_config_dir = project_dir / ".titan"
    project_config_dir.mkdir()
    project_config_path = project_config_dir / "config.toml"
    project_config_data = {
        "plugins": {
            "github": {
                "enabled": True,
                "config": {
                    "repo_owner": "test-org",
                    "repo_name": "test-repo"
                }
            }
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    # 3. Initialize TitanConfig
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    config_instance = TitanConfig()

    # 4. Assert that AI config from global is preserved
    assert config_instance.config.ai is not None
    assert config_instance.config.ai.default == "anthropic-corp"
    assert "anthropic-corp" in config_instance.config.ai.providers

    provider = config_instance.config.ai.providers["anthropic-corp"]
    assert provider.name == "Corporate Claude"
    assert provider.type == "corporate"
    assert provider.provider == "anthropic"
    assert provider.model == "claude-3-5-sonnet-20241022"
    assert provider.base_url == "https://api.company.com/llm"

    # 5. Assert that project plugin config is also present
    assert config_instance.config.plugins is not None
    assert "github" in config_instance.config.plugins
    assert config_instance.config.plugins["github"].config["repo_owner"] == "test-org"


def test_project_can_override_ai_default_provider(tmp_path: Path, monkeypatch, mocker):
    """
    Test that a project can override the default AI provider while keeping global providers.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create global config with multiple AI providers
    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"
    global_config_data = {
        "core": {
            "project_root": str(tmp_path),
            "active_project": "test-project"
        },
        "ai": {
            "default": "anthropic-individual",
            "providers": {
                "anthropic-individual": {
                    "name": "Personal Claude",
                    "type": "individual",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "gemini-individual": {
                    "name": "Personal Gemini",
                    "type": "individual",
                    "provider": "gemini",
                    "model": "gemini-1.5-pro",
                    "temperature": 0.7,
                    "max_tokens": 4096
                }
            }
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 2. Create project config that overrides default provider
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_config_dir = project_dir / ".titan"
    project_config_dir.mkdir()
    project_config_path = project_config_dir / "config.toml"
    project_config_data = {
        "ai": {
            "default": "gemini-individual"  # Override default
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    # 3. Initialize TitanConfig
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    config_instance = TitanConfig()

    # 4. Assert that default was overridden but all providers are still available
    assert config_instance.config.ai.default == "gemini-individual"
    assert "anthropic-individual" in config_instance.config.ai.providers
    assert "gemini-individual" in config_instance.config.ai.providers


def test_project_can_add_additional_ai_providers(tmp_path: Path, monkeypatch, mocker):
    """
    Test that a project can add additional AI providers to supplement global ones.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create global config with one AI provider
    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"
    global_config_data = {
        "core": {
            "project_root": str(tmp_path),
            "active_project": "test-project"
        },
        "ai": {
            "default": "global-claude",
            "providers": {
                "global-claude": {
                    "name": "Global Claude",
                    "type": "individual",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.7,
                    "max_tokens": 4096
                }
            }
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 2. Create project config with an additional provider
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_config_dir = project_dir / ".titan"
    project_config_dir.mkdir()
    project_config_path = project_config_dir / "config.toml"
    project_config_data = {
        "ai": {
            "default": "project-gemini",  # Use project-specific provider as default
            "providers": {
                "project-gemini": {
                    "name": "Project Gemini",
                    "type": "corporate",
                    "provider": "gemini",
                    "model": "gemini-1.5-pro",
                    "temperature": 0.5,
                    "max_tokens": 8192,
                    "base_url": "https://gemini.company.com"
                }
            }
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    # 3. Initialize TitanConfig
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    config_instance = TitanConfig()

    # 4. Assert that both global and project providers are available
    assert config_instance.config.ai.default == "project-gemini"
    assert "global-claude" in config_instance.config.ai.providers
    assert "project-gemini" in config_instance.config.ai.providers

    # Verify global provider is unchanged
    global_provider = config_instance.config.ai.providers["global-claude"]
    assert global_provider.name == "Global Claude"
    assert global_provider.type == "individual"

    # Verify project provider
    project_provider = config_instance.config.ai.providers["project-gemini"]
    assert project_provider.name == "Project Gemini"
    assert project_provider.type == "corporate"
    assert project_provider.base_url == "https://gemini.company.com"


def test_ai_config_merge_preserves_both_sides(tmp_path: Path, monkeypatch, mocker):
    """
    Test that AI config merge preserves providers from BOTH global and project.
    This ensures nothing is lost from either side during merge.
    """
    # Mock PluginRegistry
    mocker.patch('titan_cli.core.config.PluginRegistry')

    # 1. Create global config with TWO providers
    global_config_dir = tmp_path / ".titan"
    global_config_dir.mkdir()
    global_config_path = global_config_dir / "config.toml"
    global_config_data = {
        "core": {
            "project_root": str(tmp_path),
            "active_project": "test-project"
        },
        "ai": {
            "default": "global-claude",
            "providers": {
                "global-claude": {
                    "name": "Global Claude",
                    "type": "individual",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                "global-gemini": {
                    "name": "Global Gemini",
                    "type": "individual",
                    "provider": "gemini",
                    "model": "gemini-1.5-pro",
                    "temperature": 0.7,
                    "max_tokens": 4096
                }
            }
        }
    }
    with open(global_config_path, "wb") as f:
        tomli_w.dump(global_config_data, f)

    # 2. Create project config with TWO DIFFERENT providers
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    project_config_dir = project_dir / ".titan"
    project_config_dir.mkdir()
    project_config_path = project_config_dir / "config.toml"
    project_config_data = {
        "ai": {
            "default": "project-claude",
            "providers": {
                "project-claude": {
                    "name": "Project Claude",
                    "type": "corporate",
                    "provider": "anthropic",
                    "model": "claude-3-opus-20240229",
                    "temperature": 0.5,
                    "max_tokens": 8192,
                    "base_url": "https://claude.company.com"
                },
                "project-openai": {
                    "name": "Project OpenAI",
                    "type": "corporate",
                    "provider": "openai",
                    "model": "gpt-4-turbo",
                    "temperature": 0.5,
                    "max_tokens": 8192,
                    "base_url": "https://openai.company.com"
                }
            }
        }
    }
    with open(project_config_path, "wb") as f:
        tomli_w.dump(project_config_data, f)

    # 3. Initialize TitanConfig
    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    config_instance = TitanConfig()

    # 4. Assert that ALL FOUR providers are available (2 global + 2 project)
    assert len(config_instance.config.ai.providers) == 4

    # Verify global providers are preserved
    assert "global-claude" in config_instance.config.ai.providers
    assert "global-gemini" in config_instance.config.ai.providers

    # Verify project providers are added
    assert "project-claude" in config_instance.config.ai.providers
    assert "project-openai" in config_instance.config.ai.providers

    # Verify default was overridden
    assert config_instance.config.ai.default == "project-claude"

    # Verify each provider has correct data
    assert config_instance.config.ai.providers["global-claude"].name == "Global Claude"
    assert config_instance.config.ai.providers["global-gemini"].name == "Global Gemini"
    assert config_instance.config.ai.providers["project-claude"].name == "Project Claude"
    assert config_instance.config.ai.providers["project-openai"].name == "Project OpenAI"
