"""
Tests for the F2 quick default-CLI picker.

Mounts the real app, presses the real keys. Synchronous wrappers around asyncio.run,
matching the repo's other screen-mount tests.
"""

import asyncio
from unittest.mock import MagicMock

from textual.screen import Screen
from textual.widgets import Static

from titan_cli.ai.router.availability import AIProviderAvailability
from titan_cli.ai.router.enums import AIProviderType
from titan_cli.core.models import AIConfig
from titan_cli.ui.tui.app import TitanApp
from titan_cli.ui.tui.screens.ai_routing import QuickCliModal
from titan_cli.ui.tui.widgets import StyledOptionList


class _BlankScreen(Screen):
    def compose(self):
        yield Static("blank")


def _config(default_cli=None):
    config = MagicMock()
    config.config.ai = AIConfig(default_cli=default_cli)
    config.get_project_name.return_value = "test-project"
    return config


def _stub_availability(monkeypatch, clis):
    class _Checker:
        def __init__(self, *args, **kwargs):
            pass

        def available_headless_clis(self):
            return [
                AIProviderAvailability(provider=AIProviderType.CLI_HEADLESS, identifier=name)
                for name in clis
            ]

        def available_interactive_clis(self):
            return [
                AIProviderAvailability(
                    provider=AIProviderType.CLI_INTERACTIVE, identifier=name
                )
                for name in clis
            ]

    monkeypatch.setattr("titan_cli.ai.router.availability.AIAvailabilityChecker", _Checker)
    monkeypatch.setattr(
        "titan_cli.core.security.create_broker_factory",
        lambda root: MagicMock(),
    )


class TestQuickCliModal:

    def _run(self, config, monkeypatch, keys, *, clis=("claude", "opencode")):
        _stub_availability(monkeypatch, clis)
        captured = {}

        async def run():
            app = TitanApp(config, initial_screen=lambda: _BlankScreen())
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("f2")
                await pilot.pause()
                captured["opened"] = isinstance(app.screen, QuickCliModal)
                if captured["opened"]:
                    captured["listed"] = list(app.screen.installed)
                    option_list = app.screen.query_one(StyledOptionList)
                    captured["highlighted"] = option_list.highlighted
                for key in keys:
                    await pilot.press(key)
                    await pilot.pause()
                captured["closed"] = not isinstance(app.screen, QuickCliModal)

        asyncio.run(run())
        return captured

    def test_f2_opens_the_picker_listing_installed_clis(self, monkeypatch):
        captured = self._run(_config(), monkeypatch, keys=["escape"])

        assert captured["opened"]
        assert captured["listed"] == ["claude", "opencode"]

    def test_the_saved_default_starts_highlighted(self, monkeypatch):
        captured = self._run(_config(default_cli="opencode"), monkeypatch, keys=["escape"])

        assert captured["highlighted"] == 1

    def test_selecting_a_cli_saves_it_and_closes(self, monkeypatch):
        config = _config(default_cli="claude")
        captured = self._run(config, monkeypatch, keys=["down", "enter"])

        assert captured["closed"]
        config.set_default_ai_cli.assert_called_once_with("opencode")

    def test_escape_closes_without_saving(self, monkeypatch):
        config = _config(default_cli="claude")
        captured = self._run(config, monkeypatch, keys=["escape"])

        assert captured["closed"]
        config.set_default_ai_cli.assert_not_called()

    def test_reselecting_the_current_default_saves_nothing(self, monkeypatch):
        config = _config(default_cli="claude")
        captured = self._run(config, monkeypatch, keys=["enter"])

        assert captured["closed"]
        config.set_default_ai_cli.assert_not_called()
