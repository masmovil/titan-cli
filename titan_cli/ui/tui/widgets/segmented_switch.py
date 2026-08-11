"""
Segmented Switch Widget

Reusable two-or-more option segmented switch for compact source selection.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


@dataclass(frozen=True)
class SegmentedSwitchOption:
    """Data model for a segmented switch option."""

    value: str
    label: str


class SegmentedSwitch(Widget):
    """
    Reusable segmented switch with keyboard and mouse interaction.

    Emits a ``Changed`` message when the selected option changes.
    """

    can_focus = True
    value: reactive[str] = reactive("")

    DEFAULT_CSS = """
    SegmentedSwitch {
        width: 22;
        height: 3;
        margin-top: 0;
    }

    SegmentedSwitch > Horizontal {
        width: 100%;
        min-width: 22;
        height: 3;
        background: $surface-lighten-1;
        border: round $primary;
        padding: 0;
        layout: horizontal;
        align: center middle;
    }

    SegmentedSwitch.-plain > Horizontal {
        background: transparent;
        border: none;
    }

    SegmentedSwitch.-plain {
        width: 22;
    }

    SegmentedSwitch .segment {
        width: 1fr;
        min-width: 7;
        height: 100%;
        padding: 0 1;
        content-align: center middle;
        text-align: center;
        color: $text-muted;
        background: $surface-lighten-1;
    }

    SegmentedSwitch .segment.-active {
        color: $text;
        background: $primary;
        text-style: bold;
    }

    SegmentedSwitch.-plain .segment {
        width: 1fr;
        min-width: 7;
        background: $panel-lighten-1;
        color: $text;
    }

    SegmentedSwitch.-plain .segment.-active {
        background: $primary;
    }

    SegmentedSwitch:focus > Horizontal {
        border: round $accent;
    }

    SegmentedSwitch:focus .segment.-active {
        background: $accent;
    }

    SegmentedSwitch.-plain:focus > Horizontal {
        border: none;
    }
    """

    class Changed(Message):
        """Message sent when the selected value changes."""

        def __init__(self, sender: Widget, value: str):
            super().__init__()
            self.sender = sender
            self.value = value

    def __init__(
        self,
        options: list[SegmentedSwitchOption],
        value: Optional[str] = None,
        on_change: Optional[Callable[[str], None]] = None,
        boxed: bool = True,
        autofocus: bool = True,
        emit_on_reselect: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize the segmented switch.

        Args:
            options: Ordered list of switch options.
            value: Initially selected option value. Defaults to the first option.
            on_change: Optional callback invoked after a user-driven change.
            autofocus: Whether to take focus on mount. Turn it off when the switch is one
                control among several - inside a tab, for instance, where taking focus would
                pull the user away from whatever tab they are actually looking at.
            emit_on_reselect: Also emit ``Changed`` when the user explicitly picks the
                segment that is already active (click, home/end). Turn it on when the
                initial value is only a suggestion that the user must confirm - otherwise
                confirming it would be a silent no-op.
        """
        super().__init__(**kwargs)
        if not options:
            raise ValueError("SegmentedSwitch requires at least one option")

        self.options = options
        self.on_change = on_change
        self._segment_values: dict[str, str] = {}
        self.boxed = boxed
        self.autofocus_on_mount = autofocus
        self.emit_on_reselect = emit_on_reselect

        option_values = {option.value for option in options}
        initial_value = value if value in option_values else options[0].value
        self.value = initial_value

        if not boxed:
            self.add_class("-plain")

    def compose(self) -> ComposeResult:
        """Compose the segmented switch UI."""
        with Horizontal():
            for index, option in enumerate(self.options):
                segment_id = f"segment-{index}"
                self._segment_values[segment_id] = option.value
                yield Static(
                    option.label,
                    classes="segment",
                    id=segment_id,
                )

    def on_mount(self) -> None:
        """Sync styles and, unless asked not to, take focus when mounted."""
        self._refresh_segments()
        if self.autofocus_on_mount:
            self.focus()

    def watch_value(self, _: str) -> None:
        """Refresh segment styles when the selected value changes."""
        if self.is_mounted:
            self._refresh_segments()

    def on_click(self, event) -> None:
        """Handle mouse selection of a segment."""
        segment_value = self._segment_values.get(getattr(event.widget, "id", ""))
        if segment_value is not None:
            self._set_value(segment_value, emit=True, explicit=True)
            event.stop()

    def on_key(self, event) -> None:
        """Handle keyboard navigation and selection."""
        if event.key in {"left", "up"}:
            self._move_selection(-1)
            event.stop()
        elif event.key in {"right", "down"}:
            self._move_selection(1)
            event.stop()
        elif event.key == "home":
            self._set_value(self.options[0].value, emit=True, explicit=True)
            event.stop()
        elif event.key == "end":
            self._set_value(self.options[-1].value, emit=True, explicit=True)
            event.stop()

    def set_value(self, value: str) -> None:
        """Update the switch value without emitting a change event."""
        self._set_value(value, emit=False)

    def _move_selection(self, step: int) -> None:
        """Move the active segment left or right."""
        current_index = self._get_index(self.value)
        next_index = max(0, min(len(self.options) - 1, current_index + step))
        self._set_value(self.options[next_index].value, emit=True)

    def _set_value(self, value: str, emit: bool, explicit: bool = False) -> None:
        """
        Update the selected value and optionally emit a change event.

        Re-selecting the current value normally stays silent; an explicit pick (click,
        home/end - not a clamped arrow move) emits anyway when ``emit_on_reselect`` is set,
        so that confirming a pre-selected suggestion still reaches the listener.
        """
        if value == self.value:
            if emit and explicit and self.emit_on_reselect:
                self._emit_changed()
            return

        self.value = value
        if emit:
            self._emit_changed()

    def _emit_changed(self) -> None:
        """Emit the changed message and invoke the callback."""
        if self.on_change:
            self.on_change(self.value)
        self.post_message(self.Changed(self, self.value))

    def _get_index(self, value: str) -> int:
        """Return the index for a given option value."""
        for index, option in enumerate(self.options):
            if option.value == value:
                return index
        return 0

    def _refresh_segments(self) -> None:
        """Sync active CSS classes with the current value."""
        for segment in self.query(".segment"):
            segment_value = self._segment_values.get(segment.id or "")
            segment.set_class(segment_value == self.value, "-active")
