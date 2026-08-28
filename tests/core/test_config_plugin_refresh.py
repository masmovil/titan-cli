"""
When reloading config rebuilds the plugin registry, and when it declines to.

Rebuilding imports and initializes every installed plugin - about a second,
against ten milliseconds for rereading the files - and every screen reloads on
resume. So the rule is: rebuild when something the registry depends on changed,
and not otherwise.
"""

from unittest.mock import MagicMock, patch

import pytest
import tomli_w

from titan_cli.core.config import TitanConfig


@pytest.fixture
def config_paths(tmp_path):
    """A global and a project config, both writable by the test."""
    global_path = tmp_path / "global" / "config.toml"
    global_path.parent.mkdir(parents=True)
    global_path.write_bytes(tomli_w.dumps({"ai": {}}).encode())

    project = tmp_path / "project"
    (project / ".titan").mkdir(parents=True)
    project_path = project / ".titan" / "config.toml"
    project_path.write_bytes(
        tomli_w.dumps({"project": {"name": "demo"}, "plugins": {"git": {"enabled": True}}}).encode()
    )

    return global_path, project, project_path


def _write_plugins(project_path, plugins: dict) -> None:
    project_path.write_bytes(
        tomli_w.dumps({"project": {"name": "demo"}, "plugins": plugins}).encode()
    )


@pytest.fixture
def config(config_paths, monkeypatch):
    """A TitanConfig with a stub registry, so rebuilds are countable."""
    global_path, project, _ = config_paths
    monkeypatch.chdir(project)

    registry = MagicMock()
    registry.list_failed.return_value = []
    registry.list_sync_events.return_value = []

    with patch("titan_cli.core.config.find_project_root", return_value=project):
        cfg = TitanConfig(registry=registry, global_config_path=global_path)

    return cfg


def _rebuilds(config) -> int:
    return config.registry.prepare.call_count


def test_the_first_load_builds_the_registry(config):
    assert _rebuilds(config) == 1


def test_reloading_unchanged_config_does_not_rebuild(config):
    """The status bar refreshes on every screen resume; it must stay cheap."""
    before = _rebuilds(config)

    config.load()
    config.load()
    config.load()

    assert _rebuilds(config) == before


def test_enabling_a_plugin_rebuilds(config, config_paths):
    _, _, project_path = config_paths
    before = _rebuilds(config)

    _write_plugins(project_path, {"git": {"enabled": True}, "github": {"enabled": True}})
    config.load()

    assert _rebuilds(config) == before + 1


def test_disabling_a_plugin_rebuilds(config, config_paths):
    _, _, project_path = config_paths
    before = _rebuilds(config)

    _write_plugins(project_path, {"git": {"enabled": False}})
    config.load()

    assert _rebuilds(config) == before + 1


def test_changing_a_plugins_settings_rebuilds(config, config_paths):
    """A plugin can read its own config while initializing."""
    _, _, project_path = config_paths
    before = _rebuilds(config)

    _write_plugins(project_path, {"git": {"enabled": True, "main_branch": "develop"}})
    config.load()

    assert _rebuilds(config) == before + 1


def test_a_second_reload_after_a_change_does_not_rebuild_again(config, config_paths):
    """The fingerprint updates when it rebuilds, or every later load rebuilds too."""
    _, _, project_path = config_paths

    _write_plugins(project_path, {"git": {"enabled": True}, "github": {"enabled": True}})
    config.load()
    after_change = _rebuilds(config)

    config.load()

    assert _rebuilds(config) == after_change


def test_installing_a_plugin_rebuilds_even_with_unchanged_config(config):
    """A plugin can appear mid-session; the config file says nothing about it."""
    before = _rebuilds(config)

    new_entry_point = MagicMock()
    new_entry_point.name = "freshly-installed"
    with patch("importlib.metadata.entry_points", return_value=[new_entry_point]):
        config.load()

    assert _rebuilds(config) == before + 1


def test_force_rebuilds_unchanged_config(config):
    """
    The escape hatch for state the fingerprint cannot see - a stored credential
    a plugin reads while initializing, which lives outside the config files.
    """
    before = _rebuilds(config)

    config.load(force_plugin_init=True)

    assert _rebuilds(config) == before + 1


def test_skip_plugin_init_still_skips(config):
    before = _rebuilds(config)

    config.load(skip_plugin_init=True)

    assert _rebuilds(config) == before


def test_config_values_are_reread_even_when_the_registry_is_reused(config, config_paths):
    """
    The cheap path must still be a real reload.

    Skipping the rebuild would be worthless if it also meant serving stale
    values - that is the whole reason callers reload in the first place.
    """
    global_path, _, _ = config_paths
    before = _rebuilds(config)

    global_path.write_bytes(
        tomli_w.dumps({"ai": {"default_connection": "work"}}).encode()
    )
    config.load()

    assert config.config.ai.default_connection == "work"
    assert _rebuilds(config) == before
