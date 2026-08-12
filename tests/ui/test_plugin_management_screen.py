"""Mount-level tests for the plugin management screen."""

import asyncio
from unittest.mock import MagicMock

from textual.widgets import OptionList

from titan_cli.ui.tui.app import TitanApp
from titan_cli.ui.tui.screens.plugin_management import PluginManagementScreen


def _config(installed):
    config = MagicMock()
    config.registry.list_installed.return_value = list(installed)
    config.is_plugin_enabled.return_value = True
    config.config.plugins = {}
    config.get_project_name.return_value = "test-project"
    config.get_project_plugin_repo_url.return_value = None
    config.get_project_plugin_resolved_commit.return_value = None
    config.get_project_plugin_requested_ref.return_value = None
    config.get_plugin_source_path.return_value = None
    return config


def _mount_and_count_lists(config):
    counted = {}

    async def run():
        app = TitanApp(config, initial_screen=lambda: PluginManagementScreen(config))
        async with app.run_test() as pilot:
            await pilot.pause()
            lists = list(app.screen.query(OptionList))
            counted["lists"] = len(lists)
            counted["options"] = [
                lists[0].get_option_at_index(i).id for i in range(lists[0].option_count)
            ]

    asyncio.run(run())
    return counted


def test_the_plugin_list_is_not_duplicated_on_mount():
    """
    The screen loads its list on both on_mount and on_screen_resume, which fire in quick
    succession. Rebuilding the widget instead of refilling it left both copies on screen,
    because Textual completes `remove()` a frame after `mount()` has already landed.
    """
    result = _mount_and_count_lists(_config(["git", "github"]))

    assert result["lists"] == 1
    assert result["options"] == ["git", "github"]


def test_an_empty_plugin_list_is_also_not_duplicated():
    result = _mount_and_count_lists(_config([]))

    assert result["lists"] == 1
    assert result["options"] == ["none"]
