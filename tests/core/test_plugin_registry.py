# tests/core/test_plugin_registry.py
from unittest.mock import MagicMock

from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.core.errors import PluginLoadError
from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.plugins.community_sources import PluginChannel
from titan_cli.core.plugins.runtime import PluginRuntimePaths, PluginRuntimeResult
from titan_cli.core.config import TitanConfig
from titan_cli.core.security import SecretBroker, SecretBrokerFactory


# A proper mock class to represent a loaded plugin
class MockPlugin(TitanPlugin):
    _name = "mock-plugin"
    _dependencies = []

    def __init__(self):
        self._initialized = False
        self.received_config = None
        self.received_broker = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Description for {self._name}"

    @property
    def dependencies(self) -> list[str]:
        return self._dependencies

    def initialize(self, config: TitanConfig, broker: SecretBroker) -> None:
        self._initialized = True
        self.received_config = config
        self.received_broker = broker

    def is_available(self) -> bool:
        return True

class MockDependentPlugin(MockPlugin):
    _name = "dependent-plugin"
    _dependencies = ["plugin_one"]


def test_plugin_registry_discovery_success(mocker):
    """
    Test that PluginRegistry successfully discovers and loads plugins.
    """
    mock_ep1 = MagicMock()
    mock_ep1.name = "plugin_one"
    
    # Create a new class for each mock plugin to have a different name
    PluginOne = type("PluginOne", (MockPlugin,), {"_name": "plugin_one"})
    mock_ep1.load.return_value = PluginOne

    mock_ep2 = MagicMock()
    mock_ep2.name = "plugin_two"
    PluginTwo = type("PluginTwo", (MockPlugin,), {"_name": "plugin_two"})
    mock_ep2.load.return_value = PluginTwo

    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[mock_ep1, mock_ep2]
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()

    installed_plugins = registry.list_installed()
    assert len(installed_plugins) == 2
    assert "plugin_one" in installed_plugins
    assert "plugin_two" in installed_plugins

    plugin_instance = registry.get_plugin("plugin_one")
    assert isinstance(plugin_instance, PluginOne)
    assert plugin_instance.name == "plugin_one"


def test_plugin_registry_handles_load_failure(mocker, capsys):
    """
    Test that PluginRegistry gracefully handles a plugin that fails to load or is invalid.
    """
    class InvalidPlugin: # Does not inherit from TitanPlugin
        pass

    mock_ep1 = MagicMock()
    mock_ep1.name = "plugin_good"
    PluginGood = type("PluginGood", (MockPlugin,), {"_name": "plugin_good"})
    mock_ep1.load.return_value = PluginGood

    mock_ep_bad_import = MagicMock()
    mock_ep_bad_import.name = "plugin_bad_import"
    mock_ep_bad_import.load.side_effect = ImportError("Something went wrong during import")

    mock_ep_bad_type = MagicMock()
    mock_ep_bad_type.name = "plugin_bad_type"
    mock_ep_bad_type.load.return_value = InvalidPlugin

    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[mock_ep1, mock_ep_bad_import, mock_ep_bad_type]
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()

    installed_plugins = registry.list_installed()
    assert len(installed_plugins) == 1
    assert "plugin_good" in installed_plugins
    
    failed_plugins = registry.list_failed()
    assert len(failed_plugins) == 2
    assert "plugin_bad_import" in failed_plugins
    assert "plugin_bad_type" in failed_plugins

    assert isinstance(failed_plugins["plugin_bad_import"], PluginLoadError)
    assert "Something went wrong during import" in str(failed_plugins["plugin_bad_import"])

    assert isinstance(failed_plugins["plugin_bad_type"], PluginLoadError)
    assert "Plugin class must inherit from TitanPlugin" in str(failed_plugins["plugin_bad_type"])


