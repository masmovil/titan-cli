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
        ui: Reference to UIComponents for composition
    """
    prompts: PromptsRenderer
    menu: MenuRenderer
    ui: UIComponents

    def step_header(self, name: str, current: Optional[int] = None, total: Optional[int] = None) -> None:
        """
        Display a standardized step header (composition view).

        Composes text and spacer components to show a consistent
        step header across all workflow steps.

        Args:
            name: Step name
            current: Current step number (1-indexed)
            total: Total number of steps

        Examples:
            >>> ctx.views.step_header("git_status", ctx.current_step, ctx.total_steps)
            [2/7] git_status

            >>> ctx.views.step_header("my_step")
            ⚙️ my_step
        """
        if current is not None and total is not None:
            self.ui.text.body(f"[{current}/{total}] {name}")
        else:
            self.ui.text.body(f"⚙️ {name}")
        self.ui.spacer.small()

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
            menu=MenuRenderer(console=ui.text.console, text_renderer=ui.text),
            ui=ui,  # Store reference for composition
        )
