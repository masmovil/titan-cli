from unittest.mock import MagicMock

from titan_cli.ui.tui.screens.plugin_config_resolver import (
    plugin_has_config_ui,
    resolve_plugin_config_screen,
)
from titan_cli.ui.tui.screens.plugin_config_wizard import PluginConfigWizardScreen


class _PluginWithSchema:
    def has_custom_config_screen(self) -> bool:
        return False

    def get_config_schema(self) -> dict:
        return {"properties": {"token": {"type": "string"}}}


class _PluginWithCustomScreen:
    def has_custom_config_screen(self) -> bool:
        return True

    def create_config_screen(self, config):
        return "custom-screen"


def test_plugin_has_config_ui_for_schema_plugin() -> None:
    config = MagicMock()
    config.registry._plugins = {"sample": _PluginWithSchema()}

    assert plugin_has_config_ui(config, "sample") is True


def test_plugin_has_config_ui_for_custom_screen_plugin() -> None:
    config = MagicMock()
    config.registry._plugins = {"sample": _PluginWithCustomScreen()}

    assert plugin_has_config_ui(config, "sample") is True


def test_resolve_plugin_config_screen_prefers_custom_screen() -> None:
    config = MagicMock()
    config.registry._plugins = {"sample": _PluginWithCustomScreen()}

    assert resolve_plugin_config_screen(config, "sample") == "custom-screen"


def test_resolve_plugin_config_screen_falls_back_to_generic_wizard() -> None:
    config = MagicMock()
    config.registry._plugins = {"sample": _PluginWithSchema()}

    screen = resolve_plugin_config_screen(config, "sample")

    assert isinstance(screen, PluginConfigWizardScreen)
    assert screen.plugin_name == "sample"
