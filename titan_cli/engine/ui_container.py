"""
UI Components container for workflow context.
"""

from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.panel import PanelRenderer
from titan_cli.ui.components.table import TableRenderer
from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.ui.console import get_console


@dataclass
class UIComponents:
    """
    Container for basic UI components (Rich wrappers).
    
    All components share the same console instance for consistency.
    
    Attributes:
        text: Text rendering (titles, body, success, error, etc.)
        panel: Panel rendering with borders
        table: Table rendering
        spacer: Spacing utilities (line, small, medium, large)
    """
    text: TextRenderer
    panel: PanelRenderer
    table: TableRenderer
    spacer: SpacerRenderer

    @classmethod
    def create(cls, console: Optional[Console] = None) -> "UIComponents":
        """
        Create UI components with shared console.
        
        Args:
            console: Optional console (uses theme-aware default if None)
        
        Returns:
            UIComponents instance
        """
        console = console or get_console()

        return cls(
            text=TextRenderer(console=console),
            panel=PanelRenderer(console=console),
            table=TableRenderer(console=console),
            spacer=SpacerRenderer(console=console),
        )