def test_plugin_registry_dependency_resolution(mocker):
    """
    Test that plugins are initialized in correct dependency order.
    """
    mock_ep_p1 = MagicMock()
    mock_ep_p1.name = "plugin_one"
    PluginOne = type("PluginOne", (MockPlugin,), {"_name": "plugin_one"})
    mock_ep_p1.load.return_value = PluginOne

    mock_ep_p2 = MagicMock()
    mock_ep_p2.name = "plugin_two"
    PluginTwo = type("PluginTwo", (MockDependentPlugin,), {"_name": "plugin_two"})
    mock_ep_p2.load.return_value = PluginTwo

    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[mock_ep_p2, mock_ep_p1] # Load dependent first to test sorting
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    
    mock_config = MagicMock(spec=TitanConfig)
    mock_broker_factory = MagicMock(spec=SecretBrokerFactory)

    registry.prepare(mock_config, mock_broker_factory)
    registry.ensure_all_initialized()

    plugin_one = registry.get_plugin("plugin_one")
    plugin_two = registry.get_plugin("plugin_two")

    assert plugin_one._initialized
    assert plugin_two._initialized


def test_plugin_registry_unresolved_dependency(mocker):
    """
    Test that PluginRegistry raises an error for unresolved dependencies.
    """
    mock_ep_dep = MagicMock()
    mock_ep_dep.name = "plugin_dependent"
    DependentPlugin = type("DependentPlugin", (MockDependentPlugin,), {"_name": "plugin_dependent", "_dependencies": ["non-existent"]})
    mock_ep_dep.load.return_value = DependentPlugin

    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[mock_ep_dep]
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    
    mock_config = MagicMock(spec=TitanConfig)
    mock_broker_factory = MagicMock(spec=SecretBrokerFactory)

    registry.prepare(mock_config, mock_broker_factory)
    registry.ensure_all_initialized()

    failed_plugins = registry.list_failed()
    assert "plugin_dependent" in failed_plugins
    assert "Dependency 'non-existent' failed to load/initialize" in str(failed_plugins["plugin_dependent"])


def test_plugin_registry_plugin_initialization_context(mocker):
    """
    Test that config and a plugin-scoped broker are passed to plugin initialize.
    """
    mock_ep = MagicMock()
    mock_ep.name = "test_plugin"
    TestPlugin = type("TestPlugin", (MockPlugin,), {"_name": "test_plugin"})
    mock_ep.load.return_value = TestPlugin

    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[mock_ep]
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    
    mock_config = MagicMock(spec=TitanConfig)
    mock_broker_factory = MagicMock(spec=SecretBrokerFactory)

    registry.prepare(mock_config, mock_broker_factory)
    registry.ensure_all_initialized()

    plugin_instance = registry.get_plugin("test_plugin")
    assert plugin_instance.received_config is mock_config
    assert plugin_instance.received_broker is mock_broker_factory.for_plugin.return_value
    mock_broker_factory.for_plugin.assert_called_once_with("test_plugin")


def test_apply_source_overrides_loads_dev_local_plugin(tmp_path, mocker):
    plugin_dir = tmp_path / "plugin_repo"
    plugin_dir.mkdir()
    package_dir = plugin_dir / "sample_plugin"
    package_dir.mkdir()

    (plugin_dir / "pyproject.toml").write_text(
        """
[project]
name = "sample-plugin"
version = "0.1.0"

[project.entry-points."titan.plugins"]
sample = "sample_plugin.plugin:SamplePlugin"
""".strip(),
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "plugin.py").write_text(
        """
from titan_cli.core.plugins.plugin_base import TitanPlugin


class SamplePlugin(TitanPlugin):
    @property
    def name(self) -> str:
        return "sample"

    @property
    def dependencies(self) -> list[str]:
        return []

    def initialize(self, config, secrets) -> None:
        self.initialized = True

    def get_steps(self) -> dict:
        return {}
""".strip(),
        encoding="utf-8",
    )

    registry = PluginRegistry(discover_on_init=False)
    config = MagicMock()
    config.config = MagicMock()
    config.config.plugins = {"sample": MagicMock(enabled=True)}
    config.get_enabled_plugins.return_value = ["sample"]
    config.get_plugin_source_channel.return_value = PluginChannel.DEV_LOCAL
    config.get_plugin_source_path.return_value = plugin_dir

    registry._apply_source_overrides(config)

    plugin = registry.get_plugin("sample")
    assert plugin is not None
    assert plugin.name == "sample"
    assert registry.get_plugin_version("sample") == "dev_local"
    assert "sample" in registry.list_discovered()


