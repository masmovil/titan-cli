# tests/core/test_config_ai_preferences.py
"""Persistence of AI routing preferences (one provider choice per AI task)."""

from pathlib import Path

import pytest
import tomli
import tomli_w

from titan_cli.core.config import TitanConfig


@pytest.fixture
def config(tmp_path: Path, monkeypatch, mocker) -> TitanConfig:
    """A TitanConfig backed by a throwaway global config file."""
    mocker.patch("titan_cli.core.config.PluginRegistry")

    global_config_path = tmp_path / ".titan" / "config.toml"
    global_config_path.parent.mkdir(parents=True)
    with open(global_config_path, "wb") as f:
        tomli_w.dump({"config_version": "1.0"}, f)

    monkeypatch.setattr(TitanConfig, "GLOBAL_CONFIG", global_config_path)
    monkeypatch.chdir(tmp_path)
    return TitanConfig()


def _written_preferences(config: TitanConfig) -> dict:
    with open(TitanConfig.GLOBAL_CONFIG, "rb") as f:
        return tomli.load(f).get("ai", {}).get("preferences", {})


def test_task_preference_roundtrips_to_disk(config: TitanConfig):
    config.upsert_task_ai_preference("commit_message", {"provider": "cli_headless"})

    written = _written_preferences(config)
    assert written["tasks"]["commit_message"] == {"provider": "cli_headless"}


def test_a_task_preference_stores_only_the_provider_kind(config: TitanConfig):
    """
    Which CLI or connection runs the task is a global setting, so it must not be copied
    into every task - one place to change it, not one per task.
    """
    config.upsert_task_ai_preference("commit_message", {"provider": "cli_headless"})

    stored = _written_preferences(config)["tasks"]["commit_message"]
    assert set(stored) == {"provider"}


def test_task_preference_is_visible_in_memory_without_reloading(config: TitanConfig):
    """
    TitanConfig lives for the whole session, so a write must also update the
    parsed model - a step resolving a route right after must see the new value.
    """
    config.upsert_task_ai_preference("commit_message", {"provider": "off"})

    assert config.config.ai.preferences.tasks["commit_message"].provider == "off"


def test_deleting_a_task_preference_removes_it(config: TitanConfig):
    config.upsert_task_ai_preference("commit_message", {"provider": "remote"})

    config.delete_task_ai_preference("commit_message")

    assert _written_preferences(config)["tasks"] == {}
    assert config.config.ai.preferences.tasks == {}


def test_deleting_an_absent_task_preference_is_a_no_op(config: TitanConfig):
    config.delete_task_ai_preference("never_configured")

    assert _written_preferences(config).get("tasks", {}) == {}


def test_preferences_survive_a_full_reload(config: TitanConfig):
    config.upsert_task_ai_preference("pr_description", {"provider": "remote"})

    reloaded = TitanConfig()

    preference = reloaded.config.ai.preferences.tasks["pr_description"]
    assert preference.provider == "remote"


def test_default_cli_roundtrips_and_can_be_cleared(config: TitanConfig):
    config.set_default_ai_cli("claude")

    reloaded = TitanConfig()
    assert reloaded.config.ai.default_cli == "claude"

    config.clear_default_ai_cli()

    assert TitanConfig().config.ai.default_cli is None


def test_setting_a_default_cli_works_without_any_ai_connection(config: TitanConfig):
    """A CLI-only setup has no default connection, which TOML cannot store as a null."""
    config.set_default_ai_cli("claude")

    with open(TitanConfig.GLOBAL_CONFIG, "rb") as f:
        ai_section = tomli.load(f)["ai"]

    assert ai_section["default_cli"] == "claude"
    assert "default_connection" not in ai_section


def test_only_task_scope_is_persisted(config: TitanConfig):
    """The task is the only preference scope - nothing else is written."""
    config.upsert_task_ai_preference("commit_message", {"provider": "remote"})

    assert set(_written_preferences(config).keys()) == {"tasks"}
