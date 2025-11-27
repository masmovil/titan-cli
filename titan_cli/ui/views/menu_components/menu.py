# ui/views/menu.py
from typing import Optional
from rich.console import Console

from .menu_models import Menu
from ...components.typography import TextRenderer
from ...components.spacer import SpacerRenderer
from ...console import get_console

class MenuRenderer:
    """Renders a Menu object to the console."""

    def __init__(
        self,
        console: Optional[Console] = None,
        text_renderer: Optional[TextRenderer] = None,
        spacer_renderer: Optional[SpacerRenderer] = None,
    ):
        self.console = console or get_console()
        self.text = text_renderer or TextRenderer(console=self.console)
        self.spacer = spacer_renderer or SpacerRenderer(console=self.console)

    def render(self, menu: Menu):
        """
        Renders the complete menu to the console.

        Args:
            menu: The Menu object to render.
        """
        self.text.title(f"{menu.emoji} {menu.title}")
        self.spacer.line()

        counter = 1
        for category in menu.categories:
            self.text.body(f"{category.emoji} {category.name}", style="bold")
            self.spacer.line()
            for item in category.items:
                self.console.print(f"  [primary]{counter:2d}.[/primary] [bold]{item.label}[/bold]")
                self.console.print(f"     [dim]{item.description}[/dim]")
                self.spacer.line()
                counter += 1

        if menu.tip:
            self.text.info(menu.tip, show_emoji=True)
            self.spacer.line()
