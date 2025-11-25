from typing import Optional, Literal, Tuple, Union
from rich.panel import Panel
from rich.console import Console
from rich import box as rich_box
from ..console import get_console # Import our global theme-aware console

BorderStyle = Literal["ascii", "rounded", "heavy", "double", "none"]
BorderStyleOrBox = Union[BorderStyle, rich_box.Box, None]

# Map border style names to Rich box types
BORDER_STYLES = {
    "ascii": rich_box.ASCII,
    "rounded": rich_box.ROUNDED,
    "heavy": rich_box.HEAVY,
    "double": rich_box.DOUBLE,
    "none": None
}

# Panel style presets based on common usage patterns
class PanelStyle:
    """Predefined panel styles with theme-aware colors"""

    INFO = {
        "style": "info",
        "border_style": rich_box.ROUNDED,
        "title": "ℹ️ Info"
    }

    SUCCESS = {
        "style": "success",
        "border_style": rich_box.ROUNDED,
        "title": "✅ Success",
    }

    ERROR = {
        "style": "error",
        "border_style": rich_box.HEAVY,
        "title": "❌ Error"
    }

    WARNING = {
        "style": "warning",
        "border_style": rich_box.ROUNDED,
        "title": "⚠️ Warning"
    }

    DEFAULT = {
        "style": None,
        "border_style": rich_box.ROUNDED,
        "title": None
    }