def test_apply_source_overrides_loads_project_stable_runtime(tmp_path, mocker):
    plugin_dir = tmp_path / "stable_plugin"
    plugin_dir.mkdir()
    package_dir = plugin_dir / "sample_plugin"
    package_dir.mkdir()
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()

    (plugin_dir / "pyproject.toml").write_text(
        """
[project]
name = "sample-plugin"
version = "0.1.0"

[project.entry-points."titan.plugins"]
sample = "sample_plugin.plugin:SamplePlugin"
""".strip(),
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "plugin.py").write_text(
        """
from titan_cli.core.plugins.plugin_base import TitanPlugin


class SamplePlugin(TitanPlugin):
    @property
    def name(self) -> str:
        return "sample"

    @property
    def dependencies(self) -> list[str]:
        return []

    def initialize(self, config, secrets) -> None:
        self.initialized = True

    def get_steps(self) -> dict:
        return {}
""".strip(),
        encoding="utf-8",
    )

    registry = PluginRegistry(discover_on_init=False)
    mocker.patch.object(
        registry._runtime_manager,
        "ensure_stable_runtime",
        return_value=PluginRuntimeResult(
            paths=PluginRuntimePaths(
                cache_dir=tmp_path / "cache",
                source_dir=plugin_dir,
                venv_dir=tmp_path / "venv",
                site_packages=site_packages,
            ),
            created=True,
        ),
    )

    config = MagicMock()
    config.config = MagicMock()
    config.config.plugins = {"sample": MagicMock(enabled=True)}
    config.get_enabled_plugins.return_value = ["sample"]
    config.get_plugin_source_channel.return_value = PluginChannel.STABLE
    config.get_plugin_source_path.return_value = None
    config.get_project_plugin_repo_url.return_value = "https://github.com/example/sample-plugin"
    config.get_project_plugin_requested_ref.return_value = "v1.2.3"
    config.get_project_plugin_resolved_commit.return_value = "a" * 40

    registry._apply_source_overrides(config)

    plugin = registry.get_plugin("sample")
    assert plugin is not None
    assert plugin.name == "sample"
    assert registry.get_plugin_version("sample") == f"stable@{'a' * 12}"
    assert "sample" in registry.list_discovered()
    assert registry.list_sync_events() == ["Syncing plugin 'sample' to project version v1.2.3."]


def test_apply_source_overrides_marks_missing_path_as_failure():
    registry = PluginRegistry(discover_on_init=False)
    registry._plugins["sample"] = MagicMock()

    config = MagicMock()
    config.config = MagicMock()
    config.config.plugins = {"sample": MagicMock(enabled=True)}
    config.get_enabled_plugins.return_value = ["sample"]
    config.get_plugin_source_channel.return_value = PluginChannel.DEV_LOCAL
    config.get_plugin_source_path.return_value = None

    registry._apply_source_overrides(config)

    failed_plugins = registry.list_failed()
    assert "sample" in failed_plugins
    assert isinstance(failed_plugins["sample"], PluginLoadError)
    assert "dev_local source requires a local path" in str(failed_plugins["sample"])
    assert registry.get_plugin("sample") is None


def test_list_enabled_delegates_to_config_effective_enabled_plugins():
    registry = PluginRegistry(discover_on_init=False)

    config = MagicMock()
    config.get_enabled_plugins.return_value = ["git", "github"]

    assert registry.list_enabled(config) == ["git", "github"]
    config.get_enabled_plugins.assert_called_once_with()


# ---------------------------------------------------------------------------
# titan-cli compatibility gate in _load_local_plugin
# ---------------------------------------------------------------------------

from titan_cli.core.errors import PluginIncompatibleError  # noqa: E402
from titan_cli.core.plugins.plugin_registry import _load_local_plugin  # noqa: E402


def _write_sample_plugin(plugin_dir, pyproject_extra="", plugin_body=None):
    plugin_dir.mkdir()
    package_dir = plugin_dir / "sample_plugin"
    package_dir.mkdir()
    (plugin_dir / "pyproject.toml").write_text(
        f"""
[project]
name = "sample-plugin"
version = "0.1.0"
{pyproject_extra}

[project.entry-points."titan.plugins"]
sample = "sample_plugin.plugin:SamplePlugin"
""".strip(),
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "plugin.py").write_text(
        plugin_body
        or """
from titan_cli.core.plugins.plugin_base import TitanPlugin


class SamplePlugin(TitanPlugin):
    @property
    def name(self) -> str:
        return "sample"
""".strip(),
        encoding="utf-8",
    )


