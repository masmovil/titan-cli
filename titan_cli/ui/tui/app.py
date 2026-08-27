"""
Titan TUI Application

Main Textual application for Titan CLI with fixed status bar and theme support.
"""
from textual.app import App
from textual.binding import Binding

from titan_cli.core.config import TitanConfig
from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.external_cli.launcher import CLILauncher
from .theme import TITAN_THEME_CSS
from .screens import MainMenuScreen


class TitanApp(App):
    """
    The main Titan TUI application.

    This is a Textual-based TUI that provides a visual interface for Titan CLI,
    with a fixed status bar at the bottom and interactive menus/workflows.

    The layout is:
    - Header (top): Title and clock
    - Main content area (scrollable)
    - Status bar (bottom, fixed): Git branch, AI info, Project
    - Footer (bottom): Keybindings
    """

    # Combine theme CSS with app-specific CSS
    CSS = TITAN_THEME_CSS

    # Allow text selection in terminal (Shift+Mouse will work in most terminals)
    ENABLE_COMMAND_PALETTE = False  # Disable Ctrl+\ interference

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+shift+c", "toggle_copy_mode", "Copy Mode"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, config: TitanConfig = None, initial_screen=None, **kwargs):
        """
        Initialize the Titan TUI application.

        Args:
            config: TitanConfig instance. If None, creates a new one.
            initial_screen: Initial screen to show. If None, shows MainMenuScreen.
                          Can be a screen instance or a callable that returns a screen.
        """
        super().__init__(**kwargs)

        # Initialize config and plugin registry
        if config is None:
            plugin_registry = PluginRegistry()
            config = TitanConfig(registry=plugin_registry)

        self.config = config
        self._initial_screen = initial_screen
        self.title = "Titan CLI"
        self.sub_title = "Development Tools Orchestrator"

    def on_mount(self) -> None:
        """Initialize app and show initial screen."""
        if self._initial_screen is not None:
            # Use custom initial screen
            if callable(self._initial_screen):
                screen = self._initial_screen()
            else:
                screen = self._initial_screen
            self.push_screen(screen)
        else:
            # Default: show main menu
            self.push_screen(MainMenuScreen(self.config))

    async def launch_external_cli(self, cli_name: str, prompt: str = None) -> int:
        """
        Launch an external CLI tool (like Claude CLI or Gemini CLI).

        Suspends the TUI, launches the external CLI, then restores the TUI.

        Args:
            cli_name: Name of the CLI to launch (e.g., "claude", "gemini")
            prompt: Optional initial prompt to pass to the CLI

        Returns:
            Exit code from the CLI tool
        """

        # Suspend the TUI temporarily
        with self.suspend():
            launcher = CLILauncher(cli_name)
            exit_code = launcher.launch(prompt=prompt)

        # TUI is automatically restored here
        return exit_code

    def action_toggle_copy_mode(self) -> None:
        """Toggle copy mode - disables mouse capture to allow text selection."""
        # Toggle mouse capture
        current = getattr(self, '_copy_mode', False)
        self._copy_mode = not current

        if self._driver is None:
            return

        # Disable/enable mouse reporting at the terminal driver level.
        # `self.mouse_capture = ...` used to be set here, but that attribute
        # doesn't exist on Textual's App - it never actually stopped the
        # terminal's SGR mouse-reporting escape codes, so this toggle was a
        # no-op besides the notification.
        if self._copy_mode:
            # Disable mouse - allows terminal selection
            self._driver._disable_mouse_support()
            self.notify("📋 Copy Mode ON - Use mouse to select text, press Ctrl+Shift+C to exit", timeout=3)
        else:
            # Re-enable mouse
            self._driver._enable_mouse_support()
            self.notify("🖱️  Copy Mode OFF - Mouse interactions restored", timeout=3)
