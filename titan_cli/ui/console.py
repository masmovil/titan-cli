"""
Global Console Instance

Singleton console instance for consistent output across the application.
"""

from rich.console import Console
from typing import Optional
from titan_cli.ui.theme import TITAN_THEME # Import the theme

# Global console instance
_console: Optional[Console] = None


def get_console() -> Console:
    """
    Get the global console instance

    Returns:
        Shared Console instance

    Examples:
        >>> from titan_cli.ui.components.console import get_console
        >>> console = get_console()
        >>> console.print("Hello", style="success") # Now uses theme style
    """
    global _console
    if _console is None:
        _console = Console(theme=TITAN_THEME) # Initialize with the theme
    return _console


# Convenience alias
console = get_console()