def test_load_local_plugin_rejects_incompatible_declared_bound(tmp_path):
    plugin_dir = tmp_path / "incompatible_plugin"
    _write_sample_plugin(
        plugin_dir,
        pyproject_extra='dependencies = ["titan-cli>=999.0"]',
    )

    import pytest

    with pytest.raises(PluginIncompatibleError) as excinfo:
        _load_local_plugin(plugin_dir, "sample")

    assert "requires titan-cli >=999.0" in str(excinfo.value)


def test_load_local_plugin_translates_missing_titan_api_to_incompatibility(tmp_path):
    plugin_dir = tmp_path / "stale_api_plugin"
    _write_sample_plugin(
        plugin_dir,
        plugin_body="""
from titan_cli.core.module_that_never_existed import Something
from titan_cli.core.plugins.plugin_base import TitanPlugin


class SamplePlugin(TitanPlugin):
    @property
    def name(self) -> str:
        return "sample"
""".strip(),
    )

    import pytest

    with pytest.raises(PluginIncompatibleError) as excinfo:
        _load_local_plugin(plugin_dir, "sample")

    assert "does not exist in titan-cli" in str(excinfo.value)


def test_load_local_plugin_propagates_unrelated_missing_modules(tmp_path):
    plugin_dir = tmp_path / "broken_dep_plugin"
    _write_sample_plugin(
        plugin_dir,
        plugin_body="""
import package_that_is_not_installed
from titan_cli.core.plugins.plugin_base import TitanPlugin


class SamplePlugin(TitanPlugin):
    @property
    def name(self) -> str:
        return "sample"
""".strip(),
    )

    import pytest

    with pytest.raises(ModuleNotFoundError):
        _load_local_plugin(plugin_dir, "sample")


# ---------------------------------------------------------------------------
# Lazy initialization contract
# ---------------------------------------------------------------------------

def _registry_with(mocker, *plugin_classes):
    eps = []
    for cls in plugin_classes:
        ep = MagicMock()
        ep.name = cls._name
        ep.load.return_value = cls
        eps.append(ep)
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=eps,
    )
    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    return registry


def test_prepare_does_not_initialize_anything(mocker):
    Lazy = type("Lazy", (MockPlugin,), {"_name": "lazy_one"})
    registry = _registry_with(mocker, Lazy)

    registry.prepare(MagicMock(spec=TitanConfig), MagicMock(spec=SecretBrokerFactory))

    assert not registry.get_plugin("lazy_one")._initialized
    assert not registry.is_initialized("lazy_one")


def test_ensure_initialized_initializes_once_on_first_use(mocker):
    calls = []

    class Counting(MockPlugin):
        _name = "counting"

        def initialize(self, config, broker):
            calls.append(1)
            super().initialize(config, broker)

    registry = _registry_with(mocker, Counting)
    registry.prepare(MagicMock(spec=TitanConfig), MagicMock(spec=SecretBrokerFactory))

    first = registry.ensure_initialized("counting")
    second = registry.ensure_initialized("counting")

    assert first is second is registry.get_plugin("counting")
    assert calls == [1]
    assert registry.is_initialized("counting")


def test_ensure_initialized_initializes_dependencies_first(mocker):
    order = []

    class Base(MockPlugin):
        _name = "base_plugin"

        def initialize(self, config, broker):
            order.append(self._name)
            super().initialize(config, broker)

    class Dependent(Base):
        _name = "dependent_lazy"
        _dependencies = ["base_plugin"]

    registry = _registry_with(mocker, Dependent, Base)
    registry.prepare(MagicMock(spec=TitanConfig), MagicMock(spec=SecretBrokerFactory))

    assert registry.ensure_initialized("dependent_lazy") is not None
    assert order == ["base_plugin", "dependent_lazy"]


