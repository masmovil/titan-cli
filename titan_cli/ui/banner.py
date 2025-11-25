"""
Banner Component

ASCII art banners with gradient colors using Rich.
"""

from typing import List, Optional
from rich.text import Text
from .console import console
from ..messages import msg


def render_ascii_banner(
    lines: List[str],
    subtitle: Optional[str] = None,
    colors: Optional[List[str]] = None,
    justify: str = "center"
) -> None:
    """
    Render ASCII art banner with gradient colors

    Args:
        lines: List of ASCII art lines
        subtitle: Optional subtitle below the banner
        colors: List of hex colors for gradient (default: blue to pink)
        justify: Text alignment (left, center, right)

    Examples:
        >>> lines = [
        ...     "▀█▀ █ ▀█▀ ▄▀█ █▄ █",
        ...     " █  █  █  █▀█ █ ▀█"
        ... ]
        >>> render_ascii_banner(lines, subtitle="My App")
    """
    # Default gradient: blue → purple → pink
    if colors is None:
        colors = ["#3B82F6", "#6366F1", "#8B5CF6", "#A855F7", "#C026D3", "#DB2777", "#E11D48"]

    banner = Text()

    for line in lines:
        colored_line = Text()
        chars_per_color = len(line) // len(colors)

        for i, char in enumerate(line):
            color_idx = min(i // max(chars_per_color, 1), len(colors) - 1)
            colored_line.append(char, style=colors[color_idx])

        banner.append(colored_line)
        banner.append("\n")

    print()
    console.print(banner, justify=justify)

    if subtitle:
        console.print(Text(subtitle, style="dim italic"), justify=justify)

    print()


def render_titan_banner(subtitle: str = None) -> None:
    """
    Render TITAN CLI banner with default styling

    Args:
        subtitle: Subtitle text (default from messages.py)

    Examples:
        >>> render_titan_banner()
        >>> render_titan_banner("Custom subtitle")
        >>> render_titan_banner(msg.UI.BANNER_WORKFLOW)
    """
    lines = [
        "▀█▀ █ ▀█▀ ▄▀█ █▄ █   █▀▀ █   █",
        " █  █  █  █▀█ █ ▀█   █▄▄ █▄▄ █"
    ]

    # Use default subtitle from messages if not provided
    if subtitle is None:
        subtitle = msg.UI.BANNER_DEFAULT

    render_ascii_banner(lines, subtitle=subtitle)
