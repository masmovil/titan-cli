"""
Table Renderer Component

Reusable wrapper for rich.table.Table with centralized theme-aware styling.
"""

from typing import List, Optional, Literal, Union
from rich.table import Table
from rich.console import Console
from rich import box as rich_box
from ..console import get_console

BoxStyle = Literal["simple", "minimal", "rounded", "heavy", "double", "none"]
BoxStyleOrBox = Union[BoxStyle, rich_box.Box, None]

BOX_STYLES = {
    "simple": rich_box.SIMPLE,
    "minimal": rich_box.MINIMAL,
    "rounded": rich_box.ROUNDED,
    "heavy": rich_box.HEAVY,
    "double": rich_box.DOUBLE,
    "none": None
}


class TableRenderer:
    """
    Reusable wrapper for rich.Table with theme-aware styling.

    Provides a consistent interface for table rendering with:
    - Theme-aware styling for titles and headers.
    - Predefined box styles.
    - Centralized configuration and dependency injection support.
    """

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize TableRenderer.

        Args:
            console: Optional Rich console instance. If None, uses the global
                     theme-aware console, enabling dependency injection for testing.
        """
        if console is None:
            console = get_console()
        self.console = console

    def render(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None,
        show_header: bool = True,
        show_lines: bool = False,
        box_style: BoxStyleOrBox = "rounded",
        title_style: Optional[str] = "primary",
        header_style: Optional[str] = "primary",
        row_styles: Optional[List[str]] = None,
        caption: Optional[str] = None,
        expand: bool = False
    ) -> Table:
        """
        Renders data into a rich.table.Table object.

        This method constructs a Table with theme-aware defaults and populates
        it with the provided data.

        Args:
            headers: A list of strings for the table's column headers.
            rows: A list of lists, where each inner list represents a row.
            title: An optional title displayed above the table.
            show_header: Whether to display the header row (default: True).
            show_lines: Whether to draw lines between rows (default: False).
            box_style: The border style for the table (e.g., "rounded", "heavy").
            title_style: The theme style for the title (default: "primary").
            header_style: The theme style for the headers (default: "primary").
            row_styles: A list of styles to alternate between rows (e.g., ["dim", "none"]).
            caption: An optional caption displayed below the table.
            expand: Whether the table should expand to the full width of the console.

        Returns:
            A rich.table.Table object, ready to be printed.

        Raises:
            ValueError: If a row has a different number of elements than the number of headers.
        
        Examples:
            >>> renderer = TableRenderer()
            >>> table = renderer.render(
            ...     headers=["Name", "Status"],
            ...     rows=[["Alice", "Active"], ["Bob", "Inactive"]],
            ...     title="User List"
            ... )
            >>> console.print(table)
        """
        box = self._resolve_box_style(box_style)
        table = Table(
            title=title,
            title_style=title_style,
            show_header=show_header,
            header_style=header_style,
            show_lines=show_lines,
            box=box,
            caption=caption,
            expand=expand
        )

        for header in headers:
            table.add_column(header)

        for i, row in enumerate(rows):
            if len(row) != len(headers):
                raise ValueError(f"Row {i} has {len(row)} elements but {len(headers)} headers were provided")
            style = None
            if row_styles:
                style = row_styles[i % len(row_styles)]
            table.add_row(*row, style=style)

        return table

    def print_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        **kwargs
    ) -> None:
        """
        Renders and prints a table in a single step.

        This is a convenience method that calls render() and then prints
        the resulting table to the console.

        Args:
            headers: A list of strings for the table's column headers.
            rows: A list of lists, where each inner list represents a row.
            **kwargs: Additional arguments passed directly to the render() method.
        
        Examples:
            >>> renderer = TableRenderer()
            >>> renderer.print_table(
            ...     headers=["Name", "Age"],
            ...     rows=[["Alice", "25"]],
            ...     title="Age Table"
            ... )
        """
        table = self.render(headers, rows, **kwargs)
        self.console.print(table)

    def _resolve_box_style(self, box_style: BoxStyleOrBox) -> Optional[rich_box.Box]:
        """
        Resolves a box style name into a rich.box object.

        Args:
            box_style: A string name (e.g., "rounded") or a rich.box.Box object.

        Returns:
            A rich.box.Box object or None.
        """
        if box_style is None:
            return None
        if isinstance(box_style, rich_box.Box):
            return box_style
        if isinstance(box_style, str):
            return BOX_STYLES.get(box_style)
        return None