class PanelRenderer:
    """
    Reusable wrapper for rich.Panel with theme-aware styling

    Provides a consistent interface for panel rendering with:
    - Theme-aware color schemes
    - Predefined styles (info, success, error, warning)
    - Centralized configuration
    - Dependency injection support

    This component follows the project's DI pattern and can be injected
    into higher-level components for testability.

    Examples:
        >>> # Basic usage
        >>> renderer = PanelRenderer() # Uses global theme-aware console
        >>> panel = renderer.render("Hello World", title="Greeting")
        >>> get_console().print(panel)

        >>> # Success panel
        >>> panel = renderer.success("Task completed!")
        >>> get_console().print(panel)

        >>> # Custom styling
        >>> panel = renderer.render(
        ...     "Custom content",
        ...     title="Alert",
        ...     style="primary bold",
        ...     border_style="double"
        ... )

        >>> # Direct print (convenience)
        >>> renderer.print("Info message", panel_type="info")
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        default_border_style: BorderStyle = "rounded",
        default_padding: Tuple[int, int] = (1, 2),
        default_expand: bool = False
    ):
        """
        Initialize panel renderer

        Args:
            console: Rich Console instance (uses global theme-aware console if None)
            default_border_style: Default border style for all panels
            default_padding: Default (vertical, horizontal) padding
            default_expand: Expand panels to full width by default
        """
        if console is None:
            console = get_console() # Use our global theme-aware console
        self.console = console
        self.default_border_style = default_border_style
        self.default_padding = default_padding
        self.default_expand = default_expand

    def _get_border_style(self, border_style):
        """
        Get border style with fallback to default

        Accepts both string names ("rounded", "heavy") and rich_box objects directly
        """
        # If None, use default
        if border_style is None:
            border_style = self.default_border_style

        # If it's already a rich_box object, return it
        if isinstance(border_style, rich_box.Box):
            return border_style

        # If it's a string, convert it
        return BORDER_STYLES.get(border_style, rich_box.ROUNDED)

    def render(
        self,
        content: str,
        title: Optional[str] = None,
        style: Optional[str] = None,
        border_style: BorderStyleOrBox = None,
        title_align: Literal["left", "center", "right"] = "left",
        padding: Optional[Tuple[int, int]] = None,
        expand: Optional[bool] = None,
        subtitle: Optional[str] = None
    ) -> Panel:
        """
        Create a panel with custom styling

        Args:
            content: Panel content (can be markdown or rich renderables)
            title: Optional title
            style: Color/style name (e.g., "cyan", "green", "red1")
            border_style: Border style (ascii, rounded, heavy, double, none)
            title_align: Title alignment (left, center, right)
            padding: (vertical, horizontal) padding override
            expand: Expand to full width override
            subtitle: Optional subtitle at bottom

        Returns:
            Rich Panel object ready to print

        Examples:
            >>> renderer = PanelRenderer()
            >>> panel = renderer.render("Hello", title="Greeting")
            >>> console.print(panel)

            >>> # Custom style
            >>> panel = renderer.render(
            ...     "Important!",
            ...     title="Alert",
            ...     style="magenta bold",
            ...     border_style="heavy"
            ... )
        """
        box_style = self._get_border_style(border_style)

        # Build panel kwargs, only include style if not None
        panel_kwargs = {
            "title": title,
            "box": box_style,
            "title_align": title_align,
            "padding": padding if padding is not None else self.default_padding,
            "expand": expand if expand is not None else self.default_expand,
        }

        if style is not None:
            panel_kwargs["style"] = style

        if subtitle is not None:
            panel_kwargs["subtitle"] = subtitle

        return Panel(content, **panel_kwargs)

    def info(
        self,
        content: str,
        title: Optional[str] = None,
        **kwargs
    ) -> Panel:
        """
        Create an info panel (cyan border, rounded box)

        Matches display.py render_info_panel() styling exactly.

        Args:
            content: Panel content
            title: Optional title (uses default "ℹ️ Info" if None)
            **kwargs: Additional arguments passed to render()

        Returns:
            Rich Panel object

        Examples:
            >>> renderer = PanelRenderer()
            >>> panel = renderer.info("This is informational")
            >>> console.print(panel)
        """
        preset = PanelStyle.INFO

        return self.render(
            content,
            title=title if title is not None else preset["title"],
            style=preset["style"],
            border_style=preset["border_style"],  # Pass preset box
            **kwargs
        )

    def success(
        self,
        content: str,
        title: Optional[str] = None,
        **kwargs
    ) -> Panel:
        """
        Create a success panel (green border, rounded box)

        Matches display.py render_success_panel() styling exactly.

        Args:
            content: Panel content
            title: Optional title (uses default "✅ Success" if None)
            **kwargs: Additional arguments passed to render()

        Returns:
            Rich Panel object

        Examples:
            >>> renderer = PanelRenderer()
            >>> panel = renderer.success("Operation completed!")
            >>> console.print(panel)
        """
        preset = PanelStyle.SUCCESS

        return self.render(
            content,
            title=title if title is not None else preset["title"],
            style=preset["style"],
            border_style=preset["border_style"],  # Pass preset box
            **kwargs
        )

    def error(
        self,
        content: str,
        title: Optional[str] = None,
        **kwargs
    ) -> Panel:
        """
        Create an error panel (red1 border, heavy box)

        Matches display.py render_error_panel() styling exactly.

        Args:
            content: Panel content
            title: Optional title (uses default "❌ Error" if None)
            **kwargs: Additional arguments passed to render()

        Returns:
            Rich Panel object

        Examples:
            >>> renderer = PanelRenderer()
            >>> panel = renderer.error("An error occurred!")
            >>> console.print(panel)
        """
        preset = PanelStyle.ERROR

        return self.render(
            content,
            title=title if title is not None else preset["title"],
            style=preset["style"],
            border_style=preset["border_style"],  # Pass preset box (HEAVY)
            **kwargs
        )

    def warning(
        self,
        content: str,
        title: Optional[str] = None,
        **kwargs
    ) -> Panel:
        """
        Create a warning panel (yellow border, rounded box)

        Matches display.py render_warning_panel() styling exactly.

        Args:
            content: Panel content
            title: Optional title (uses default "⚠️ Warning" if None)
            **kwargs: Additional arguments passed to render()

        Returns:
            Rich Panel object

        Examples:
            >>> renderer = PanelRenderer()
            >>> panel = renderer.warning("Proceed with caution")
            >>> console.print(panel)
        """
        preset = PanelStyle.WARNING

        return self.render(
            content,
            title=title if title is not None else preset["title"],
            style=preset["style"],
            border_style=preset["border_style"],  # Pass preset box
            **kwargs
        )

    def print(
        self,
        content: str,
        panel_type: Literal["info", "success", "error", "warning", "default"] = "default",
        **kwargs
    ) -> None:
        """
        Create and print a panel in one step

        Convenience method that creates and prints directly to console.

        Args:
            content: Panel content
            panel_type: Type of panel (info, success, error, warning, default)
            **kwargs: Additional arguments passed to the panel method

        Examples:
            >>> renderer = PanelRenderer()
            >>> renderer.print("Task done!", panel_type="success")
            >>> renderer.print("Error occurred", panel_type="error")
        """
        if panel_type == "info":
            panel = self.info(content, **kwargs)
        elif panel_type == "success":
            panel = self.success(content, **kwargs)
        elif panel_type == "error":
            panel = self.error(content, **kwargs)
        elif panel_type == "warning":
            panel = self.warning(content, **kwargs)
        else:
            panel = self.render(content, **kwargs)

        self.console.print(panel)