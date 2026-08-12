"""
Tests for the Chip widget and the `ai_chip` step-facing helper.

Mounted for real rather than constructed: every bug this screen family has shipped (a
`compose_content` that never yielded, colliding widget ids) was invisible to unit-level
construction and obvious the moment something was actually mounted.
"""

import asyncio

from textual.app import App, ComposeResult

from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import Chip


class _ChipApp(App):
    def compose(self) -> ComposeResult:
        yield Chip(f"{Icons.AI} claude · CLI, automatic")
        yield Chip("AI is off for this task", variant="warning")


def _mount_chips():
    captured = {}

    async def run():
        app = _ChipApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            chips = list(app.query(Chip))
            captured["labels"] = [str(chip.renderable) for chip in chips]
            captured["classes"] = [set(chip.classes) for chip in chips]
            # Content-width: a chip that stretched to the full line would read as another
            # line of text, which is the thing it exists not to be.
            captured["widths"] = [chip.outer_size.width for chip in chips]
            captured["screen_width"] = app.screen.outer_size.width

    asyncio.run(run())
    return captured


def test_a_chip_renders_its_label_and_variant():
    captured = _mount_chips()

    assert captured["labels"][0] == f"{Icons.AI} claude · CLI, automatic"
    assert captured["classes"][0] == set()
    assert "warning" in captured["classes"][1]


def test_a_chip_is_only_as_wide_as_its_content():
    captured = _mount_chips()

    for width in captured["widths"]:
        assert 0 < width < captured["screen_width"]


def test_ai_chip_is_a_valid_announce_sink():
    """The façade calls announce(text) with one positional string and nothing else."""
    from inspect import signature

    from titan_cli.ui.tui.textual_components import TextualComponents

    params = list(signature(TextualComponents.ai_chip).parameters)

    assert params == ["self", "text"]
