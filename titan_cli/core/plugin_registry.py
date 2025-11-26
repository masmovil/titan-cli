# core/plugin_registry.py
from importlib.metadata import entry_points
from typing import Dict, List, Any
from .errors import PluginLoadError

class PluginRegistry:
    """Discovers installed plugins via entry points"""

    def __init__(self):
        self._plugins: Dict[str, Any] = {}
        self._discover()

    def _discover(self):
        """Discover all installed Titan plugins"""
        discovered = entry_points(group='titan.plugins')

        for ep in discovered:
            try:
                plugin_class = ep.load()
                self._plugins[ep.name] = plugin_class()
            except Exception as e:
                # Wrap the generic exception in our custom one and print a warning.
                # In a real app, this would be handled by a proper logger.
                error = PluginLoadError(plugin_name=ep.name, original_exception=e)
                print(f"Warning: {error}")


    def list_installed(self) -> List[str]:
        """List all installed plugins (via entry points)"""
        return list(self._plugins.keys())

    def get_plugin(self, name: str):
        """Get plugin instance by name"""
        return self._plugins.get(name)
