"""
Text Component

Reusable wrapper for rich.console.print with theme-aware styling.
"""

from typing import Optional, Literal
from rich.console import Console
from rich.text import Text
from ..console import get_console
from ...messages import msg


class TextRenderer:
    """
    Reusable wrapper for text rendering with theme-aware styling
    """

    def __init__(
        self, console: Optional[Console] = None, default_show_emoji: bool = True
    ):
        if console is None:
            console = get_console()
        self.console = console
        self.default_show_emoji = default_show_emoji

    def title(
        self, text: str, justify: Literal["left", "center", "right"] = "left"
    ) -> None:
        self.console.print(f"[bold primary]{text}[/bold primary]", justify=justify)

    def subtitle(
        self, text: str, justify: Literal["left", "center", "right"] = "left"
    ) -> None:
        self.console.print(f"[dim]{text}[/dim]", justify=justify)

    def body(self, text: str, style: Optional[str] = None) -> None:
        if style:
            self.console.print(f"[{style}]{text}[/{style}]")
        else:
            self.console.print(text)

    def success(
        self,
        text: str,
        show_emoji: Optional[bool] = None,
        justify: Literal["left", "center", "right"] = "left",
    ) -> None:
        """Print a success message with green styling"""
        self._semantic_message(text, "success", msg.EMOJI.SUCCESS, show_emoji, justify)

    def error(
        self,
        text: str,
        show_emoji: Optional[bool] = None,
        justify: Literal["left", "center", "right"] = "left",
    ) -> None:
        """Print an error message with red styling"""
        self._semantic_message(text, "error", msg.EMOJI.ERROR, show_emoji, justify)

    def warning(
        self,
        text: str,
        show_emoji: Optional[bool] = None,
        justify: Literal["left", "center", "right"] = "left",
    ) -> None:
        """Print a warning message with yellow styling"""
        self._semantic_message(text, "warning", msg.EMOJI.WARNING, show_emoji, justify)

    def info(
        self,
        text: str,
        show_emoji: Optional[bool] = None,
        justify: Literal["left", "center", "right"] = "left",
    ) -> None:
        """Print an informational message with cyan styling"""
        self._semantic_message(text, "info", msg.EMOJI.INFO, show_emoji, justify)

    def line(self, count: int = 1) -> None:
        for _ in range(count):
            self.console.print()

    def divider(self, char: str = "─", style: Optional[str] = "dim") -> None:
        divider_line = char * self.console.width
        if style:
            self.console.print(f"[{style}]{divider_line}[/{style}]")
        else:
            self.console.print(divider_line)

    def _semantic_message(
        self,
        text: str,
        message_type: str,
        icon: str,
        show_emoji: Optional[bool] = None,
        justify: Literal["left", "center", "right"] = "left",
    ) -> None:
        """Helper method for semantic messages"""
        if show_emoji is None:
            show_emoji = self.default_show_emoji

        if show_emoji:
            message = Text.assemble((f"{icon} ", ""), (text, message_type))
            self.console.print(message, justify=justify)
        else:
            self.console.print(text, style=message_type, justify=justify)

    def styled_text(
        self,
        *parts: tuple[str, str],
        justify: Literal["left", "center", "right"] = "left",
    ) -> None:
        """
        Print text with multiple styled parts.

        This is useful when you need different styles within the same line,
        such as a number in one color and a label in another.

        Args:
            *parts: Variable number of (text, style) tuples.
                   Each tuple contains the text to print and its style.
            justify: Text alignment (left, center, or right)

        Examples:
            >>> # Menu item with styled number and label
            >>> text.styled_text(
            ...     ("  1. ", "primary"),
            ...     ("Create PR", "bold")
            ... )

            >>> # Status message with multiple styles
            >>> text.styled_text(
            ...     ("Status: ", "dim"),
            ...     ("SUCCESS", "success"),
            ...     (" (completed in ", "dim"),
            ...     ("2.5s", "bold"),
            ...     (")", "dim")
            ... )

            >>> # Centered multi-styled text
            >>> text.styled_text(
            ...     ("⚡ ", ""),
            ...     ("Fast Mode", "bold primary"),
            ...     (" Enabled", "success"),
            ...     justify="center"
            ... )
        """
        message = Text.assemble(*parts)
        self.console.print(message, justify=justify)
