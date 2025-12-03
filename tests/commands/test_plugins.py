import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, PropertyMock

from titan_cli.cli import app
from titan_cli.core.config import TitanConfig
from titan_cli.core.plugin_base import TitanPlugin
from titan_cli.core.errors import PluginLoadError, PluginInitializationError

runner = CliRunner()

# --- Fixtures and Mocks ---
@pytest.fixture
def mock_titan_plugin():
    """Returns a mock TitanPlugin instance."""
    mock_plugin = MagicMock(spec=TitanPlugin)
    mock_plugin.name = "mock-plugin"
    mock_plugin.version = "1.0.0"
    mock_plugin.is_available.return_value = True
    return mock_plugin

@pytest.fixture
def mock_failed_plugin():
    """Returns a mock TitanPlugin instance that is not available."""
    mock_plugin = MagicMock(spec=TitanPlugin)
    mock_plugin.name = "failed-plugin"
    mock_plugin.version = "0.9.0"
    mock_plugin.is_available.return_value = False
    return mock_plugin

@pytest.fixture
def mock_registry(mocker, mock_titan_plugin, mock_failed_plugin):
    """Mocks the PluginRegistry with various plugin states."""
    mock_reg = MagicMock()
    
    # Successful plugins
    mocker.patch.object(mock_titan_plugin, 'name', new_callable=PropertyMock(return_value='success-plugin-1'))
    mocker.patch.object(mock_titan_plugin, 'version', new_callable=PropertyMock(return_value='1.0.0'))
    mock_titan_plugin.is_available.return_value = True

    mock_reg.list_installed.return_value = ['success-plugin-1']
    mock_reg.get_plugin.side_effect = lambda name: mock_titan_plugin if name == 'success-plugin-1' else None

    # Failed plugins
    mock_load_error = PluginLoadError(
        plugin_name="load-fail-plugin",
        original_exception=Exception("Test load error")
    )
    mock_init_error = PluginInitializationError(
        plugin_name="init-fail-plugin",
        original_exception=ValueError("Test init error")
    )
    mock_reg.list_failed.return_value = {
        "load-fail-plugin": mock_load_error,
        "init-fail-plugin": mock_init_error,
    }
    
    return mock_reg

@pytest.fixture(autouse=True)
def mock_titan_config(mocker, mock_registry):
    """Mocks TitanConfig to return our mock registry."""
    # Patch the class in the module where it's instantiated
    mock_config_class = mocker.patch('titan_cli.commands.plugins.TitanConfig', autospec=True)
    
    # Get the instance that will be created when TitanConfig() is called
    mock_instance = mock_config_class.return_value
    
    # Configure the instance's registry property
    type(mock_instance).registry = PropertyMock(return_value=mock_registry)
    
    return mock_instance

# --- Tests for 'titan plugins list' ---
def test_list_plugins_no_plugins(mocker, mock_titan_config):
    """Test 'titan plugins list' when no plugins are installed or all failed silently."""
    mock_titan_config.registry.list_installed.return_value = []
    mock_titan_config.registry.list_failed.return_value = {}

    result = runner.invoke(app, ["plugins", "list"])

    assert result.exit_code == 0
    assert "Installed Plugins" in result.stdout
    assert "Plugin" in result.stdout # Check for table header
    assert "No plugins found" not in result.stdout # Should display empty table, not "no plugins found"
    assert "failed to load or initialize" not in result.stdout


def test_list_plugins_with_successful_plugins(mock_titan_config, mock_titan_plugin):
    """Test 'titan plugins list' with successfully loaded plugins."""
    mock_titan_config.registry.list_installed.return_value = ['success-plugin-1']
    mock_titan_config.registry.get_plugin.return_value = mock_titan_plugin
    mock_titan_config.registry.list_failed.return_value = {}

    result = runner.invoke(app, ["plugins", "list"])

    assert result.exit_code == 0
    assert "Installed Plugins" in result.stdout
    assert "success-plugin-1" in result.stdout
    assert "1.0.0" in result.stdout
    assert "Available" in result.stdout
    assert "failed to load or initialize" not in result.stdout


