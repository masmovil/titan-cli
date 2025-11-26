# core/plugin_registry.py
from importlib.metadata import entry_points
from typing import Dict, List, Any

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
                # Log warning but don't fail
                # In a real app, you'd use a proper logger here
                print(f"Warning: Failed to load plugin '{ep.name}': {e}")

    def list_installed(self) -> List[str]:
        """List all installed plugins (via entry points)"""
        return list(self._plugins.keys())

    def get_plugin(self, name: str):
        """Get plugin instance by name"""
        return self._plugins.get(name)
