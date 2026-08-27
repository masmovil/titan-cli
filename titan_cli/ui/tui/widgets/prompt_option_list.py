"""
PromptOptionList Widget

Widget for selecting a single option from a list with title and description.
Similar to the workflow selection interface.
"""

from typing import Any, Callable, List
from textual.widget import Widget
from textual.widgets import OptionList
from textual.widgets.option_list import Option
from titan_cli.engine.option_item import OptionItem
from .text import BoldText, DimText


class PromptOptionList(Widget):
    """
    Widget for selecting a single option from a styled list.

    Displays a question and a list of options with bold titles and dim descriptions.
    User navigates with arrow keys and selects with Enter.

    Example:
        options = [
            OptionItem(
                value="pr1",
                title="#123: Fix bug in login",
                description="Branch: fix/login → main"
            ),
            OptionItem(
                value="pr2",
                title="#124: Add feature",
                description="Branch: feat/new → main"
            ),
        ]

        option_list = PromptOptionList(
            question="Select a PR:",
            options=options,
            on_select=lambda value: print(f"Selected: {value}")
        )
    """

    # Allow this widget to receive focus
    can_focus = True
    can_focus_children = True

    DEFAULT_CSS = """
    PromptOptionList {
        width: 100%;
        height: auto;
        padding: 1;
        margin: 1 0;
        background: $surface-lighten-1;
        border: round $accent;
    }

    PromptOptionList > BoldText,
    PromptOptionList > DimText {
        width: 100%;
        height: auto;
        margin-bottom: 0;
    }

    PromptOptionList > OptionList {
        width: 100%;
        height: auto;
        max-height: 15;
    }

    PromptOptionList .option-list--option {
        padding: 1;
    }

    PromptOptionList .option-list--option-highlighted {
        background: $accent 20%;
    }
    """

    def __init__(
        self,
        question: str,
        options: List[OptionItem],
        on_select: Callable[[Any], None],
        **kwargs
    ):
        """
        Initialize PromptOptionList.

        Args:
            question: Question to display above the option list
            options: List of OptionItem instances
            on_select: Callback that receives the selected value
        """
        super().__init__(**kwargs)
        self.question = question
        self.options = options
        self.on_select_callback = on_select

    def compose(self):
        # Question text (usando BoldText para consistencia)
        yield BoldText(self.question)

        # Instructions (usando DimText para consistencia)
        yield DimText("↑/↓: Navigate  │  Enter: Select")

        # Create Option objects for OptionList
        # Aquí usamos markup porque OptionList solo acepta strings
        option_objects = []
        for i, opt in enumerate(self.options):
            if opt.description:
                # Title in bold, description in dim
                prompt = f"[bold]{opt.title}[/bold]\n[dim]{opt.description}[/dim]"
            else:
                # Just title in bold
                prompt = f"[bold]{opt.title}[/bold]"

            option_objects.append(
                Option(prompt, id=str(i))  # Use index as ID
            )

        # OptionList widget
        yield OptionList(*option_objects, id="option-list")

    def on_mount(self):
        """Focus option list when mounted and scroll into view."""
        self.call_after_refresh(self._focus_list)

    def _focus_list(self):
        """Focus the option list widget and scroll into view."""
        try:
            option_list = self.query_one(OptionList)
            # Use app.set_focus() to force focus change
            self.app.set_focus(option_list)
            # Highlight first option
            if len(option_list._options) > 0:
                option_list.highlighted = 0
            # Scroll to make this widget visible
            self.scroll_visible(animate=False)
        except Exception:
            pass

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle when user presses Enter to select an option."""
        try:
            # Get the index from the option ID
            selected_index = int(event.option.id)
            # Get the actual value from our options list
            selected_value = self.options[selected_index].value
            # Call the callback
            self.on_select_callback(selected_value)
        except Exception:
            pass
