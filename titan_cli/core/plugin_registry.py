# core/plugin_registry.py
from importlib.metadata import entry_points
from typing import Dict, List, Any, Optional
from .errors import PluginLoadError, PluginInitializationError, PluginError
from .plugin_base import TitanPlugin

class PluginRegistry:
    """Discovers and manages installed plugins."""

    def __init__(self, discover_on_init: bool = True):
        self._plugins: Dict[str, TitanPlugin] = {}
        self._failed_plugins: Dict[str, Exception] = {}
        if discover_on_init:
            self.discover()

    def discover(self):
        """Discover all installed Titan plugins."""
        discovered = entry_points(group='titan.plugins')
        for ep in discovered:
            try:
                plugin_class = ep.load()
                if not issubclass(plugin_class, TitanPlugin):
                    raise TypeError("Plugin class must inherit from TitanPlugin")
                self._plugins[ep.name] = plugin_class()
            except Exception as e:
                error = PluginLoadError(plugin_name=ep.name, original_exception=e)
                self._failed_plugins[ep.name] = error

    def initialize_plugins(self, config: Any, secrets: Any) -> None:
        """
        Initializes all discovered plugins in dependency order.
        
        Args:
            config: TitanConfig instance
            secrets: SecretManager instance
        """
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
                            del self._plugins[name]
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
                    plugin.initialize(config, secrets)
                    initialized.add(name)
                except Exception as e:
                    error = PluginInitializationError(plugin_name=name, original_exception=e)
                    self._failed_plugins[name] = error
                    del self._plugins[name] # Remove from active plugins

            plugins_to_initialize = next_pass_plugins
            if len(plugins_to_initialize) == remaining_plugins_count and remaining_plugins_count > 0:
                # Circular dependency or unresolvable dependency
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

    def list_installed(self) -> List[str]:
        """List successfully loaded plugins."""
        return list(self._plugins.keys())

    def list_failed(self) -> Dict[str, Exception]:
        """
        List plugins that failed to load or initialize.
        
        Returns:
            Dict mapping plugin name to error
        """
        return self._failed_plugins.copy()

    def get_plugin(self, name: str) -> Optional[TitanPlugin]:
        """Get plugin instance by name."""
        return self._plugins.get(name)