def test_ensure_initialized_returns_none_for_disabled_plugin(mocker):
    Lazy = type("Lazy", (MockPlugin,), {"_name": "disabled_one"})
    registry = _registry_with(mocker, Lazy)

    config = MagicMock(spec=TitanConfig)
    config.is_plugin_enabled.return_value = False
    registry.prepare(config, MagicMock(spec=SecretBrokerFactory))

    assert registry.ensure_initialized("disabled_one") is None
    # Never even loaded: disabled plugins stay as entry-point metadata.
    assert registry.get_plugin("disabled_one") is None
    assert "disabled_one" not in registry.list_failed()


def test_ensure_initialized_returns_none_before_prepare(mocker):
    Lazy = type("Lazy", (MockPlugin,), {"_name": "unprepared"})
    registry = _registry_with(mocker, Lazy)

    assert registry.ensure_initialized("unprepared") is None
    assert registry.get_plugin("unprepared") is None


def test_init_failure_is_sticky_until_next_prepare(mocker):
    attempts = []

    class Flaky(MockPlugin):
        _name = "flaky"

        def initialize(self, config, broker):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("credential missing")
            super().initialize(config, broker)

    registry = _registry_with(mocker, Flaky)
    config = MagicMock(spec=TitanConfig)
    factory = MagicMock(spec=SecretBrokerFactory)
    registry.prepare(config, factory)

    assert registry.ensure_initialized("flaky") is None
    assert "flaky" in registry.list_failed()
    # Sticky: no retry within the same build
    assert registry.ensure_initialized("flaky") is None
    assert attempts == [1]

    # A new prepare (what force_plugin_init produces) clears it and retries
    registry.prepare(config, factory)
    assert "flaky" not in registry.list_failed()
    assert registry.ensure_initialized("flaky") is not None
    assert attempts == [1, 1]


def test_prepare_keeps_load_failures(mocker):
    bad_ep = MagicMock()
    bad_ep.name = "broken_import"
    bad_ep.load.side_effect = ImportError("boom")
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[bad_ep],
    )
    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()
    assert "broken_import" in registry.list_failed()

    registry.prepare(MagicMock(spec=TitanConfig), MagicMock(spec=SecretBrokerFactory))

    # prepare clears initialization failures, never load failures
    assert "broken_import" in registry.list_failed()


def test_ensure_initialized_is_thread_safe(mocker):
    import threading as _threading

    started = _threading.Event()
    calls = []

    class Slow(MockPlugin):
        _name = "slow_plugin"

        def initialize(self, config, broker):
            started.set()
            calls.append(1)
            super().initialize(config, broker)

    registry = _registry_with(mocker, Slow)
    registry.prepare(MagicMock(spec=TitanConfig), MagicMock(spec=SecretBrokerFactory))

    results = []
    threads = [
        _threading.Thread(target=lambda: results.append(registry.ensure_initialized("slow_plugin")))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls == [1]
    assert all(r is registry.get_plugin("slow_plugin") for r in results)


def test_import_failure_traceback_logged_once_per_session(mocker):
    bad_ep = MagicMock()
    bad_ep.name = "always_broken"
    bad_ep.load.side_effect = ImportError("no such module")
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[bad_ep],
    )
    mock_logger = mocker.patch("titan_cli.core.plugins.plugin_registry.logger")

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()
    registry.reset()  # re-discovers: same broken import fails again on load
    registry.load_all()
    registry.reset()  # and a third time
    registry.load_all()

    # Full traceback exactly once; later cycles get a one-line warning.
    exception_calls = [
        c for c in mock_logger.exception.call_args_list
        if c.args and c.args[0] == "plugin_load_failed"
    ]
    warning_calls = [
        c for c in mock_logger.warning.call_args_list
        if c.args and c.args[0] == "plugin_load_failed"
    ]
    assert len(exception_calls) == 1
    assert len(warning_calls) == 2
    # The failure itself is still recorded every cycle.
    assert "always_broken" in registry.list_failed()


# ---------------------------------------------------------------------------
# Plugin version contract at discovery
# ---------------------------------------------------------------------------

def test_discover_prefers_plugin_declared_version_over_distribution(mocker):
    class Versioned(MockPlugin):
        _name = "versioned"

        @property
        def version(self):
            return "2.3.4"

    ep = MagicMock()
    ep.name = "versioned"
    ep.load.return_value = Versioned
    ep.dist.version = "0.8.0"  # the bundling distribution (titan-cli itself)
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[ep],
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()

    assert registry.get_plugin_version("versioned") == "2.3.4"


