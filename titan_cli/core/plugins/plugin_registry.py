# core/plugin_registry.py
import importlib
import sys
import threading
from importlib.metadata import entry_points
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from ..errors import PluginIncompatibleError, PluginLoadError, PluginInitializationError
from .plugin_base import TitanPlugin
from .community_sources import (
    PluginChannel,
    get_github_token,
    get_titan_incompatibility,
    parse_plugin_metadata,
)
from .trust import PluginTrust, TrustFinding, classify_plugin, scan_plugin_source
from .runtime import PluginRuntimeManager
from titan_cli.core.logging import get_logger

logger = get_logger(__name__)


def _load_local_plugin(
    repo_path: Path,
    plugin_name: str,
    extra_sys_paths: Optional[list[Path]] = None,
) -> TitanPlugin:
    """Load a Titan plugin directly from a local repository path."""
    _reject_reserved_plugin_name(plugin_name)
    pyproject_path = repo_path / "pyproject.toml"
    if not pyproject_path.is_file():
        raise FileNotFoundError(f"No pyproject.toml found in {repo_path}")

    metadata = parse_plugin_metadata(pyproject_path.read_text(encoding="utf-8"))
    if metadata.get("parse_error"):
        raise ValueError(f"Could not parse {pyproject_path}")

    from titan_cli import __version__ as titan_version
    incompatibility = get_titan_incompatibility(metadata, titan_version)
    if incompatibility:
        raise PluginIncompatibleError(plugin_name, incompatibility)

    entry_point = (metadata.get("titan_entry_points") or {}).get(plugin_name)
    if not entry_point:
        raise ValueError(
            f"Local repository {repo_path} does not expose titan plugin '{plugin_name}'"
        )

    module_name, sep, class_name = entry_point.partition(":")
    if not module_name or not sep or not class_name:
        raise ValueError(f"Invalid entry point for '{plugin_name}': {entry_point}")

    package_root = module_name.split(".", 1)[0]
    sys_paths = [str(path) for path in (extra_sys_paths or [])] + [str(repo_path)]
    for sys_path_entry in reversed(sys_paths):
        if sys_path_entry in sys.path:
            sys.path.remove(sys_path_entry)
        sys.path.insert(0, sys_path_entry)

    stale_modules = [
        name for name in list(sys.modules)
        if name == package_root or name.startswith(f"{package_root}.")
    ]
    for name in stale_modules:
        sys.modules.pop(name, None)

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        # A missing titan_cli.* module is a version mismatch, not a broken plugin:
        # the plugin was built against an API this titan-cli no longer (or not yet) has.
        if e.name == "titan_cli" or (e.name or "").startswith("titan_cli."):
            from titan_cli import __version__ as titan_version
            from titan_cli.messages import msg
            raise PluginIncompatibleError(
                plugin_name,
                msg.Errors.PLUGIN_API_MISSING.format(current=titan_version, error=e),
            ) from e
        raise
    plugin_class = getattr(module, class_name)
    if not issubclass(plugin_class, TitanPlugin):
        raise TypeError("Plugin class must inherit from TitanPlugin")
    plugin = plugin_class()
    plugin._dev_local_package_root = package_root
    return plugin


def _load_dev_local_plugin(repo_path: Path, plugin_name: str) -> TitanPlugin:
    """Load a Titan plugin from a local development repository."""
    return _load_local_plugin(repo_path, plugin_name)


# `derive_namespace` maps these names onto Titan's own scopes (`titan.core`,
# `titan.project`, `titan.user`) — the namespace where app-level credentials
# such as AI keys live. A plugin registering under one of them would receive
# a broker over that scope, so the names are rejected at registration; the
# namespace derivation itself must keep accepting "core" (the engine builder
# legitimately uses `for_plugin("core")` for app-level consumers).
_RESERVED_PLUGIN_NAMES = frozenset({"core", "project", "user"})


def _reject_reserved_plugin_name(plugin_name: str) -> None:
    if plugin_name in _RESERVED_PLUGIN_NAMES:
        raise ValueError(
            f"'{plugin_name}' is a reserved name and cannot be used by a plugin: "
            "it maps onto Titan's own secret namespace."
        )


