"""
Base Screen

Base class for all Titan TUI screens with consistent layout.
"""
from textual.app import ComposeResult
from textual.screen import Screen

from titan_cli.core.config import TitanConfig
from titan_cli.ui.tui.widgets.status_bar import StatusBarWidget
from titan_cli.ui.tui.widgets.header import HeaderWidget
from titan_cli.core.result import ClientSuccess

class BaseScreen(Screen):
    """
    Base screen with consistent layout for all Titan screens.

    Provides:
    - Header (top)
    - Content area (middle) - to be defined by subclasses
    - StatusBar (bottom, above footer)
    - Footer (bottom)

    Subclasses should override `compose_content()` to define their content.
    """

    CSS = """
    BaseScreen {
        background: $surface;
    }

    #screen-content {
        height: 1fr;
        overflow-y: auto;
    }
    """

    def __init__(
        self,
        config: TitanConfig,
        title: str = "Titan CLI",
        show_back: bool = False,
        show_favorite: bool = False,
        is_favorite: bool = False,
        show_status_bar: bool = True,
        **kwargs,
    ):
        """
        Initialize base screen.

        Args:
            config: TitanConfig instance
            title: Title to display in header
            show_back: Whether to show back button in header
            show_favorite: Whether to show favorite button in header
            is_favorite: Initial favorite state for the header button
            show_status_bar: Whether to show status bar at bottom
        """
        super().__init__(**kwargs)
        self.config = config
        self.screen_title = title
        self.show_back = show_back
        self.show_favorite = show_favorite
        self.is_favorite = is_favorite
        self.show_status_bar = show_status_bar

    def compose(self) -> ComposeResult:
        """Compose the base screen layout."""
        # Header with title and optional back/favorite buttons
        yield HeaderWidget(
            title=self.screen_title,
            show_back=self.show_back,
            show_favorite=self.show_favorite,
            is_favorite=self.is_favorite,
        )

        # Content area - subclasses define this
        yield from self.compose_content()

        # StatusBar with current config values (optional)
        if self.show_status_bar:
            status_bar = StatusBarWidget(id="status-bar")
            self._update_status_bar(status_bar)
            yield status_bar

    def _update_status_bar(self, status_bar: StatusBarWidget) -> None:
        """
        Update status bar with current config values.

        Args:
            status_bar: StatusBarWidget to update
        """
        from titan_cli.ai.constants import get_source_display_name
        # Get git status
        git_branch = "N/A"
        try:
            git_plugin = self.config.registry.get_plugin("git")
            if git_plugin and git_plugin.is_available():
                git_client = git_plugin.get_client()
                result = git_client.get_status()
                match result:
                    case ClientSuccess(data=git_status):
                        git_branch = git_status.branch
                    case _:
                        git_branch = "N/A"
        except Exception:
            pass

        # Get AI info directly from config
        ai_info = "N/A"
        if (
            self.config.config
            and self.config.config.ai
            and self.config.config.ai.default_connection
        ):
            default_connection_id = self.config.config.ai.default_connection
            if default_connection_id in self.config.config.ai.connections:
                connection_cfg = self.config.config.ai.connections[
                    default_connection_id
                ]
                source_name = get_source_display_name(
                    connection_cfg.provider or connection_cfg.gateway_backend
                )
                model = connection_cfg.default_model or "default"
                ai_info = f"{source_name} / {model}"

        # Get project name directly from config
        project_name = self.config.get_project_name() or "N/A"

        # Update status bar
        status_bar.git_branch = git_branch
        status_bar.ai_info = ai_info
        status_bar.project_name = project_name

    def on_resume(self) -> None:
        """Called when screen is resumed (e.g., after another screen is dismissed)."""
        # Refresh status bar with latest config values
        if self.show_status_bar:
            try:
                # Reload config from disk to get latest changes
                self.config.load()

                status_bar = self.query_one("#status-bar", StatusBarWidget)
                self._update_status_bar(status_bar)
            except Exception:
                pass  # Status bar might not be mounted yet

    def on_header_widget_back_pressed(self, message: HeaderWidget.BackPressed) -> None:
        """Handle back button press from header."""
        self.action_go_back()

    def action_go_back(self) -> None:
        """Go back to previous screen. Override in subclasses if needed."""
        self.app.pop_screen()

    def on_header_widget_favorite_pressed(self, message: HeaderWidget.FavoritePressed) -> None:
        """Handle favorite button press from header."""
        self.action_toggle_favorite()

    def action_toggle_favorite(self) -> None:
        """Toggle favorite status for the screen's subject. Override in subclasses."""
        pass
