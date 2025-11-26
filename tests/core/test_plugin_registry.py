# tests/core/test_plugin_registry.py
import pytest
from unittest.mock import MagicMock, patch
from titan_cli.core.plugin_registry import PluginRegistry
from titan_cli.core.errors import PluginLoadError

# A simple mock class to represent a loaded plugin
class MockPlugin:
    pass

def test_plugin_registry_discovery_success(mocker):
    """
    Test that PluginRegistry successfully discovers and loads plugins.
    """
    # 1. Create mock entry points
    mock_ep1 = MagicMock()
    mock_ep1.name = "plugin_one"
    mock_ep1.load.return_value = MockPlugin

    mock_ep2 = MagicMock()
    mock_ep2.name = "plugin_two"
    mock_ep2.load.return_value = MockPlugin

    # 2. Patch 'importlib.metadata.entry_points' to return our mocks
    mocker.patch(
        "titan_cli.core.plugin_registry.entry_points",
        return_value=[mock_ep1, mock_ep2]
    )

    # 3. Initialize the registry
    registry = PluginRegistry()

    # 4. Assertions
    installed_plugins = registry.list_installed()
    assert len(installed_plugins) == 2
    assert "plugin_one" in installed_plugins
    assert "plugin_two" in installed_plugins

    # Check that get_plugin returns an instance of the loaded class
    plugin_instance = registry.get_plugin("plugin_one")
    assert isinstance(plugin_instance, MockPlugin)

def test_plugin_registry_handles_load_failure(mocker, capsys):
    """
    Test that PluginRegistry gracefully handles a plugin that fails to load.
    """
    # 1. Create mock entry points, one of which will fail
    mock_ep1 = MagicMock()
    mock_ep1.name = "plugin_good"
    mock_ep1.load.return_value = MockPlugin

    mock_ep_bad = MagicMock()
    mock_ep_bad.name = "plugin_bad"
    mock_ep_bad.load.side_effect = ImportError("Something went wrong")

    # 2. Patch 'importlib.metadata.entry_points'
    mocker.patch(
        "titan_cli.core.plugin_registry.entry_points",
        return_value=[mock_ep1, mock_ep_bad]
    )

    # 3. Initialize the registry
    registry = PluginRegistry()

    # 4. Assertions
    # Check that the good plugin was still loaded
    installed_plugins = registry.list_installed()
    assert len(installed_plugins) == 1
    assert "plugin_good" in installed_plugins
    assert "plugin_bad" not in installed_plugins

    # Check that a warning was printed for the bad plugin
    captured = capsys.readouterr()
    output = captured.err + captured.out
    assert "Warning: Failed to load plugin 'plugin_bad'" in output
    assert "Something went wrong" in output # Check for the exception message, not its type

