"""Mount-level tests for the plugin management screen."""

import asyncio
from unittest.mock import MagicMock

from textual.widgets import OptionList

from titan_cli.ui.tui.app import TitanApp
from titan_cli.ui.tui.screens.plugin_management import PluginManagementScreen


def _config(installed, failed=None):
    config = MagicMock()
    config.registry.list_installed.return_value = list(installed)
    config.registry.list_failed.return_value = dict(failed or {})
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


def _config_with_broken_plugin(pinned=True):
    """An enabled plugin that crashed while loading, optionally with a stable pin."""
    config = _config([], failed={"ragnarok": ModuleNotFoundError("No module named 'titan_cli.core.secrets'")})
    config.config.plugins = {"ragnarok": MagicMock(enabled=True)}
    if pinned:
        config.get_project_plugin_repo_url.return_value = "https://github.com/acme/ragnarok-workflows"
        config.get_project_plugin_resolved_commit.return_value = "c" * 40
        config.get_project_plugin_requested_ref.return_value = "0.10.0"
    return config


def _mount_and_inspect(config):
    """Mount the screen and capture the list labels plus the details pane state."""
    from textual.containers import Container
    from titan_cli.ui.tui.widgets import Button

    seen = {}

    async def run():
        app = TitanApp(config, initial_screen=lambda: PluginManagementScreen(config))
        async with app.run_test() as pilot:
            await pilot.pause()
            plugin_list = app.screen.query_one("#plugin-list", OptionList)
            seen["labels"] = [
                str(plugin_list.get_option_at_index(i).prompt)
                for i in range(plugin_list.option_count)
            ]
            details = app.screen.query_one("#details-content", Container)
            seen["details_text"] = " ".join(
                str(getattr(w, "renderable", "")) for w in details.query("*")
            )
            seen["button_ids"] = [b.id for b in details.query(Button)]
            seen["screen"] = app.screen

            # The update action must resolve the plugin even though it never loaded
            worker_calls = []
            app.screen.run_worker = lambda coro, **kw: (worker_calls.append(coro), coro.close())
            app.screen.action_update_plugin()
            seen["update_started"] = len(worker_calls) == 1

    asyncio.run(run())
    return seen


def test_a_plugin_that_failed_to_load_is_not_reported_as_not_installed():
    seen = _mount_and_inspect(_config_with_broken_plugin())

    assert any("Load failed" in label for label in seen["labels"])
    assert not any("Not installed" in label for label in seen["labels"])
    assert "titan_cli.core.secrets" in seen["details_text"]


def test_a_failed_pinned_plugin_can_still_be_updated():
    seen = _mount_and_inspect(_config_with_broken_plugin(pinned=True))

    assert "update-button" in seen["button_ids"]
    assert seen["update_started"]


def test_a_plugin_absent_from_the_environment_still_reads_not_installed():
    config = _config([])
    config.config.plugins = {"ragnarok": MagicMock(enabled=True)}

    seen = _mount_and_inspect(config)

    assert any("Not installed" in label for label in seen["labels"])
    assert "update-button" not in seen["button_ids"]
