# core/plugin_registry.py
import importlib
import sys
from importlib.metadata import entry_points
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..errors import PluginLoadError, PluginInitializationError
from .plugin_base import TitanPlugin
from .community_sources import PluginChannel, get_github_token, parse_plugin_metadata
from .runtime import PluginRuntimeManager
from titan_cli.core.logging import get_logger

logger = get_logger(__name__)


def _load_local_plugin(
    repo_path: Path,
    plugin_name: str,
    extra_sys_paths: Optional[list[Path]] = None,
) -> TitanPlugin:
    """Load a Titan plugin directly from a local repository path."""
    pyproject_path = repo_path / "pyproject.toml"
    if not pyproject_path.is_file():
        raise FileNotFoundError(f"No pyproject.toml found in {repo_path}")

    metadata = parse_plugin_metadata(pyproject_path.read_text(encoding="utf-8"))
    if metadata.get("parse_error"):
        raise ValueError(f"Could not parse {pyproject_path}")

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

    module = importlib.import_module(module_name)
    plugin_class = getattr(module, class_name)
    if not issubclass(plugin_class, TitanPlugin):
        raise TypeError("Plugin class must inherit from TitanPlugin")
    plugin = plugin_class()
    plugin._dev_local_package_root = package_root
    return plugin


def _load_dev_local_plugin(repo_path: Path, plugin_name: str) -> TitanPlugin:
    """Load a Titan plugin from a local development repository."""
    return _load_local_plugin(repo_path, plugin_name)


class PluginRegistry:
    """Discovers and manages installed plugins."""

    def __init__(self, discover_on_init: bool = True):
        self._plugins: Dict[str, TitanPlugin] = {}
        self._failed_plugins: Dict[str, Exception] = {}
        self._discovered_plugin_names: List[str] = []
        self._plugin_versions: Dict[str, str] = {}
        self._plugin_sync_events: list[str] = []
        self._dev_local_sys_paths: set[str] = set()
        self._dev_local_package_roots: set[str] = set()
        self._runtime_manager = PluginRuntimeManager()
        if discover_on_init:
            self.discover()

    def discover(self):
        """Discover all installed Titan plugins."""
        discovered = entry_points(group='titan.plugins')

        # Deduplicate entry points (can happen in dev mode with editable installs)
        seen = {}
        unique_eps = []
        for ep in discovered:
            if ep.name not in seen:
                seen[ep.name] = ep
                unique_eps.append(ep)

        self._discovered_plugin_names = [ep.name for ep in unique_eps]
        logger.info("plugins_discovered", count=len(self._discovered_plugin_names), plugins=self._discovered_plugin_names)

        for ep in unique_eps:
            try:
                logger.debug("plugin_loading", name=ep.name)
                plugin_class = ep.load()
                if not issubclass(plugin_class, TitanPlugin):
                    raise TypeError("Plugin class must inherit from TitanPlugin")
                self._plugins[ep.name] = plugin_class()
                self._plugin_versions[ep.name] = ep.dist.version if ep.dist else "unknown"
                logger.debug("plugin_loaded", name=ep.name)
            except Exception as e:
                logger.exception("plugin_load_failed", name=ep.name)
                error = PluginLoadError(plugin_name=ep.name, original_exception=e)
                self._failed_plugins[ep.name] = error

        logger.info("plugin_discovery_completed", loaded=len(self._plugins), failed=len(self._failed_plugins), failed_plugins=list(self._failed_plugins.keys()))

    def initialize_plugins(self, config: Any, broker_factory: Any) -> None:
        """
        Initializes all discovered plugins in dependency order.

        Args:
            config: TitanConfig instance
            broker_factory: SecretBrokerFactory; each plugin receives a broker
                already scoped to its own namespace, never the factory itself.
        """
        self._apply_source_overrides(config)

        # Create a copy of plugin names to iterate over, as _plugins might change
        plugins_to_initialize = list(self._plugins.keys())
        initialized = set()

        # Simple dependency resolution loop
        while plugins_to_initialize:
            remaining_plugins_count = len(plugins_to_initialize)
            next_pass_plugins = []

            for name in plugins_to_initialize:
                if name in initialized:
                    continue

                # Skip plugins that are disabled in configuration
                if not config.is_plugin_enabled(name):
                    logger.info("plugin_disabled", name=name)
                    initialized.add(name)  # Mark as processed so we don't retry
                    continue

                plugin = self._plugins[name]
                dependencies_met = True

                # Check if all dependencies are initialized or failed
                for dep_name in plugin.dependencies:
                    if dep_name not in initialized:
                        # If a dependency failed to load/initialize, this plugin also implicitly fails
                        if dep_name in self._failed_plugins:
                            # Mark this plugin as failed due to dependency
                            error = PluginInitializationError(
                                plugin_name=name,
                                original_exception=f"Dependency '{dep_name}' failed to load/initialize."
                            )
                            self._failed_plugins[name] = error
                            logger.error("plugin_dependency_failed", name=name, dependency=dep_name)
                            # Don't delete from _plugins - keep it available for configuration
                            dependencies_met = False
                            break
                        else:
                            dependencies_met = False
                            break

                if not dependencies_met:
                    if name not in self._failed_plugins: # If not already marked failed by dependency
                        next_pass_plugins.append(name)
                    continue

                # Initialize the plugin if dependencies are met
                try:
                    logger.info("plugin_initializing", name=name)
                    plugin.initialize(config, broker_factory.for_plugin(name))
                    initialized.add(name)
                    logger.info("plugin_initialized", name=name)
                except Exception as e:
                    logger.exception("plugin_init_failed", name=name)
                    error = PluginInitializationError(plugin_name=name, original_exception=e)
                    self._failed_plugins[name] = error
                    # Don't delete from _plugins - keep it available for configuration

            plugins_to_initialize = next_pass_plugins
            if len(plugins_to_initialize) == remaining_plugins_count and remaining_plugins_count > 0:
                # Circular dependency or unresolvable dependency
                logger.error("circular_dependency_detected", plugins=plugins_to_initialize)
                for name in plugins_to_initialize:
                    if name not in self._failed_plugins: # Only mark if not already failed by dependency
                        error = PluginInitializationError(
                            plugin_name=name,
                            original_exception="Circular or unresolvable dependency detected."
                        )
                        self._failed_plugins[name] = error
                        if name in self._plugins: # Only delete if it wasn't deleted by a dep error
                            del self._plugins[name]
                break # Exit the loop if no progress is made

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
        self._plugin_sync_events.clear()
        self.discover()
