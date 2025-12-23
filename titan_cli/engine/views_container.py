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

    def step_header(self, name: str, step_type: Optional[str] = None, step_detail: Optional[str] = None) -> None:
        """
        Display a standardized step header (composition view).

        Args:
            name: Step name
            step_type: Type of step (plugin, command, workflow, hook)
            step_detail: Additional detail (e.g., "git.get_status", "workflow:commit-ai")

        Examples:
            >>> ctx.views.step_header("Check Git Status", step_type="plugin", step_detail="git.get_status")

            🔧 Check Git Status
               git.get_status
            ─────────────────────────────────────────────────────────────
        """
        # Determine icon based on step type
        icon_map = {
            "plugin": "🔧",
            "command": "💻",
            "workflow": "🔄",
            "hook": "⚡",
        }
        icon = icon_map.get(step_type, "⚙️")

        # Show step name with icon (bold)
        self.ui.text.styled_text((f"{icon} {name}", "bold cyan"))

        # Show detail if provided (dimmed, indented)
        if step_detail:
            self.ui.text.styled_text((f"   {step_detail}", "dim"))

        # Separator line
        self.ui.text.styled_text(("─" * 60, "dim"))
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