class PluginRegistry:
    """Discovers and manages installed plugins."""

    def __init__(self, discover_on_init: bool = True):
        self._plugins: Dict[str, TitanPlugin] = {}
        self._failed_plugins: Dict[str, Exception] = {}
        self._entry_points: Dict[str, Any] = {}
        self._discovered_plugin_names: List[str] = []
        self._plugin_versions: Dict[str, str] = {}
        self._plugin_trust: Dict[str, PluginTrust] = {}
        self._security_findings: Dict[str, list[TrustFinding]] = {}
        self._plugin_sync_events: list[str] = []
        self._dev_local_sys_paths: set[str] = set()
        self._dev_local_package_roots: set[str] = set()
        self._runtime_manager = PluginRuntimeManager()
        # Lazy initialization state. Plugins initialize on first use, not when
        # the registry is built: initialize() does real I/O (subprocesses,
        # keyring reads), and most registry consumers only need the instance.
        self._initialized: Set[str] = set()
        self._init_lock = threading.RLock()
        self._config: Any = None
        self._broker_factory: Any = None
        # Import failures already reported with a full traceback this session.
        # Deliberately NOT cleared by reset(): a broken import cannot fix
        # itself mid-session, so repeat rebuilds log one line, not a traceback.
        self._reported_load_failures: Set[str] = set()
        if discover_on_init:
            self.discover()

    def discover(self):
        """
        Enumerate installed Titan plugins from entry-point metadata.

        Deliberately imports nothing: enumeration costs milliseconds, imports
        cost hundreds (slack_sdk alone is ~200ms cold), and a project usually
        enables only a subset of what is installed. Loading (import +
        instantiate + compatibility check) happens per plugin in _load() —
        for enabled plugins at prepare(), for the rest only when something
        explicitly asks (the plugin management screen).
        """
        discovered = entry_points(group='titan.plugins')

        # Deduplicate entry points (can happen in dev mode with editable installs)
        self._entry_points = {}
        for ep in discovered:
            if ep.name not in self._entry_points:
                self._entry_points[ep.name] = ep

        self._discovered_plugin_names = list(self._entry_points.keys())
        logger.info("plugins_discovered", count=len(self._discovered_plugin_names), plugins=self._discovered_plugin_names)

        for name, ep in self._entry_points.items():
            self._plugin_trust[name] = classify_plugin(
                name,
                channel=None,
                dist_name=ep.dist.name if ep.dist else None,
            )

    def load_plugin(self, name: str) -> Optional[TitanPlugin]:
        """
        Import and instantiate a discovered plugin now, regardless of whether
        it is enabled, and return it — or None when it is unknown or failed.

        Does NOT initialize. For consumers that need the instance of a plugin
        the project has disabled — the management screen showing a disabled
        plugin's version, description or config schema — where a user-invoked
        import is the right trade.
        """
        with self._init_lock:
            return self._load(name)

    def load_all(self) -> None:
        """Import and instantiate every discovered plugin (management screen)."""
        for name in list(self._entry_points.keys()):
            self.load_plugin(name)

    def _load(self, name: str) -> Optional[TitanPlugin]:
        if name in self._plugins:
            return self._plugins[name]
        if name in self._failed_plugins:
            return None
        ep = self._entry_points.get(name)
        if ep is None:
            return None

        from titan_cli import __version__ as titan_version

        try:
            logger.debug("plugin_loading", name=name)
            _reject_reserved_plugin_name(name)
            plugin_class = ep.load()
            if not issubclass(plugin_class, TitanPlugin):
                raise TypeError("Plugin class must inherit from TitanPlugin")
            plugin = plugin_class()

            # A plugin built against a different titan-cli API must not
            # load: record it as failed with a message naming both
            # versions instead of breaking at first use.
            incompatibility = get_titan_incompatibility(
                {"titan_requirement": plugin.titan_requires}, titan_version
            )
            if incompatibility:
                error = PluginIncompatibleError(name, incompatibility)
                logger.warning(
                    "plugin_incompatible", name=name, reason=incompatibility
                )
                self._failed_plugins[name] = error
                return None

            self._plugins[name] = plugin
            # The plugin's own declared version wins; the owning
            # distribution's version is only a fallback (for a plugin
            # bundled inside another wheel, the distribution's version is
            # the bundler's, not the plugin's — and in dev installs with
            # duplicate entry points it depends on import ordering).
            self._plugin_versions[name] = (
                plugin.version
                or (ep.dist.version if ep.dist else None)
                or "unknown"
            )
            logger.debug("plugin_loaded", name=name)
            return plugin
        except Exception as e:
            if name in self._reported_load_failures:
                logger.warning("plugin_load_failed", name=name, error=str(e))
            else:
                logger.exception("plugin_load_failed", name=name)
                self._reported_load_failures.add(name)
            self._failed_plugins[name] = PluginLoadError(
                plugin_name=name, original_exception=e
            )
            return None

    def prepare(self, config: Any, broker_factory: Any) -> None:
        """
        Make the registry ready to initialize plugins on first use.

        Applies per-project source overrides and stores the config and broker
        factory that ensure_initialized() will hand to each plugin. Does NOT
        initialize anything: initialize() does real I/O (subprocesses, keyring
        reads through dbus), so it runs lazily, when a plugin is first used.

        Args:
            config: TitanConfig instance
            broker_factory: SecretBrokerFactory; each plugin receives a broker
                already scoped to its own namespace, never the factory itself.
        """
        with self._init_lock:
            self._config = config
            self._broker_factory = broker_factory
            # A new preparation invalidates previous initialization state:
            # plugin config may have changed, and a recorded init failure may
            # be curable now (e.g. a credential stored since the last attempt).
            self._initialized.clear()
            self._failed_plugins = {
                name: error
                for name, error in self._failed_plugins.items()
                if not isinstance(error, PluginInitializationError)
            }
        self._apply_source_overrides(config)

        # Load (import + instantiate + compatibility check) what this project
        # actually enables; disabled plugins stay as unloaded entry-point
        # metadata and cost nothing.
        with self._init_lock:
            for name in list(self._entry_points.keys()):
                if config.is_plugin_enabled(name):
                    self._load(name)

    def ensure_initialized(self, name: str) -> Optional[TitanPlugin]:
        """
        Initialize a plugin on first use and return it, or None.

        Returns the plugin instance when it is loaded, enabled and initialized
        (initializing it now if needed, dependencies first). Returns None when
        the plugin is unknown, disabled, the registry is not prepared yet, or
        initialization failed — failures are recorded in list_failed() and are
        sticky until the next prepare()/reset() (force_plugin_init=True on
        config.load() is the escape hatch that clears them).

        Thread-safe: workflow threads and the UI thread may race to first use.
        """
        with self._init_lock:
            return self._ensure_initialized_locked(name, in_progress=set())

    def ensure_all_initialized(self) -> None:
        """
        Initialize every discovered, enabled plugin now.

        For consumers that need the full picture at once — the plugin
        management screen showing real per-plugin state — rather than the
        lazy default.
        """
        for name in list(self._entry_points.keys()):
            self.ensure_initialized(name)
        # Plugins that entered via source overrides rather than entry points
        # (dev_local / stable channel) initialize too.
        for name in list(self._plugins.keys()):
            self.ensure_initialized(name)

    def is_initialized(self, name: str) -> bool:
        """Whether a plugin has been initialized in the current build."""
        return name in self._initialized

    def _ensure_initialized_locked(self, name: str, in_progress: Set[str]) -> Optional[TitanPlugin]:
        if name in self._initialized:
            return self._plugins.get(name)
        if name in self._failed_plugins:
            return None

        config = self._config
        broker_factory = self._broker_factory
        if config is None or broker_factory is None:
            # Not prepared yet (setup wizard phase): nothing can initialize.
            logger.debug("plugin_registry_not_prepared", name=name)
            return None

        if not config.is_plugin_enabled(name):
            logger.debug("plugin_disabled", name=name)
            return None

        plugin = self._load(name)
        if plugin is None:
            return None

        if name in in_progress:
            logger.error("circular_dependency_detected", plugins=sorted(in_progress))
            self._failed_plugins[name] = PluginInitializationError(
                plugin_name=name,
                original_exception="Circular or unresolvable dependency detected.",
            )
            return None
        in_progress.add(name)

        for dep_name in plugin.dependencies:
            if self._ensure_initialized_locked(dep_name, in_progress) is None:
                logger.error("plugin_dependency_failed", name=name, dependency=dep_name)
                self._failed_plugins[name] = PluginInitializationError(
                    plugin_name=name,
                    original_exception=f"Dependency '{dep_name}' failed to load/initialize.",
                )
                return None

        try:
            logger.info("plugin_initializing", name=name)
            plugin.initialize(config, broker_factory.for_plugin(name))
            self._initialized.add(name)
            logger.info("plugin_initialized", name=name)
            return plugin
        except Exception as e:
            logger.exception("plugin_init_failed", name=name)
            self._failed_plugins[name] = PluginInitializationError(
                plugin_name=name, original_exception=e
            )
            return None

    def _apply_source_overrides(self, config: Any) -> None:
        """Apply effective per-project plugin sources before initialization."""
        config_model = getattr(config, "config", None)
        plugins = getattr(config_model, "plugins", None)
        if not config or not plugins:
            return

        for plugin_name in config.get_enabled_plugins():
            channel = config.get_plugin_source_channel(plugin_name)

            if channel == PluginChannel.DEV_LOCAL:
                repo_path = config.get_plugin_source_path(plugin_name)
                if not repo_path:
                    error = PluginLoadError(
                        plugin_name=plugin_name,
                        original_exception=ValueError("dev_local source requires a local path"),
                    )
                    self._failed_plugins[plugin_name] = error
                    self._plugins.pop(plugin_name, None)
                    continue

                try:
                    plugin = _load_dev_local_plugin(repo_path, plugin_name)
                    self._plugins[plugin_name] = plugin
                    self._dev_local_sys_paths.add(str(repo_path))
                    package_root = getattr(plugin, "_dev_local_package_root", None)
                    if package_root:
                        self._dev_local_package_roots.add(package_root)
                    self._plugin_versions[plugin_name] = PluginChannel.DEV_LOCAL
                    self._record_trust_scan(plugin_name, PluginChannel.DEV_LOCAL, Path(repo_path))
                    if plugin_name not in self._discovered_plugin_names:
                        self._discovered_plugin_names.append(plugin_name)
                    logger.info(
                        "plugin_dev_local_override_applied",
                        name=plugin_name,
                        path=str(repo_path),
                    )
                except Exception as e:
                    logger.exception(
                        "plugin_dev_local_override_failed",
                        name=plugin_name,
                        path=str(repo_path),
                    )
                    error = PluginLoadError(plugin_name=plugin_name, original_exception=e)
                    self._failed_plugins[plugin_name] = error
                    self._plugins.pop(plugin_name, None)
                continue

            repo_url = config.get_project_plugin_repo_url(plugin_name)
            resolved_commit = config.get_project_plugin_resolved_commit(plugin_name)
            if not repo_url or not resolved_commit:
                continue

            try:
                runtime = self._runtime_manager.ensure_stable_runtime(
                    plugin_name=plugin_name,
                    repo_url=repo_url,
                    resolved_commit=resolved_commit,
                    token=get_github_token(),
                )
                plugin = _load_local_plugin(
                    runtime.paths.source_dir,
                    plugin_name,
                    extra_sys_paths=[runtime.paths.site_packages],
                )
                self._plugins[plugin_name] = plugin
                self._dev_local_sys_paths.add(str(runtime.paths.site_packages))
                self._dev_local_sys_paths.add(str(runtime.paths.source_dir))
                package_root = getattr(plugin, "_dev_local_package_root", None)
                if package_root:
                    self._dev_local_package_roots.add(package_root)
                self._plugin_versions[plugin_name] = f"stable@{resolved_commit[:12]}"
                self._record_trust_scan(
                    plugin_name, PluginChannel.STABLE, Path(runtime.paths.source_dir)
                )
                if runtime.created:
                    requested_ref = config.get_project_plugin_requested_ref(plugin_name) or resolved_commit[:12]
                    self._plugin_sync_events.append(
                        f"Syncing plugin '{plugin_name}' to project version {requested_ref}."
                    )
                if plugin_name not in self._discovered_plugin_names:
                    self._discovered_plugin_names.append(plugin_name)
                logger.info(
                    "plugin_stable_runtime_applied",
                    name=plugin_name,
                    repo_url=repo_url,
                    resolved_commit=resolved_commit,
                )
            except Exception as e:
                logger.exception(
                    "plugin_stable_runtime_failed",
                    name=plugin_name,
                    repo_url=repo_url,
                    resolved_commit=resolved_commit,
                )
                error = PluginLoadError(plugin_name=plugin_name, original_exception=e)
                self._failed_plugins[plugin_name] = error
                self._plugins.pop(plugin_name, None)

    def list_installed(self) -> List[str]:
        """List successfully loaded plugins."""
        return list(self._plugins.keys())

    def list_discovered(self) -> List[str]:
        """List all discovered plugins by name, regardless of load status."""
        return self._discovered_plugin_names

    def list_enabled(self, config: Any) -> List[str]:
        """
        List plugins that are enabled in the current project configuration.

        Args:
            config: TitanConfig instance

        Returns:
            List of enabled plugin names
        """
        if not config:
            return []
        if hasattr(config, "get_enabled_plugins"):
            return config.get_enabled_plugins()
        return []

    def list_failed(self) -> Dict[str, Exception]:
        """
        List plugins that failed to load or initialize.

        Returns:
            Dict mapping plugin name to error
        """
        return self._failed_plugins.copy()

    def list_sync_events(self) -> list[str]:
        """List plugin runtime sync events from the latest load cycle."""
        return list(self._plugin_sync_events)

    def get_plugin(self, name: str) -> Optional[TitanPlugin]:
        """Get plugin instance by name."""
        return self._plugins.get(name)

    def get_plugin_version(self, name: str) -> str:
        """Get the installed package version for a plugin, from distribution metadata."""
        return self._plugin_versions.get(name, "unknown")

    def get_plugin_trust(self, name: str) -> Optional[PluginTrust]:
        """Trust classification for a loaded plugin (None if unknown)."""
        return self._plugin_trust.get(name)

    def get_security_findings(self, name: str) -> list[TrustFinding]:
        """Secret-access constructs found by the static scan for a plugin."""
        return list(self._security_findings.get(name, []))

    def _record_trust_scan(
        self, plugin_name: str, channel: PluginChannel, source_dir: Path
    ) -> None:
        """
        Classify a source-overridden plugin and statically scan its tree.

        The scan warns, never blocks: a finding means the plugin's source
        plainly touches secret machinery (`keyring`, the private vault,
        `SecretManager`), which the user should know about — but whether to
        keep running it is their call.
        """
        self._plugin_trust[plugin_name] = classify_plugin(plugin_name, channel)
        try:
            findings = scan_plugin_source(source_dir)
        except OSError as e:
            logger.warning(
                "plugin_security_scan_failed", name=plugin_name, error=str(e)
            )
            return
        self._security_findings[plugin_name] = findings
        if findings:
            logger.warning(
                "plugin_security_scan_findings",
                name=plugin_name,
                trust=str(self._plugin_trust[plugin_name]),
                count=len(findings),
                findings=[f"{f.file}:{f.line} {f.code}" for f in findings[:10]],
            )

    def reset(self):
        """Resets the registry, clearing all loaded plugins and re-discovering."""
        for repo_path in list(self._dev_local_sys_paths):
            while repo_path in sys.path:
                sys.path.remove(repo_path)
        self._dev_local_sys_paths.clear()

        for package_root in list(self._dev_local_package_roots):
            stale_modules = [
                name for name in list(sys.modules)
                if name == package_root or name.startswith(f"{package_root}.")
            ]
            for name in stale_modules:
                sys.modules.pop(name, None)
        self._dev_local_package_roots.clear()

        importlib.invalidate_caches()

        self._plugins.clear()
        self._failed_plugins.clear()
        self._plugin_versions.clear()
        self._plugin_trust.clear()
        self._security_findings.clear()
        self._plugin_sync_events.clear()
        with self._init_lock:
            self._initialized.clear()
        self.discover()
