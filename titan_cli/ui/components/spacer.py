"""
Spacer Component

Simple, reusable component for managing vertical whitespace in terminal output.
Provides consistent spacing throughout the application.

Examples:
    >>> # Basic usage
    >>> spacer = SpacerRenderer()
    >>>
    >>> # Print single line
    >>> spacer.line()
    >>>
    >>> # Print multiple lines
    >>> spacer.lines(3)
    >>>
    >>> # Use predefined spacing
    >>> spacer.small()   # 1 line
    >>> spacer.medium()  # 2 lines
    >>> spacer.large()   # 3 lines
"""

from typing import Optional
from rich.console import Console
from ..console import get_console # Import our global theme-aware console


class SpacerRenderer:
    """
    Reusable wrapper for managing vertical whitespace in the console.

    Provides consistent, reusable spacing between UI components.

    Usage:
        >>> spacer = SpacerRenderer()
        >>> spacer.line()      # 1 line
        >>> spacer.small()     # 1 line
        >>> spacer.medium()    # 2 lines
        >>> spacer.large()     # 3 lines
        >>> spacer.lines(5)    # Custom count
    """

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize SpacerRenderer

        Args:
            console: Rich Console instance (uses global theme-aware console if None)
        """
        if console is None:
            console = get_console()
        self.console = console

    def line(self) -> None:
        """Print single blank line"""
        self.console.print()

    def lines(self, count: int = 1) -> None:
        """
        Print multiple blank lines

        Args:
            count: Number of blank lines to print (default: 1)
        """
        for _ in range(count):
            self.console.print()

    def small(self) -> None:
        """Small spacing (1 line)"""
        self.lines(1)

    def medium(self) -> None:
        """Medium spacing (2 lines)"""
        self.lines(2)

    def large(self) -> None:
        """Large spacing (3 lines)"""
        self.lines(3)