"""
Every blocking ask_* method must unblock when the app is no longer running.

The workflow runs on a NON-DAEMON executor thread (Textual thread worker →
asyncio's default ThreadPoolExecutor), and `concurrent.futures` joins those
threads at interpreter exit. So an ask_* wait loop with no app-exit escape
turns "quit while a prompt is open" into a hung console: the TUI is gone, the
prompt thread spins forever, and the atexit join never returns until a second
Ctrl+C kills it with a threading-shutdown traceback.

A KeyboardInterrupt handler inside the loop cannot prevent this - SIGINT is
only ever delivered to the main thread, never to the worker.

These tests run each prompt on a plain thread against an app that reports
`is_running = False`. A regression hangs that thread, which the join timeout
converts into a failure instead of a stuck test run.
"""

import threading

import pytest

from titan_cli.engine.option_item import OptionItem
from titan_cli.ui.tui.textual_components import TextualComponents
from titan_cli.ui.tui.widgets import ChoiceOption, SelectionOption


class _ExitingApp:
    """An app in the state right after the user quit: not running, loop gone."""

    is_running = False

    def call_from_thread(self, fn, *args, **kwargs):
        raise RuntimeError("App is closing")


def _call_on_thread(fn, timeout=5.0):
    """Run fn on a thread; fail (not hang) if it never returns."""
    box = {}

    def target():
        box["result"] = fn()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    assert not thread.is_alive(), (
        f"{fn.__name__} stayed blocked after the app stopped running - this is the "
        "hung-console-on-Ctrl+C bug"
    )
    return box["result"]


@pytest.fixture
def components():
    return TextualComponents(app=_ExitingApp(), output_widget=None)


def test_ask_option_returns_when_app_stops(components):
    result = _call_on_thread(
        lambda: components.ask_option("pick", [OptionItem(value=1, title="one")])
    )
    assert result is None


def test_ask_multiselect_returns_when_app_stops(components):
    result = _call_on_thread(
        lambda: components.ask_multiselect(
            "pick", [SelectionOption(value="a", label="A", selected=False)]
        )
    )
    assert result == []


def test_ask_text_returns_default_when_app_stops(components):
    result = _call_on_thread(lambda: components.ask_text("name?", default="dft"))
    assert result == "dft"


def test_ask_confirm_returns_default_when_app_stops(components):
    result = _call_on_thread(lambda: components.ask_confirm("sure?", default=True))
    assert result is True


def test_ask_choice_returns_none_when_app_stops(components):
    result = _call_on_thread(
        lambda: components.ask_choice("pick", [ChoiceOption(value="y", label="Yes")])
    )
    assert result is None