def test_list_plugins_with_failed_plugins(mock_titan_config, mock_registry):
    """Test 'titan plugins list' with plugins that failed to load or initialize."""
    mock_titan_config.registry.list_installed.return_value = [] # No successfully installed plugins
    
    # mock_registry already configured with failed plugins
    mock_titan_config.registry.list_failed.return_value = mock_registry.list_failed.return_value

    result = runner.invoke(app, ["plugins", "list"])

    assert result.exit_code == 0
    assert "Installed Plugins" in result.stdout
    assert "2 plugin(s) failed to load or initialize:" in result.stdout
    assert "load-fail-plugin" in result.stdout
    assert "init-fail-plugin" in result.stdout
    assert "Test load error" in result.stdout
    assert "Test init error" in result.stdout
    assert "Failed" in result.stdout # Panel title

# --- Tests for 'titan plugins doctor' ---
def test_doctor_no_plugins(mock_titan_config):
    """Test 'titan plugins doctor' when no plugins are installed or all failed silently."""
    mock_titan_config.registry.list_installed.return_value = []
    mock_titan_config.registry.list_failed.return_value = {}

    result = runner.invoke(app, ["plugins", "doctor"])

    assert result.exit_code == 0
    assert "Plugin Health Check" in result.stdout
    assert "All plugins are healthy!" in result.stdout
    assert "failed to load" not in result.stdout


def test_doctor_with_healthy_plugins(mock_titan_config, mock_titan_plugin):
    """Test 'titan plugins doctor' with healthy plugins."""
    mock_titan_config.registry.list_installed.return_value = ['healthy-plugin']
    # Configure get_plugin to return a healthy plugin for the correct name
    mock_titan_config.registry.get_plugin.side_effect = lambda name: mock_titan_plugin if name == 'healthy-plugin' else None
    mock_titan_config.registry.list_failed.return_value = {}

    result = runner.invoke(app, ["plugins", "doctor"])

    assert result.exit_code == 0
    assert "Plugin Health Check" in result.stdout
    assert "Checking healthy-plugin..." in result.stdout
    assert "healthy-plugin is healthy" in result.stdout
    assert "All plugins are healthy!" in result.stdout
    assert "failed to load" not in result.stdout


def test_doctor_with_unavailable_successful_plugin(mock_titan_config, mock_failed_plugin):
    """
    Test 'titan plugins doctor' with a plugin that loaded successfully but is_available() is False.
    This simulates a plugin that has missing system dependencies.
    """
    mock_titan_config.registry.list_installed.return_value = ['unavailable-plugin']
    mock_titan_config.registry.get_plugin.return_value = mock_failed_plugin
    mock_titan_config.registry.list_failed.return_value = {}

    result = runner.invoke(app, ["plugins", "doctor"])

    assert result.exit_code == 1 # Should exit with error due to unavailable plugin
    assert "Plugin Health Check" in result.stdout
    assert "Checking unavailable-plugin..." in result.stdout
    assert "unavailable-plugin' is not available" in result.stdout
    assert "Some plugins have issues." in result.stdout
    assert "All plugins are healthy!" not in result.stdout
    assert "failed to load" not in result.stdout


def test_doctor_with_failed_plugins(mock_titan_config, mock_registry):
    """Test 'titan plugins doctor' with plugins that failed to load or initialize."""
    mock_titan_config.registry.list_installed.return_value = [] # No successfully installed plugins
    
    # mock_registry already configured with failed plugins
    mock_titan_config.registry.list_failed.return_value = mock_registry.list_failed.return_value

    result = runner.invoke(app, ["plugins", "doctor"])

    assert result.exit_code == 1 # Should exit with error due to failed plugins
    assert "Plugin Health Check" in result.stdout
    assert "2 plugin(s) failed to load:" in result.stdout
    assert "load-fail-plugin" in result.stdout
    assert "init-fail-plugin" in result.stdout
    assert "Test load error" in result.stdout
    assert "Test init error" in result.stdout
    assert "Failed to Load" in result.stdout # Panel title
    assert "Some plugins have issues." in result.stdout
    assert "All plugins are healthy!" not in result.stdout