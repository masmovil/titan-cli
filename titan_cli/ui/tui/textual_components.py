"""
Textual UI Components container for workflow context.

Provides utilities for workflow steps to mount widgets and request user input in the TUI.

Steps can import widgets directly from titan_cli.ui.tui.widgets and mount them using ctx.textual.
"""

import threading
from typing import Optional, List, Any
from contextlib import contextmanager
from textual.widget import Widget
from textual.widgets import LoadingIndicator, Static, Markdown
from textual.containers import Container
from titan_cli.ui.tui.widgets import Panel, PromptInput, PromptTextArea, PromptSelectionList, SelectionOption, PromptChoice, ChoiceOption, PromptOptionList, OptionItem, DecisionBadge


class TextualComponents:
    """
    Textual UI utilities for workflow steps.

    All text styling uses the theme system for consistent colors across themes.

    Steps can use these utilities to:
    - Display panels with consistent styling
    - Append text with theme-based styling
    - Request user input interactively
    - Mount custom widgets to the output panel

    Example:
        def my_step(ctx):
            # Show a panel
            ctx.textual.panel("Warning message", panel_type="warning")

            # Append styled text (uses theme system)
            ctx.textual.dim_text("Fetching data...")
            ctx.textual.success_text("Operation completed!")
            ctx.textual.error_text("Failed to connect")
            ctx.textual.bold_primary_text("AI Analysis Results")

            # Append plain text
            ctx.textual.text("Processing...")

            # Ask for input
            response = ctx.textual.ask_confirm("Continue?", default=True)
    """

    def __init__(self, app, output_widget):
        """
        Initialize Textual components.

        Args:
            app: TitanApp instance for thread synchronization
            output_widget: WorkflowExecutionContent widget to render to
        """
        self.app = app
        self.output_widget = output_widget
        self._active_step_container = None

    def begin_step(self, step_name: str) -> None:
        """
        Begin a new step by creating a StepContainer and auto-scrolling to it.

        Args:
            step_name: Name of the step
        """
        from titan_cli.ui.tui.widgets import StepContainer

        def _create_container():
            container = StepContainer(step_name=step_name)
            self.output_widget.mount(container)
            self._active_step_container = container
            # Auto-scroll to show the new step
            self.output_widget._scroll_to_end()

        try:
            self.app.call_from_thread(_create_container)
        except Exception:
            pass

    def end_step(self, result_type: str) -> None:
        """
        End the current step by updating its container color.

        Args:
            result_type: One of 'success', 'skip', 'error'
        """
        if not self._active_step_container:
            return

        def _update_container():
            if self._active_step_container:
                self._active_step_container.set_result(result_type)
                self._active_step_container = None

        try:
            self.app.call_from_thread(_update_container)
        except Exception:
            pass

    def mount(self, widget: Widget) -> None:
        """
        Mount a widget to the output panel.

        Args:
            widget: Any Textual widget to mount (Panel, DimText, etc.)

        Example:
            from titan_cli.ui.tui.widgets import Panel
            ctx.textual.mount(Panel("Success!", panel_type="success"))
        """
        def _mount():
            # Mount to active step container if it exists, otherwise to output widget
            target = self._active_step_container if self._active_step_container else self.output_widget
            target.mount(widget)

        # call_from_thread already blocks until the function completes
        try:
            self.app.call_from_thread(_mount)
        except Exception:
            # App is closing or worker was cancelled
            pass

    def scroll_to_end(self) -> None:
        """
        Scroll to the end of the output widget.

        Useful for ensuring user sees newly added content in steps with lots of output.

        Example:
            ctx.textual.markdown(large_content)
            ctx.textual.scroll_to_end()  # Ensure user sees what comes next
        """
        def _scroll():
            self.output_widget._scroll_to_end()

        try:
            self.app.call_from_thread(_scroll)
        except Exception:
            pass

    def _append_text_no_truncate(self, text: str) -> None:
        """
        Internal helper to append text without truncation.

        Creates a Static widget with proper overflow handling to show full text.

        Args:
            text: Text to append
        """
        widget = Static(text)
        widget.styles.width = "100%"
        widget.styles.height = "auto"
        widget.styles.overflow_x = "auto"
        self.output_widget.mount(widget)

    def text(self, text: str) -> None:
        """
        Append plain text without styling.

        For styled text, use specific methods: dim_text(), success_text(), etc.

        Args:
            text: Text to append

        Example:
            ctx.textual.text("Processing...")
            ctx.textual.text("")  # Empty line
        """
        def _append():
            # If there's an active step container, append to it; otherwise to output widget
            if self._active_step_container:
                from textual.widgets import Static
                widget = Static(text)
                widget.styles.height = "auto"
                self._active_step_container.mount(widget)
            else:
                self.output_widget.append_output(text)

        # call_from_thread already blocks until the function completes
        try:
            self.app.call_from_thread(_append)
        except Exception:
            # App is closing or worker was cancelled
            pass

    def markdown(self, markdown_text: str) -> None:
        """
        Render markdown content (parent container handles scrolling).

        Args:
            markdown_text: Markdown content to render

        Example:
            ctx.textual.markdown("## My Title\n\nSome **bold** text")
        """
        # Create markdown widget directly (Textual's Markdown already handles wrapping)
        md_widget = Markdown(markdown_text)

        # Apply basic styling - let it expand fully, parent has scroll
        md_widget.styles.width = "100%"
        md_widget.styles.height = "auto"
        md_widget.styles.padding = (1, 2)
        md_widget.styles.margin = (0, 0, 1, 0)

        def _mount():
            # Mount to active step container if it exists, otherwise to output widget
            target = self._active_step_container if self._active_step_container else self.output_widget
            target.mount(md_widget)
            # Note: Screen handles auto-scroll when step completes, not here

        # call_from_thread already blocks until the function completes
        try:
            self.app.call_from_thread(_mount)
        except Exception:
            # App is closing or worker was cancelled
            pass

    def panel(
        self,
        text: str,
        panel_type: str = "info",
        show_icon: bool = True,
        use_markdown: bool = False,
    ) -> None:
        """
        Show a panel with consistent styling.

        Args:
            text: Text to display in the panel
            panel_type: Type of panel - "info", "success", "warning", or "error"
            show_icon: Whether to show the type icon (default: True)
            use_markdown: Render content as markdown instead of plain text

        Example:
            ctx.textual.panel("Operation completed successfully!", panel_type="success")
            ctx.textual.panel("Warning: This action cannot be undone", panel_type="warning")
            ctx.textual.panel("## Analysis\n\n- Point one", panel_type="info", use_markdown=True)
        """
        panel_widget = Panel(text=text, panel_type=panel_type, show_icon=show_icon, use_markdown=use_markdown)
        self.mount(panel_widget)

    def table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: str = "",
        full_width: bool = True,
        cell_padding: int = 1,
        zebra_stripes: bool = False,
        show_header: bool = True,
        show_cursor: bool = True,
        cursor_type: str = "row",
        row_height: int = 1,
    ) -> None:
        """
        Show a table with consistent styling.

        Args:
            headers: List of column headers
            rows: List of rows (each row is a list of cell values)
            title: Optional title shown on the table border
            full_width: If False, table uses auto width (compact mode)
            cell_padding: Horizontal padding inside each cell (default 1)
            zebra_stripes: Alternate row background colours
            show_header: Show the column header row
            show_cursor: Show the cursor highlight
            cursor_type: Cursor movement mode ("cell", "row", "column", "none")
            row_height: Number of lines per row (default 1, use 2+ for multiline cells)

        Example:
            ctx.textual.table(headers=["Name", "Value"], rows=[["foo", "bar"]])
            ctx.textual.table(headers=headers, rows=rows, title="Results", row_height=2)
        """
        from titan_cli.ui.tui.widgets import Table
        table_widget = Table(
            headers=headers,
            rows=rows,
            title=title,
            full_width=full_width,
            cell_padding=cell_padding,
            zebra_stripes=zebra_stripes,
            show_header=show_header,
            show_cursor=show_cursor,
            cursor_type=cursor_type,
            row_height=row_height,
        )
        self.mount(table_widget)

    def dim_text(self, text: str) -> None:
        """
        Append dim/muted text (uses theme system).

        Args:
            text: Text to display

        Example:
            ctx.textual.dim_text("Fetching versions for project: ECAPP")
        """
        from titan_cli.ui.tui.widgets import DimText
        widget = DimText(text)
        widget.styles.height = "auto"
        self.mount(widget)

    def success_text(self, text: str) -> None:
        """
        Append success text (green, uses theme system).

        Args:
            text: Text to display

        Example:
            ctx.textual.success_text("Commit created: abc1234")
        """
        from titan_cli.ui.tui.widgets import SuccessText
        widget = SuccessText(text)
        widget.styles.height = "auto"
        self.mount(widget)

    def error_text(self, text: str) -> None:
        """
        Append error text (red, uses theme system).

        Args:
            text: Text to display

        Example:
            ctx.textual.error_text("Failed to connect to API")
        """
        from titan_cli.ui.tui.widgets import ErrorText
        widget = ErrorText(text)
        widget.styles.height = "auto"
        self.mount(widget)

    def warning_text(self, text: str) -> None:
        """
        Append warning text (yellow, uses theme system).

        Args:
            text: Text to display

        Example:
            ctx.textual.warning_text("This action will overwrite existing files")
        """
        from titan_cli.ui.tui.widgets import WarningText
        widget = WarningText(text)
        widget.styles.height = "auto"
        self.mount(widget)

    def ai_chip(self, text: str) -> None:
        """
        Show which AI is serving this step, as a tinted chip.

        Written to be passed straight to the façade as a sink:
        `ctx.ai_router.generate_text(..., announce=ctx.textual.ai_chip)`. It exists because a
        dim line naming the provider was indistinguishable from the progress text around it,
        and noticing the wrong AI is what makes a user go and change it.

        Args:
            text: Provider summary, e.g. "claude · CLI, automatic"

        Example:
            ctx.textual.ai_chip("claude · CLI, automatic")
        """
        from titan_cli.ui.tui.icons import Icons
        from titan_cli.ui.tui.widgets import Chip
        widget = Chip(f"{Icons.AI} {text}")
        widget.styles.height = "auto"
        self.mount(widget)

    def primary_text(self, text: str) -> None:
        """
        Append primary colored text (uses theme system).

        Args:
            text: Text to display

        Example:
            ctx.textual.primary_text("Processing items...")
        """
        from titan_cli.ui.tui.widgets import PrimaryText
        widget = PrimaryText(text)
        widget.styles.height = "auto"
        self.mount(widget)

    def bold_text(self, text: str) -> None:
        """
        Append bold text.

        Args:
            text: Text to display

        Example:
            ctx.textual.bold_text("Important: Read carefully")
        """
        from titan_cli.ui.tui.widgets import BoldText
        widget = BoldText(text)
        widget.styles.height = "auto"
        self.mount(widget)

    def bold_primary_text(self, text: str) -> None:
        """
        Append bold text with primary theme color.

        Args:
            text: Text to display

        Example:
            ctx.textual.bold_primary_text("AI Analysis Results")
        """
        from titan_cli.ui.tui.widgets import BoldPrimaryText
        widget = BoldPrimaryText(text)
        widget.styles.height = "auto"
        self.mount(widget)

    def show_diff_stat(
        self,
        formatted_files: List[str],
        formatted_summary: List[str],
        title: str = "Changes summary:",
        use_panel: bool = False,
    ) -> None:
        """
        Render a formatted git diff --stat display.

        Displays a titled block with file change lines (colored) and summary line (dimmed).
        Use alongside format_diff_stat_display() from titan_plugin_git.operations.

        Args:
            formatted_files: Colored file change lines (from format_diff_stat_display)
            formatted_summary: Colored summary lines (from format_diff_stat_display)
            title: Section title to show above the file list
            use_panel: If True, wrap the content in a bordered panel instead of plain text

        Example:
            from titan_plugin_git.operations import format_diff_stat_display
            formatted_files, formatted_summary = format_diff_stat_display(stat_output)
            ctx.textual.show_diff_stat(formatted_files, formatted_summary, "Changes in branch:")
            ctx.textual.show_diff_stat(formatted_files, formatted_summary, "Changes made:", use_panel=True)
        """
        if use_panel:
            panel_content = "\n".join(formatted_files + [""] + formatted_summary)
            self.panel(panel_content, show_icon=False)
        else:
            self.text("")
            self.bold_text(title)
            self.text("")
            for line in formatted_files:
                self.text(f"  {line}")
            for line in formatted_summary:
                self.dim_text(f"  {line}")
            self.text("")

    def ask_text(self, question: str, default: str = "") -> Optional[str]:
        """
        Ask user for text input (blocks until user responds).

        Args:
            question: Question to ask
            default: Default value

        Returns:
            User's input text, or None if empty (or if cancelled)

        Raises:
            KeyboardInterrupt: If user presses Escape to cancel

        Example:
            message = ctx.textual.ask_text("Enter commit message:", default="")
        """
        # Event and result container for synchronization
        result_event = threading.Event()
        result_container = {"value": None, "cancelled": False}

        def _mount_input():
            # Handler when Enter is pressed
            def on_submitted(value: str):
                result_container["value"] = value
                result_container["cancelled"] = False

                # Show what user entered (confirmation)
                self._append_text_no_truncate(f"  → {value}")

                # Remove the input widget
                input_widget.remove()

                # Unblock the step
                result_event.set()

            # Handler when Escape is pressed
            def on_cancelled():
                result_container["value"] = None
                result_container["cancelled"] = True

                # Show cancellation message
                self.output_widget.append_output("  [dim](cancelled)[/dim]")

                # Remove the input widget
                input_widget.remove()

                # Unblock the step
                result_event.set()

            # Create PromptInput widget that handles the submission
            input_widget = PromptInput(
                question=question,
                default=default,
                placeholder="Type here and press Enter... (Esc to cancel)",
                on_submit=on_submitted,
                on_cancel=on_cancelled
            )

            # Mount the widget (it will auto-focus)
            self.output_widget.mount(input_widget)

        # Call from thread since executor runs in background thread
        try:
            self.app.call_from_thread(_mount_input)
        except Exception:
            # App is closing or worker was cancelled
            return default

        # BLOCK here until user responds (with timeout to allow cancellation)
        # Wait in loop with timeout so we can be interrupted
        while not result_event.is_set():
            if result_event.wait(timeout=0.5):
                break
            # Check if app is still running
            if not self.app.is_running:
                return default

        # Check if user cancelled
        if result_container.get("cancelled", False):
            raise KeyboardInterrupt("User cancelled input")

        return result_container["value"]

    def ask_password(self, question: str) -> Optional[str]:
        """
        Ask user for a password/secret (input hidden, blocks until user responds).

        Args:
            question: Question to ask

        Returns:
            User's input text, or None if empty

        Raises:
            KeyboardInterrupt: If user presses Escape to cancel

        Example:
            passphrase = ctx.textual.ask_password("Enter GPG passphrase:")
        """
        result_event = threading.Event()
        result_container = {"value": None, "cancelled": False}

        def _mount_input():
            def on_submitted(value: str):
                result_container["value"] = value
                result_container["cancelled"] = False
                self._append_text_no_truncate("  → ••••••••")
                input_widget.remove()
                result_event.set()

            def on_cancelled():
                result_container["value"] = None
                result_container["cancelled"] = True
                self.output_widget.append_output("  [dim](cancelled)[/dim]")
                input_widget.remove()
                result_event.set()

            input_widget = PromptInput(
                question=question,
                default="",
                placeholder="Type passphrase and press Enter... (Esc to cancel)",
                on_submit=on_submitted,
                on_cancel=on_cancelled,
                password=True,
            )
            self.output_widget.mount(input_widget)

        try:
            self.app.call_from_thread(_mount_input)
        except Exception:
            return None

        while not result_event.is_set():
            if result_event.wait(timeout=0.5):
                break
            if not self.app.is_running:
                return None

        if result_container.get("cancelled", False):
            raise KeyboardInterrupt("User cancelled input")

        return result_container["value"]

    def ask_multiline(self, question: str, default: str = "") -> Optional[str]:
        """
        Ask user for multiline text input (blocks until user responds).

        Args:
            question: Question to ask
            default: Default value

        Returns:
            User's multiline input text, or None if empty (or if cancelled)

        Raises:
            KeyboardInterrupt: If user presses Escape to cancel

        Example:
            body = ctx.textual.ask_multiline("Enter issue description:", default="")
        """
        # Event and result container for synchronization
        result_event = threading.Event()
        result_container = {"value": None, "cancelled": False}

        def _mount_textarea():
            # Handler when Ctrl+D is pressed
            def on_submitted(value: str):
                result_container["value"] = value
                result_container["cancelled"] = False

                # Show confirmation with full text (first line only for multiline)
                if '\n' in value:
                    preview = value.split('\n')[0]  # Show first line for multiline
                else:
                    preview = value  # Show full text for single line

                self._append_text_no_truncate(f"  → {preview}")

                # Remove the textarea widget
                textarea_widget.remove()

                # Unblock the step
                result_event.set()

            # Handler when Escape is pressed
            def on_cancelled():
                result_container["value"] = None
                result_container["cancelled"] = True

                # Show cancellation message
                self.output_widget.append_output("  [dim](cancelled)[/dim]")

                # Remove the textarea widget
                textarea_widget.remove()

                # Unblock the step
                result_event.set()

            # Create PromptTextArea widget that handles the submission
            textarea_widget = PromptTextArea(
                question=question,
                default=default,
                on_submit=on_submitted,
                on_cancel=on_cancelled
            )

            # Mount the widget (it will auto-focus)
            self.output_widget.mount(textarea_widget)

        # Call from thread since executor runs in background thread
        try:
            self.app.call_from_thread(_mount_textarea)
        except Exception:
            # App is closing or worker was cancelled
            return default

        # BLOCK here until user responds (with timeout to allow cancellation)
        # Wait in loop with timeout so we can be interrupted
        while not result_event.is_set():
            if result_event.wait(timeout=0.5):
                break
            # Check if app is still running
            if not self.app.is_running:
                return default

        # Check if user cancelled
        if result_container.get("cancelled", False):
            raise KeyboardInterrupt("User cancelled multiline input")

        return result_container["value"]

    def ask_confirm(self, question: str, default: bool = True) -> bool:
        """
        Ask user for confirmation using Yes/No buttons.

        Args:
            question: Question to ask
            default: Default value (True = Yes, False = No)

        Returns:
            True if user confirmed, False otherwise

        Example:
            if ctx.textual.ask_confirm("Use AI message?", default=True):
                # User said yes
        """
        result_event = threading.Event()
        result_container = {}

        options = [
            ChoiceOption(value=True, label="Yes", variant="primary" if default else "default"),
            ChoiceOption(value=False, label="No", variant="default" if default else "primary"),
        ]

        def _mount():
            choice_widget_ref = []
            target = self._active_step_container or self.output_widget

            def on_selected(value: bool):
                # Called from UI thread (button press event)
                # Replace PromptChoice with DecisionBadge
                widget = choice_widget_ref[0]
                label = "✓ Yes" if value else "✗ No"
                variant = "success" if value else "warning"
                badge = DecisionBadge(label, variant=variant)
                widget.remove()
                target.mount(badge)
                result_container["value"] = value
                result_event.set()

            widget = PromptChoice(
                question=question,
                options=options,
                on_select=on_selected,
            )
            choice_widget_ref.append(widget)
            target.mount(widget)

        try:
            self.app.call_from_thread(_mount)
        except Exception:
            return default

        while not result_event.is_set():
            if result_event.wait(timeout=0.5):
                break
            if not self.app.is_running:
                return default

        return result_container.get("value", default)

    def ask_choice(self, question: str, options: List[ChoiceOption]) -> Optional[Any]:
        """
        Ask user to select one option from multiple choices using buttons.

        Args:
            question: Question to display above the buttons
            options: List of ChoiceOption instances

        Returns:
            The selected option's value, or None if app closes

        Example:
            choice = ctx.textual.ask_choice(
                "What would you like to do?",
                options=[
                    ChoiceOption(value="send", label="Send", variant="primary"),
                    ChoiceOption(value="edit", label="Edit", variant="default"),
                    ChoiceOption(value="skip", label="Skip", variant="error"),
                ]
            )
        """
        result_event = threading.Event()
        result_container = {}

        def _mount():
            choice_widget_ref = []
            target = self._active_step_container or self.output_widget

            def on_selected(value):
                widget = choice_widget_ref[0]
                selected = next((o for o in options if o.value == value), None)
                label = f"→ {selected.label}" if selected else f"→ {value}"
                badge = DecisionBadge(label)
                widget.remove()
                target.mount(badge)
                result_container["value"] = value
                result_event.set()

            widget = PromptChoice(
                question=question,
                options=options,
                on_select=on_selected,
            )
            choice_widget_ref.append(widget)
            target.mount(widget)

        try:
            self.app.call_from_thread(_mount)
        except Exception:
            return None

        while not result_event.is_set():
            if result_event.wait(timeout=0.5):
                break
            if not self.app.is_running:
                return None

        return result_container.get("value")

    def ask_multiselect(
        self,
        question: str,
        options: List[SelectionOption],
    ) -> List[Any]:
        """
        Ask user to select multiple options from a list using checkboxes.

        Args:
            question: Question to display
            options: List of SelectionOption instances

        Returns:
            List of selected values (the 'value' field from SelectionOption)

        Example:
            from titan_cli.ui.tui.widgets import SelectionOption

            options = [
                SelectionOption(value="option1", label="First Option", selected=True),
                SelectionOption(value="option2", label="Second Option", selected=True),
                SelectionOption(value="option3", label="Third Option", selected=False),
            ]

            selected = ctx.textual.ask_multiselect(
                "Select options to include:",
                options
            )
            # selected might be ["option1", "option2"] if user didn't change anything
        """
        result_container = {"result": None, "ready": threading.Event()}

        def on_submit(selected_values: List[Any]):
            result_container["result"] = selected_values
            result_container["ready"].set()

        # Create and mount the selection widget
        selection_widget = PromptSelectionList(
            question=question,
            options=options,
            on_submit=on_submit
        )

        self.mount(selection_widget)

        # Wait for user to submit. The app-exit check is what lets this thread die when
        # the user quits mid-prompt: this thread is a non-daemon executor thread that the
        # interpreter joins at exit, so a wait with no escape hangs the console after the
        # TUI is gone. (A KeyboardInterrupt handler would not help here - SIGINT is only
        # ever delivered to the main thread, never to this one.)
        while not result_container["ready"].wait(timeout=0.5):
            if not self.app.is_running:
                return []

        # Remove the widget
        def _remove():
            try:
                selection_widget.remove()
            except Exception:
                pass

        try:
            self.app.call_from_thread(_remove)
        except Exception:
            pass

        return result_container["result"]

    def ask_option(
        self,
        question: str,
        options: List[OptionItem],
    ) -> Any:
        """
        Ask user to select one option from a list with title and description.

        Similar to workflow selection - displays a scrollable list with
        bold titles and dim descriptions.

        Args:
            question: Question to display
            options: List of OptionItem instances

        Returns:
            The selected value (the 'value' field from OptionItem)

        Example:
            from titan_cli.ui.tui.widgets import OptionItem

            options = [
                OptionItem(
                    value=123,
                    title="#123: Fix bug in login",
                    description="Branch: fix/login → main"
                ),
                OptionItem(
                    value=124,
                    title="#124: Add feature",
                    description="Branch: feat/new → main"
                ),
            ]

            selected = ctx.textual.ask_option(
                "Select a PR to review:",
                options
            )
            # selected might be 123 or 124
        """
        result_container = {"result": None, "ready": threading.Event()}

        def on_select(selected_value: Any):
            result_container["result"] = selected_value
            result_container["ready"].set()

        # Create and mount the option list widget
        option_widget = PromptOptionList(
            question=question,
            options=options,
            on_select=on_select
        )

        self.mount(option_widget)

        # Wait for user to select. Same app-exit escape as every other ask_* method: this
        # runs on a non-daemon executor thread that the interpreter joins at exit, so a
        # wait with no escape hangs the console after the TUI is gone. (KeyboardInterrupt
        # cannot unblock it - SIGINT is only ever delivered to the main thread.)
        while not result_container["ready"].wait(timeout=0.5):
            if not self.app.is_running:
                return None

        # Remove the widget
        def _remove():
            try:
                option_widget.remove()
            except Exception:
                pass

        try:
            self.app.call_from_thread(_remove)
        except Exception:
            pass

        return result_container["result"]

    @contextmanager
    def loading(self, message: str = "Loading..."):
        """
        Show a loading indicator with a message (context manager).

        Args:
            message: Message to display while loading

        Example:
            with ctx.textual.loading("Generating commit message..."):
                response = ctx.ai.generate(messages)
        """
        # Create loading container with message and spinner
        loading_container = Container(
            Static(f"[dim]{message}[/dim]"),
            LoadingIndicator()
        )
        loading_container.styles.height = "auto"

        # Mount the loading widget
        self.mount(loading_container)

        try:
            yield
        finally:
            # Remove loading widget when done
            def _remove():
                try:
                    loading_container.remove()
                except Exception:
                    pass

            try:
                self.app.call_from_thread(_remove)
            except Exception:
                # App is closing or worker was cancelled
                pass

    def launch_external_cli(self, cli_name: str, prompt: str = None, cwd: str = None) -> int:
        """
        Launch an external CLI tool, suspending the TUI while it runs.

        Args:
            cli_name: Name of the CLI to launch (e.g., "claude", "gemini")
            prompt: Optional initial prompt to pass to the CLI
            cwd: Working directory (default: current)

        Returns:
            Exit code from the CLI tool

        Example:
            exit_code = ctx.textual.launch_external_cli("claude", prompt="Fix this bug")
        """
        from titan_cli.external_cli.launcher import CLILauncher
        from titan_cli.external_cli.configs import CLI_REGISTRY

        # Container for result (since we need to pass it from main thread back to worker)
        result_container = {"exit_code": None}
        result_event = threading.Event()

        def _launch():
            # Suspend TUI, launch CLI, restore TUI
            with self.app.suspend():
                # Get CLI configuration for proper flag usage
                config = CLI_REGISTRY.get(cli_name, {})
                launcher = CLILauncher(
                    cli_name,
                    install_instructions=config.get("install_instructions"),
                    prompt_flag=config.get("prompt_flag"),
                    model_flag=config.get("model_flag")
                )
                exit_code = launcher.launch(prompt=prompt, cwd=cwd)
                result_container["exit_code"] = exit_code

            # Signal completion
            result_event.set()

        # Run in main thread (because suspend() must run on main thread)
        try:
            self.app.call_from_thread(_launch)
        except Exception:
            # App is closing or worker was cancelled
            return -1

        # Wait for completion (with timeout to allow cancellation)
        while not result_event.is_set():
            if result_event.wait(timeout=0.5):
                break
            # Check if app is still running
            if not self.app.is_running:
                return -1

        return result_container["exit_code"]

    def _content_review_options_flow(
        self,
        combined_content: str,
        edit_instruction: str,
        confirm_question: str,
        choice_question: str,
        parse_fn=None,
        preview_fn=None,
    ) -> tuple[str, Optional[str]]:
        """
        Internal helper for Use/Edit/Reject options flow.

        Handles the common logic of presenting options and managing the edit loop.
        Can be customized via parse_fn and preview_fn for different content types.

        Args:
            combined_content: The full content to edit (e.g., "title\n\nbody" or just document)
            edit_instruction: Instruction shown when editing
            confirm_question: Question to confirm after editing
            choice_question: Question for Use/Edit/Reject choice
            parse_fn: Optional function to parse edited content (default: identity)
            preview_fn: Optional function to preview content after editing (default: markdown)

        Returns:
            Tuple of (choice, final_content):
                - choice: "use", "edit", or "reject"
                - final_content: The final content (original or edited), or None if rejected
        """
        # Ask user what to do
        options = [
            ChoiceOption(value="use", label="Use", variant="primary"),
            ChoiceOption(value="edit", label="Edit", variant="default"),
            ChoiceOption(value="reject", label="Reject", variant="error"),
        ]

        choice = self.ask_choice(choice_question, options)

        # Handle rejection
        if choice == "reject":
            return ("reject", None)

        # Store initial value
        final_content = combined_content

        # Handle edit
        if choice == "edit":
            # Edit loop: allow user to edit until they confirm
            while True:
                self.text("")
                self.dim_text(edit_instruction)

                # Ask user to edit
                edited_content = self.ask_multiline(
                    "Edit content:",
                    default=final_content
                )

                if not edited_content or not edited_content.strip():
                    self.warning_text("Content cannot be empty")
                    return ("reject", None)

                # Parse if custom parser provided
                if parse_fn:
                    final_content = parse_fn(edited_content)
                else:
                    final_content = edited_content

                # Show preview if custom preview function provided
                self.text("")
                self.bold_text("Final Preview:")
                self.text("")

                if preview_fn:
                    preview_fn(final_content)
                else:
                    self.markdown(final_content)

                self.text("")

                # Confirm
                confirmed = self.ask_confirm(confirm_question, default=True)

                if confirmed:
                    break
                # If not confirmed, loop back to edit

        return (choice, final_content)

    def ai_content_review_flow(
        self,
        content_title: str,
        content_body: str,
        header_text: str = "AI-Generated Content",
        title_label: str = "Title:",
        description_label: str = "Description:",
        edit_instruction: str = "Edit the content below (first line = title, rest = description)",
        confirm_question: str = "Use this content?",
        choice_question: str = "What would you like to do?",
    ) -> tuple[str, Optional[str], Optional[str]]:
        """
        Generic flow for reviewing AI-generated content with Use/Edit/Reject options.

        This method provides a consistent UX for reviewing AI-generated content across
        different workflows (PR, Issue, etc.). It shows a preview, offers 3 options
        (Use/Edit/Reject), and handles the edit loop.

        Args:
            title: Not used currently, kept for backwards compatibility
            content_title: The AI-generated title/subject line
            content_body: The AI-generated body/description
            header_text: Header to show above the preview (default: "AI-Generated Content")
            title_label: Label for the title field (default: "Title:")
            description_label: Label for the body field (default: "Description:")
            edit_instruction: Instruction text shown when editing (default: generic)
            confirm_question: Question to ask after editing (default: "Use this content?")
            choice_question: Question for the Use/Edit/Reject choice (default: generic)

        Returns:
            Tuple of (choice, final_title, final_body):
                - choice: "use", "edit", or "reject"
                - final_title: The final title (original or edited), or None if rejected
                - final_body: The final body (original or edited), or None if rejected

        Raises:
            KeyboardInterrupt: If user cancels the operation

        Example:
            choice, title, body = ctx.textual.ai_content_review_flow(
                content_title="feat: Add dark mode support",
                content_body="## Summary\\n- Implemented theme switcher...",
                header_text="AI-Generated PR",
                title_label="PR Title:",
                description_label="PR Description:"
            )

            if choice == "reject":
                return Skip("User rejected AI content")
            elif choice in ("use", "edit"):
                ctx.set("pr_title", title)
                ctx.set("pr_body", body)
        """
        # Show preview header
        self.text("")  # spacing
        self.bold_text(header_text)
        self.text("")  # spacing

        # Show title
        self.bold_text(title_label)
        self.primary_text(f"  {content_title}")

        # Warn if title is too long
        number_of_characters = 72
        if len(content_title) > number_of_characters:
            self.warning_text(f"⚠ Title is {len(content_title)} characters (recommended: ≤ {number_of_characters})")

        self.text("")  # spacing

        # Show description
        self.bold_text(description_label)
        self.markdown(content_body)

        self.text("")  # spacing

        # Combine title and body for editing
        combined_content = f"{content_title}\n\n{content_body}"

        # Parse function: split first line as title, rest as body
        def parse_title_body(edited: str) -> str:
            return edited  # Return as-is, will be split later

        # Preview function: show title and body separately with markdown
        def preview_title_body(content: str):
            lines = content.strip().split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""

            self.bold_text(title_label)
            self.primary_text(f"  {title}")
            self.text("")
            self.bold_text(description_label)
            self.markdown(body)

        # Use common options flow
        choice, final_content = self._content_review_options_flow(
            combined_content=combined_content,
            edit_instruction=edit_instruction,
            confirm_question=confirm_question,
            choice_question=choice_question,
            parse_fn=parse_title_body,
            preview_fn=preview_title_body,
        )

        # Handle result
        if choice == "reject":
            return ("reject", None, None)

        # Split final content into title and body
        lines = final_content.strip().split("\n", 1)
        final_title = lines[0].strip()
        final_body = lines[1].strip() if len(lines) > 1 else ""

        return (choice, final_title, final_body)

    def ai_document_review_flow(
        self,
        document_title: str,
        document_content: str,
        header_text: str = "AI-Generated Document",
        title_label: str = "Document:",
        edit_instruction: str = "Edit the document below:",
        confirm_question: str = "Use this document?",
        choice_question: str = "What would you like to do with the document?",
    ) -> tuple[str, Optional[str]]:
        """
        Flow for reviewing AI-generated long-form documents with Use/Edit/Reject options.

        Similar to ai_content_review_flow but designed for single long documents
        (like release notes, reports, etc.) rather than title+description pairs.
        Uses panel() to preserve line breaks instead of markdown() which collapses them.

        Args:
            document_title: Title/label for the document (e.g., "Release Notes v26.8")
            document_content: The full document content
            header_text: Header to show above the preview (default: "AI-Generated Document")
            title_label: Label for the document title (default: "Document:")
            edit_instruction: Instruction shown when editing (default: generic)
            confirm_question: Question to confirm after editing (default: "Use this document?")
            choice_question: Question for Use/Edit/Reject choice (default: generic)

        Returns:
            Tuple of (choice, final_content):
                - choice: "use", "edit", or "reject"
                - final_content: The final document content (original or edited), or None if rejected

        Raises:
            KeyboardInterrupt: If user cancels the operation

        Example:
            choice, content = ctx.textual.ai_document_review_flow(
                document_title="Release Notes v26.8",
                document_content="# 26.8\\n\\n## Features\\n- ...",
                header_text="📋 AI-Generated Release Notes",
                title_label="Version:"
            )

            if choice == "reject":
                return Error("User rejected release notes")
            elif choice in ("use", "edit"):
                ctx.set("release_notes", content)
        """
        # Show preview header
        self.text("")  # spacing
        self.bold_text(header_text)
        self.text("")  # spacing

        # Show title
        self.bold_text(title_label)
        self.primary_text(f"  {document_title}")
        self.text("")  # spacing

        # Show content using panel (preserves line breaks)
        self.panel(document_content, panel_type="info", show_icon=False)
        self.text("")  # spacing

        # Preview function: show content in panel
        def preview_document(content: str):
            self.panel(content, panel_type="info", show_icon=False)

        # Use common options flow
        choice, final_content = self._content_review_options_flow(
            combined_content=document_content,
            edit_instruction=edit_instruction,
            confirm_question=confirm_question,
            choice_question=choice_question,
            parse_fn=None,  # No parsing needed, use content as-is
            preview_fn=preview_document,
        )

        return (choice, final_content)
