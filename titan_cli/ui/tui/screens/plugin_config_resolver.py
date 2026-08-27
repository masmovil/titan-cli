"""Helpers for resolving plugin configuration UI screens."""

from typing import Any

from .plugin_config_wizard import PluginConfigWizardScreen


def plugin_has_config_ui(config: Any, plugin_name: str) -> bool:
    """Return whether a plugin exposes any configuration UI."""
    plugin = config.registry._plugins.get(plugin_name)
    if not plugin:
        return False

    if hasattr(plugin, "has_custom_config_screen") and plugin.has_custom_config_screen():
        return True

    if hasattr(plugin, "get_config_schema"):
        try:
            schema = plugin.get_config_schema()
            return bool(schema and schema.get("properties"))
        except Exception:
            return False

    return False


def resolve_plugin_config_screen(config: Any, plugin_name: str) -> Any:
    """Return the appropriate configuration screen for a plugin."""
    plugin = config.registry._plugins.get(plugin_name)
    if plugin and hasattr(plugin, "has_custom_config_screen") and plugin.has_custom_config_screen():
        screen = plugin.create_config_screen(config)
        if screen is not None:
            return screen

    return PluginConfigWizardScreen(config, plugin_name)
