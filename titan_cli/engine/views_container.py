"""
UI Views container for workflow context.
"""

from dataclasses import dataclass
from typing import Optional

from titan_cli.ui.views.prompts import PromptsRenderer
from titan_cli.ui.views.menu_components.menu import MenuRenderer
from .ui_container import UIComponents


@dataclass
class UIViews:
    """
    Container for UI views (component compositions).
    
    Views are composed of basic UI components and provide
    higher-level functionality.
    
    Attributes:
        prompts: Interactive prompts (ask_text, ask_confirm, etc.)
        menu: Menu rendering and selection
    """
    prompts: PromptsRenderer
    menu: MenuRenderer

    @classmethod
    def create(cls, ui: UIComponents) -> "UIViews":
        """
        Create UI views using components.
        
        Args:
            ui: UIComponents instance for composition
        
        Returns:
            UIViews instance
        """
        return cls(
            prompts=PromptsRenderer(text_renderer=ui.text),
            menu=MenuRenderer(console=ui.text.console, text_renderer=ui.text), # Pass ui.text to menu_renderer
        )
