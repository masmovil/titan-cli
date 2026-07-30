"""
Workflows Screen

Screen for listing and executing workflows.
"""
from typing import List

from textual.app import ComposeResult
from textual.widgets import Static, OptionList
from textual.widgets.option_list import Option, OptionDoesNotExist
from textual.containers import Container
from textual.containers import Horizontal
from textual.css.query import NoMatches

from titan_cli.core.workflows.workflow_filter_service import WorkflowFilterService
from titan_cli.core.workflows.workflow_sources import WorkflowInfo
from titan_cli.ui.tui.screens.workflow_execution import WorkflowExecutionScreen
from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import StyledOption
from .base import BaseScreen

class WorkflowsScreen(BaseScreen):
    """
    Workflows screen for selecting and executing workflows.

    Lists all available workflows and allows the user to:
    - View workflow details
    - Execute workflows
    - Go back to main menu
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("q", "go_back", "Back"),
        ("left", "focus_plugins", "Plugins"),
        ("right", "focus_workflows", "Workflows"),
        ("tab", "focus_next", "Next Panel"),
    ]

    def __init__(self, config):
        super().__init__(config, title="⚡ Available Workflows", show_back=True)
        self.selected_plugin = "all"  # Track selected plugin filter (start with "all")
        self._is_mounting = False  # Flag to prevent auto-update during mount
        self._all_workflows = None  # Cache for discovered workflows
        self._plugin_source_map = {}  # Map plugin names to their source identifiers
        self._favorite_names = set()  # Cache of favorited workflow names

    def on_mount(self) -> None:
        """Initialize the screen with first options highlighted."""
        self._is_mounting = True

        try:
            # Highlight first plugin option
            plugin_list = self.query_one("#plugin-list", OptionList)
            if len(plugin_list._options) > 0:
                plugin_list.highlighted = 0

            # Highlight first workflow option
            workflow_list = self.query_one("#workflow-list", OptionList)
            if len(workflow_list._options) > 0:
                workflow_list.highlighted = 0
        except (NoMatches, AttributeError):
            pass
        finally:
            # Re-enable auto-filtering after mount completes
            self._is_mounting = False

    def refresh_favorites(self) -> None:
        """Re-sort and re-render the workflow list to reflect updated favorite state.

        Called directly by WorkflowExecutionScreen right after a favorite is
        toggled, rather than via a screen lifecycle hook - this keeps the
        refresh scoped to the one moment it's actually needed instead of
        running on every screen transition.
        """
        if self._all_workflows is None:
            return
        self._favorite_names = set(self.config.get_favorite_workflows())
        self._all_workflows = WorkflowFilterService.sort_favorites_first(
            self._all_workflows, self._favorite_names
        )
        self._plugin_source_map = WorkflowFilterService.group_by_plugin(self._all_workflows)
        self._update_workflow_list()

    CSS = """
    WorkflowsScreen {
        align: center middle;
    }

    #workflows-container {
        width: 100%;
        height: 1fr;
        background: $surface-lighten-1;
    }

    #workflows-container Horizontal {
        width: 100%;
        height: 1fr;
        padding: 1;
    }

    #left-panel {
        width: 20%;
        height: 100%;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
    }

    #left-panel OptionList {
        height: 100%;
        width: 100%;
        padding: 1 0;
        margin: 0;
    }

    #right-panel {
        width: 80%;
        height: 100%;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
    }

    #right-panel OptionList {
        height: 100%;
        width: 100%;
        padding: 1 0;
        margin: 0;
    }

    OptionList > .option-list--option {
        padding: 1;
    }
    """

    def compose_content(self) -> ComposeResult:
        """
        Compose the workflows screen content.

        Creates a two-panel layout:
        - Left panel (20%): Plugin filter list
        - Right panel (80%): Workflows list (filtered by selected plugin)
        """
        all_workflows = self.config.workflows.discover()

        # Cache and remove duplicates using service
        self._all_workflows = WorkflowFilterService.remove_duplicates(all_workflows)

        # Favorited workflows always sort to the top
        self._favorite_names = set(self.config.get_favorite_workflows())
        self._all_workflows = WorkflowFilterService.sort_favorites_first(
            self._all_workflows, self._favorite_names
        )

        with Container(id="workflows-container"):
            if not self._all_workflows:
                yield Static("No workflows found.", id="no-workflows")
            else:
                # Group workflows by plugin using service
                self._plugin_source_map = WorkflowFilterService.group_by_plugin(self._all_workflows)
                plugin_names = WorkflowFilterService.get_unique_plugin_names(self._all_workflows)

                # Build plugin filter options
                plugin_options = [Option(f"{Icons.PACKAGE} All Plugins", id="all")]
                for plugin_name in sorted(plugin_names):
                    plugin_options.append(Option(f"{Icons.PLUGIN} {plugin_name}", id=plugin_name))

                # Build workflow options (initially show all)
                workflow_options = self._build_workflow_options(self._all_workflows)

                with Horizontal():
                    left_panel = Container(id="left-panel")
                    left_panel.border_title = "Plugins"
                    with left_panel:
                        yield OptionList(*plugin_options, id="plugin-list")

                    right_panel = Container(id="right-panel")
                    right_panel.border_title = "Workflows"
                    with right_panel:
                        yield OptionList(*workflow_options, id="workflow-list")

    def _build_workflow_options(self, workflows: List[WorkflowInfo], selected_plugin: str = None) -> List[Option]:
        """Build workflow options, optionally filtered by plugin."""
        options = []

        # Get workflows for selected plugin
        if selected_plugin and selected_plugin != "all":
            # Use the pre-mapped workflows for this plugin
            workflows_to_show = self._plugin_source_map.get(selected_plugin, [])
        else:
            # Show all workflows
            workflows_to_show = workflows

        for wf_info in workflows_to_show:
            display_title = wf_info.title if wf_info.title else wf_info.name.capitalize()
            if wf_info.name in self._favorite_names:
                display_title = f"{Icons.STAR} {display_title}"
            styled_opt = StyledOption(
                id=wf_info.name,
                title=display_title,
                description=wf_info.description
            )
            # Convert StyledOption to Option with markup
            prompt = f"[bold]{styled_opt.title}[/bold]\n[dim]{styled_opt.description}[/dim]"
            options.append(Option(prompt, id=styled_opt.id))

        return options if options else [Option("No workflows found", id="none", disabled=True)]

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Handle plugin navigation - auto-filter when highlighting."""
        # Ignore during mount to prevent duplicate updates
        if self._is_mounting:
            return

        if event.option_list.id == "plugin-list":
            # Only update if plugin actually changed to avoid duplicate updates
            if self.selected_plugin != event.option.id:
                self.selected_plugin = event.option.id
                self._update_workflow_list()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle workflow selection (Enter key)."""
        if event.option_list.id == "workflow-list":
            # Workflow selected - execute it
            workflow_name = event.option.id
            if workflow_name != "none":  # Don't execute disabled placeholder
                self.execute_workflow(workflow_name)

    def _update_workflow_list(self) -> None:
        """Update the workflow list based on selected plugin filter."""
        # Use cached workflows instead of discovering again
        workflow_options = self._build_workflow_options(self._all_workflows, self.selected_plugin)

        # Get the workflow list widget and replace its options
        workflow_list = self.query_one("#workflow-list", OptionList)

        # Preserve the highlighted item (by id) across the rebuild so toggling
        # a favorite doesn't reset the user's cursor position
        highlighted_id = None
        if workflow_list.highlighted is not None:
            highlighted_option = workflow_list.get_option_at_index(workflow_list.highlighted)
            highlighted_id = highlighted_option.id

        # Clear and add in one operation
        workflow_list.clear_options()
        workflow_list.add_options(workflow_options)

        if highlighted_id is not None:
            try:
                workflow_list.highlighted = workflow_list.get_option_index(highlighted_id)
            except OptionDoesNotExist:
                pass

        # Force refresh to update display
        workflow_list.refresh()

    def execute_workflow(self, workflow_name: str) -> None:
        """
        Execute a workflow.

        Args:
            workflow_name: Name of the workflow to execute
        """

        # Navigate to workflow execution screen
        execution_screen = WorkflowExecutionScreen(self.config, workflow_name)
        self.app.push_screen(execution_screen)

    def action_go_back(self) -> None:
        """Go back to main menu."""
        self.app.pop_screen()

    def action_focus_plugins(self) -> None:
        """Focus on the plugins panel."""
        try:
            plugin_list = self.query_one("#plugin-list", OptionList)
            plugin_list.focus()
        except NoMatches:
            pass

    def action_focus_workflows(self) -> None:
        """Focus on the workflows panel."""
        try:
            workflow_list = self.query_one("#workflow-list", OptionList)
            workflow_list.focus()
            # Ensure first item is highlighted if nothing is selected
            if workflow_list.highlighted is None and len(workflow_list._options) > 0:
                workflow_list.highlighted = 0
        except NoMatches:
            pass
