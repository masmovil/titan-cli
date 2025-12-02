# core/plugin_registry.py
from importlib.metadata import entry_points
from typing import Dict, List, Any
from .errors import PluginLoadError, PluginError
from .plugin_base import TitanPlugin

class PluginRegistry:
    """Discovers and manages installed plugins."""

    def __init__(self):
        self._plugins: Dict[str, TitanPlugin] = {}
        self._discover()

    def _discover(self):
        """Discover all installed Titan plugins."""
        discovered = entry_points(group='titan.plugins')
        for ep in discovered:
            try:
                plugin_class = ep.load()
                # Ensure it's a TitanPlugin before instantiating
                if not issubclass(plugin_class, TitanPlugin):
                    raise PluginLoadError(
                        ep.name, 
                        TypeError("Plugin class must inherit from TitanPlugin")
                    )
                self._plugins[ep.name] = plugin_class()
            except Exception as e:
                error = PluginLoadError(plugin_name=ep.name, original_exception=e)
                print(f"Warning: {error}")

    def initialize_plugins(self, config, secrets):
        """
        Initializes all discovered plugins in dependency order.
        This should be called after the registry is instantiated.
        """
        # Simple topological sort
        initialized = set()
        
        # Use a copy of keys to allow modification during iteration if needed
        plugin_names = list(self._plugins.keys())

        for name in plugin_names:
            self._initialize_plugin_with_deps(name, config, secrets, initialized)

    def _initialize_plugin_with_deps(self, name: str, config, secrets, initialized: set):
        """Recursively initialize a plugin and its dependencies."""
        if name in initialized:
            return

        plugin = self._plugins.get(name)
        if not plugin:
            # This case should ideally not be hit if called from initialize_plugins
            raise PluginError(f"Plugin '{name}' not found in registry.")

        # Initialize dependencies first
        for dep_name in plugin.dependencies:
            if dep_name not in self._plugins:
                raise PluginError(f"Plugin '{name}' has an unresolved dependency: '{dep_name}'")
            self._initialize_plugin_with_deps(dep_name, config, secrets, initialized)

        # Initialize the plugin itself
        plugin.initialize(config, secrets)
        initialized.add(name)

    def list_installed(self) -> List[str]:
        """List all installed plugins (via entry points)"""
        return list(self._plugins.keys())

    def get_plugin(self, name: str) -> TitanPlugin:
        """Get plugin instance by name"""
        return self._plugins.get(name)
