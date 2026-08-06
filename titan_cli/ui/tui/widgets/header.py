"""
Header Widget

Custom header widget with title, back button, and favorite button.
"""
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.message import Message

from titan_cli.ui.tui.icons import Icons


class HeaderWidget(Widget):
    """
    Header widget that displays screen title, back button, and favorite button.

    Shows:
    - Left: Back button (← Back)
    - Center: Screen title
    - Right: Favorite button (☆ Favorite / ⭐ Favorited), optional
    """

    # Reactive property for title
    title: reactive[str] = reactive("Titan CLI")

    # Reactive property for favorite state
    is_favorite: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    HeaderWidget {
        background: $surface-lighten-1;
        height: 3;
        width: 100%;
        dock: top;
    }

    HeaderWidget Horizontal {
        width: 100%;
        height: 100%;
        align: center middle;
    }

    HeaderWidget #header-back {
        width: auto;
        min-width: 15;
        height: 100%;
        background: transparent;
        color: $primary;
        text-align: left;
        padding: 0 2;
        content-align: left middle;
    }

    HeaderWidget #header-back:hover {
        background: $surface-lighten-2;
        text-style: bold;
    }

    HeaderWidget #header-favorite {
        width: auto;
        min-width: 15;
        height: 100%;
        background: transparent;
        color: $primary;
        text-align: right;
        padding: 0 2;
        content-align: right middle;
    }

    HeaderWidget #header-favorite:hover {
        background: $surface-lighten-2;
        text-style: bold;
    }

    HeaderWidget #header-title {
        width: 1fr;
        height: 100%;
        content-align: center middle;
        text-align: center;
        color: $primary;
        text-style: bold;
    }

    HeaderWidget .header-left,
    HeaderWidget .header-right {
        width: auto;
        min-width: 15;
        height: 100%;
    }
    """

    def __init__(
        self,
        title: str = "Titan CLI",
        show_back: bool = True,
        show_favorite: bool = False,
        is_favorite: bool = False,
        **kwargs,
    ):
        """
        Initialize header widget.

        Args:
            title: Title to display in header
            show_back: Whether to show back button
            show_favorite: Whether to show favorite button
            is_favorite: Initial favorite state
        """
        super().__init__(**kwargs)
        self.title = title
        self.show_back = show_back
        self.show_favorite = show_favorite
        self.is_favorite = is_favorite

    def compose(self) -> ComposeResult:
        """Compose the header with back button, title, and favorite button."""
        with Horizontal():
            if self.show_back:
                yield Static(f"{Icons.BACK} Back", id="header-back", classes="header-left")
            else:
                yield Static("", classes="header-left")

            yield Static(self.title, id="header-title")

            if self.show_favorite:
                yield Static(self._favorite_label(), id="header-favorite", classes="header-right")
            else:
                yield Static("", classes="header-right")

    def _favorite_label(self) -> str:
        """Return the label for the favorite button based on current state."""
        if self.is_favorite:
            return f"{Icons.STAR} Favorited"
        return f"{Icons.STAR_OUTLINE} Favorite"

    def on_click(self, event) -> None:
        """Handle click on header elements."""
        if event.widget.id == "header-back":
            # Post a message to the screen to go back
            self.post_message(self.BackPressed())
        elif event.widget.id == "header-favorite":
            # Post a message to the screen to toggle favorite status
            self.post_message(self.FavoritePressed())

    def watch_title(self, new_value: str) -> None:
        """Update title display when title changes."""
        if self.is_mounted:
            try:
                title_widget = self.query_one("#header-title", Static)
                title_widget.update(new_value)
            except Exception:
                pass

    def watch_is_favorite(self, new_value: bool) -> None:
        """Update favorite button display when is_favorite changes."""
        if self.is_mounted and self.show_favorite:
            try:
                favorite_widget = self.query_one("#header-favorite", Static)
                favorite_widget.update(self._favorite_label())
            except Exception:
                pass

    class BackPressed(Message):
        """Message sent when back button is pressed."""
        pass

    class FavoritePressed(Message):
        """Message sent when favorite button is pressed."""
        pass