def test_discover_falls_back_to_distribution_version(mocker):
    # MockPlugin's package (this test module's root) declares no __version__,
    # so plugin.version is None and the owning distribution's version is used
    # - the correct answer for a third-party plugin installed as its own dist.
    Plain = type("Plain", (MockPlugin,), {"_name": "plain"})
    ep = MagicMock()
    ep.name = "plain"
    ep.load.return_value = Plain
    ep.dist.version = "3.1.4"
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[ep],
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()

    assert registry.get_plugin_version("plain") == "3.1.4"


def test_incompatible_plugin_is_recorded_failed_with_legible_message(mocker):
    class TooNew(MockPlugin):
        _name = "too_new"

        @property
        def titan_requires(self):
            return ">=999.0"

    ep = MagicMock()
    ep.name = "too_new"
    ep.load.return_value = TooNew
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[ep],
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()

    assert registry.get_plugin("too_new") is None
    failure = registry.list_failed()["too_new"]
    assert "requires titan-cli >=999.0" in str(failure)


def test_compatible_requirement_loads_normally(mocker):
    class Compatible(MockPlugin):
        _name = "compatible"

        @property
        def titan_requires(self):
            return ">=0.1"

    ep = MagicMock()
    ep.name = "compatible"
    ep.load.return_value = Compatible
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[ep],
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.load_all()

    assert registry.get_plugin("compatible") is not None
    assert "compatible" not in registry.list_failed()


# ---------------------------------------------------------------------------
# Disabled plugins are never imported (installed vs loaded split)
# ---------------------------------------------------------------------------

def test_discover_imports_nothing(mocker):
    ep = MagicMock()
    ep.name = "untouched"
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[ep],
    )

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()

    ep.load.assert_not_called()
    # The plugin is still visible as installed metadata.
    assert "untouched" in registry.list_discovered()


def test_prepare_loads_only_enabled_plugins(mocker):
    Enabled = type("Enabled", (MockPlugin,), {"_name": "enabled_one"})
    Disabled = type("Disabled", (MockPlugin,), {"_name": "disabled_two"})

    ep_on = MagicMock()
    ep_on.name = "enabled_one"
    ep_on.load.return_value = Enabled
    ep_off = MagicMock()
    ep_off.name = "disabled_two"
    ep_off.load.return_value = Disabled
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[ep_on, ep_off],
    )

    config = MagicMock(spec=TitanConfig)
    config.is_plugin_enabled.side_effect = lambda n: n == "enabled_one"
    config.get_enabled_plugins.return_value = ["enabled_one"]

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.prepare(config, MagicMock(spec=SecretBrokerFactory))

    ep_on.load.assert_called_once()
    ep_off.load.assert_not_called()
    # Loaded vs merely installed:
    assert registry.get_plugin("enabled_one") is not None
    assert registry.get_plugin("disabled_two") is None
    assert "disabled_two" in registry.list_discovered()
    # And the workflow-source pattern (get_plugin -> None -> skip) holds.
    assert "disabled_two" not in registry.list_installed()


def test_load_plugin_imports_a_disabled_plugin_on_demand(mocker):
    Disabled = type("Disabled", (MockPlugin,), {"_name": "disabled_demand"})
    ep = MagicMock()
    ep.name = "disabled_demand"
    ep.load.return_value = Disabled
    ep.dist.version = "9.9.9"
    mocker.patch(
        "titan_cli.core.plugins.plugin_registry.entry_points",
        return_value=[ep],
    )

    config = MagicMock(spec=TitanConfig)
    config.is_plugin_enabled.return_value = False
    config.get_enabled_plugins.return_value = []

    registry = PluginRegistry(discover_on_init=False)
    registry.discover()
    registry.prepare(config, MagicMock(spec=SecretBrokerFactory))
    ep.load.assert_not_called()

    # The management screen's path: load for display, without initializing.
    plugin = registry.load_plugin("disabled_demand")
    assert plugin is not None
    assert not plugin._initialized
    assert registry.get_plugin_version("disabled_demand") == "9.9.9"
