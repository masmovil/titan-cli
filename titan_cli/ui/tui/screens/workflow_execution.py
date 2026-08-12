"""
Workflow Execution Screen

Screen for executing workflows and displaying progress in real-time.
"""
import os
from typing import Any, List, Optional, Dict

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Container, Horizontal, VerticalScroll
from textual.worker import Worker, WorkerState

from titan_cli.ui.tui.widgets import HeaderWidget
from titan_cli.ui.tui.icons import Icons

from titan_cli.core.interrupt import (
    WorkflowAborted,
    clear_abort_check,
    set_abort_check,
)
from titan_cli.core.secrets import SecretManager
from titan_cli.core.workflows import ParsedWorkflow
from titan_cli.engine.builder import WorkflowContextBuilder
from titan_cli.core.workflows.workflow_exceptions import (
    WorkflowNotFoundError,
    WorkflowExecutionError,
)
from titan_cli.ui.tui.textual_workflow_executor import TextualWorkflowExecutor
from titan_cli.ui.tui.widgets.text import DimText
from titan_cli.core.logging import get_logger
from .base import BaseScreen

logger = get_logger(__name__)

class WorkflowExecutionScreen(BaseScreen):
    """
    Screen for executing a workflow with real-time progress display.

    The internal structure (progress tracking, output handling, etc.)
    will be implemented separately.
    """

    BINDINGS = [
        ("escape", "cancel_execution", "Cancel"),
        ("q", "cancel_execution", "Cancel"),
        ("f", "toggle_favorite", "Favorite"),
    ]

    CSS = """
    WorkflowExecutionScreen {
        align: center middle;
    }

    #workflow-description {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    #execution-container {
        width: 100%;
        height: 1fr;
        background: $surface-lighten-1;
        padding: 0 2 1 2;
    }

    #steps-panel {
        width: 20%;
        height: 100%;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
    }

    #steps-content {
        padding: 1;
    }

    #workflow-execution-panel {
        width: 80%;
        height: 100%;
        border: round $primary;
        border-title-align: center;
        background: $surface-lighten-1;
        padding: 0;
    }

    #execution-content {
        padding: 1;
    }
    """

    def __init__(self, config, workflow_name: str, **kwargs):
        super().__init__(
            config,
            title=f"{Icons.WORKFLOW} Executing: {workflow_name}",
            show_back=True,
            show_favorite=True,
            is_favorite=config.is_favorite_workflow(workflow_name),
            **kwargs
        )
        self.workflow_name = workflow_name
        self.workflow: Optional[ParsedWorkflow] = None
        self._worker: Optional[Worker] = None
        self._original_cwd = os.getcwd()
        self._should_auto_back = False  # Flag to trigger auto-back when worker finishes

    def compose_content(self) -> ComposeResult:
        """Compose the workflow execution screen."""
        with Container(id="execution-container"):
            yield DimText(id="workflow-description")
            with Horizontal():
                    left_panel = VerticalScroll(id="steps-panel")
                    left_panel.border_title = "Steps"
                    with left_panel:
                        yield StepsContent(id="steps-content")

                    right_panel = VerticalScroll(id="workflow-execution-panel")
                    right_panel.border_title = "Workflow Execution"
                    with right_panel:
                        yield WorkflowExecutionContent(id="execution-content")            
                
    def on_mount(self) -> None:
        """Start workflow execution when screen is mounted."""
        self._load_and_execute_workflow()

    def _load_and_execute_workflow(self) -> None:
        """Load and execute the workflow."""
        try:
            # Load workflow
            self.workflow = self.config.workflows.get_workflow(self.workflow_name)
            if not self.workflow:
                logger.error("workflow_not_found", workflow_name=self.workflow_name)
                self._output(f"[red]{Icons.ERROR} Workflow '{self.workflow_name}' not found.[/red]")
                self._output("[dim]Press ESC or Q to return[/dim]")
                return

            self._update_header_title(f"{Icons.WORKFLOW} {self.workflow.name}")
            self._update_description(self.workflow.description or "")

            # Create step widgets for non-hook steps
            steps_widget = self.query_one("#steps-content", StepsContent)
            steps_widget.set_steps(self.workflow.steps)

            self._output("Preparing to execute workflow...")

            # Execute workflow in background thread (not async worker)
            self._worker = self.run_worker(
                self._execute_workflow,
                name="workflow_executor",
                thread=True
            )

        except (WorkflowNotFoundError, WorkflowExecutionError) as e:
            self._output(f"[red]{Icons.ERROR} Error loading workflow: {e}[/red]")
            self._output("[dim]Press ESC or Q to return[/dim]")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.exception("workflow_load_unexpected_error", workflow_name=self.workflow_name, error=str(e))
            self._output(f"[red]{Icons.ERROR} Unexpected error loading workflow:[/red]")
            self._output(f"[red]{type(e).__name__}: {e}[/red]")
            self._output(f"[dim]{error_details}[/dim]")
            self._output("[dim]Press ESC or Q to return[/dim]")

    def _execute_workflow(self) -> None:
        """Execute the workflow in a background thread."""
        # Let blocking calls made from this thread (AI requests, headless CLI
        # subprocesses) notice when the app closes, so quitting mid-call doesn't
        # leave this non-daemon thread hanging interpreter shutdown.
        app = self.app
        set_abort_check(lambda: not app.is_running)
        try:
            # We're already in the project directory (current working directory)
            # No need to change directory

            # Create secret manager for current project
            from pathlib import Path
            secrets = SecretManager(project_path=Path.cwd())

            # Build workflow context (without UI - executor handles messaging)
            ctx_builder = WorkflowContextBuilder(
                plugin_registry=self.config.registry,
                secrets=secrets,
                ai_config=self.config.config.ai,
            )

            # Add AI if configured
            ctx_builder.with_ai()
            ctx_builder.with_ai_router()
            ctx_builder.with_titan_config(self.config)

            # Add registered plugins to context
            for plugin_name in self.config.registry.list_installed():
                plugin = self.config.registry.get_plugin(plugin_name)
                if not plugin:
                    continue

                if hasattr(ctx_builder, f"with_{plugin_name}"):
                    try:
                        client = plugin.get_client()
                        getattr(ctx_builder, f"with_{plugin_name}")(client)
                    except Exception:
                        # Plugin client initialization failed - workflow steps
                        # using this plugin will fail gracefully
                        pass

                try:
                    managers = plugin.get_workflow_managers(project_root=secrets.project_path)
                    if managers is not None:
                        ctx_builder.with_plugin_managers(plugin_name, managers)
                except Exception:
                    pass

            # Build context and create executor
            execution_context = ctx_builder.build()
            if secrets.project_path:
                execution_context.data["project_root"] = str(secrets.project_path)
            executor = TextualWorkflowExecutor(
                plugin_registry=self.config.registry,
                workflow_registry=self.config.workflows,
                message_target=self  # Pass self to receive messages
            )

            # Execute workflow (this is synchronous and may take time)
            executor.execute(self.workflow, execution_context)

        except WorkflowAborted:
            # The app closed while a step was blocked in an AI call or prompt.
            # There is no UI left to report to; just let this thread die.
            logger.info("workflow_aborted_on_app_exit", workflow_name=self.workflow_name)
        except (WorkflowNotFoundError, WorkflowExecutionError) as e:
            self._output(f"\n[red]{Icons.ERROR} Workflow failed: {e}[/red]")
            self._output("[dim]Press ESC or Q to return[/dim]")
        except Exception as e:
            self._output(f"\n[red]{Icons.ERROR} Unexpected error: {type(e).__name__}: {e}[/red]")
            self._output("[dim]Press ESC or Q to return[/dim]")
        finally:
            clear_abort_check()
            # Restore original working directory
            os.chdir(self._original_cwd)

    def _update_header_title(self, title: str) -> None:
        """Update the header title."""
        try:
            header = self.query_one(HeaderWidget)
            header.title = title
        except Exception:
            pass

    def action_toggle_favorite(self) -> None:
        """Toggle favorite status for this workflow and update the header."""
        try:
            new_state = self.config.toggle_favorite_workflow(self.workflow_name)
        except Exception as exc:
            self.notify(f"Could not save favorite: {exc}", severity="error")
            return

        self.is_favorite = new_state
        try:
            header = self.query_one(HeaderWidget)
            header.is_favorite = new_state
        except Exception:
            pass

        # Local import avoids a circular import (workflows.py imports this module).
        from titan_cli.ui.tui.screens.workflows import WorkflowsScreen

        for screen in self.app.screen_stack:
            if isinstance(screen, WorkflowsScreen):
                screen.refresh_favorites()

    def _update_description(self, description: str) -> None:
        """Update the workflow description."""
        try:
            header = self.query_one("#workflow-description", DimText)
            header.update(description)
        except Exception:
            pass

    def _output(self, text: str) -> None:
        """Helper to append output to execution widget."""
        try:
            execution_widget = self.query_one("#execution-content", WorkflowExecutionContent)
            execution_widget.append_output(text)
        except Exception:
            pass

    # Generic message handler for TextualWorkflowExecutor events
    def on_textual_workflow_executor_workflow_started(
        self, message: TextualWorkflowExecutor.WorkflowStarted
    ) -> None:
        """Handle workflow started event."""
        self._handle_workflow_event(message)

    def on_textual_workflow_executor_step_started(
        self, message: TextualWorkflowExecutor.StepStarted
    ) -> None:
        """Handle step started event."""
        self._handle_workflow_event(message)

    def on_textual_workflow_executor_step_completed(
        self, message: TextualWorkflowExecutor.StepCompleted
    ) -> None:
        """Handle step completed event."""
        self._handle_workflow_event(message)

    def on_textual_workflow_executor_step_failed(
        self, message: TextualWorkflowExecutor.StepFailed
    ) -> None:
        """Handle step failed event."""
        self._handle_workflow_event(message)

    def on_textual_workflow_executor_step_skipped(
        self, message: TextualWorkflowExecutor.StepSkipped
    ) -> None:
        """Handle step skipped event."""
        self._handle_workflow_event(message)

    def on_textual_workflow_executor_workflow_completed(
        self, message: TextualWorkflowExecutor.WorkflowCompleted
    ) -> None:
        """Handle workflow completed event."""
        self._handle_workflow_event(message)

    def on_textual_workflow_executor_workflow_failed(
        self, message: TextualWorkflowExecutor.WorkflowFailed
    ) -> None:
        """Handle workflow failed event."""
        self._handle_workflow_event(message)

    def _handle_workflow_event(self, message) -> None:
        """Generic handler that delegates to widgets."""
        try:
            from titan_cli.ui.tui.textual_workflow_executor import TextualWorkflowExecutor

            # Update steps widget for step-related and workflow events
            if hasattr(message, 'step_id') or isinstance(message, (TextualWorkflowExecutor.WorkflowStarted, TextualWorkflowExecutor.WorkflowCompleted)):
                steps_widget = self.query_one("#steps-content", StepsContent)
                steps_widget.handle_event(message)

            # Update execution widget for output
            execution_widget = self.query_one("#execution-content", WorkflowExecutionContent)
            execution_widget.handle_event(message)
        except Exception:
            pass

    def _schedule_auto_back(self) -> None:
        """Schedule auto-back - will poll worker state until it finishes."""
        # import time
        # with open("/tmp/titan_debug.log", "a") as f:
        #     f.write(f"[{time.time():.3f}] SCREEN: Auto-back scheduled, starting polling\n")
        self._should_auto_back = True
        # Start polling worker state
        self._poll_worker_and_pop()

    def _poll_worker_and_pop(self) -> None:
        """Poll worker state and pop screen when finished."""
        # Check if worker is still running
        if self._worker and self._worker.state == WorkerState.RUNNING:
            # with open("/tmp/titan_debug.log", "a") as f:
            #     f.write(f"[{time.time():.3f}] SCREEN: Worker still running, will check again in 0.1s\n")
            # Worker still running, check again in 100ms
            self.set_timer(0.1, self._poll_worker_and_pop)
        else:
            # Worker finished, safe to pop
            # with open("/tmp/titan_debug.log", "a") as f:
            #     f.write(f"[{time.time():.3f}] SCREEN: Worker finished, popping screen now\n")
            self.app.pop_screen()

    def action_cancel_execution(self) -> None:
        """Cancel workflow execution and go back."""
        # Cancel worker if running
        if self._worker and self._worker.state == WorkerState.RUNNING:
            # Try to cancel, but don't wait for it to finish
            # The worker thread may be blocked, so we just move on
            try:
                self._worker.cancel()
            except Exception:
                pass

        # Restore working directory
        try:
            os.chdir(self._original_cwd)
        except Exception:
            pass

        # Pop screen immediately without waiting for worker
        self.app.pop_screen()

class StepsContent(Widget):
    """Widget to display workflow steps and their statuses."""

    DEFAULT_CSS = """
    StepsContent {
        width: 100%;
        height: auto;
        layout: vertical;
    }

    .step-widget {
        width: 100%;
        height: auto;
        padding: 0 1 1 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.steps: List[Dict[str, Any]] = []
        self._step_widgets: Dict[str, Static] = {}
        self._workflow_stack: List[Dict[str, Any]] = []  # Stack to track nested workflows

    def set_steps(self, steps: List[Dict[str, Any]]) -> None:
        """Set the steps to display."""
        self.steps = steps

        for idx, step_data in enumerate(steps):
            if step_data.get("hook"):
                continue

            step_id = step_data.get("id") or f"step_{idx}"
            step_name = step_data.get("name") or step_id

            step_widget = Static(f"{Icons.PENDING} {step_name}", classes="step-widget")
            self._step_widgets[step_id] = step_widget
            self.mount(step_widget)

    def update_step(self, step_id: str, text: str) -> None:
        """Update a specific step's display."""
        if step_id in self._step_widgets:
            self._step_widgets[step_id].update(text)

    def set_step_running(self, step_id: str, step_name: str) -> None:
        """Mark a step as running."""
        self.update_step(step_id, f"{Icons.RUNNING} [cyan]{step_name}[/cyan]")

    def set_step_success(self, step_id: str, step_name: str) -> None:
        """Mark a step as successful."""
        self.update_step(step_id, f"{Icons.SUCCESS} [green]{step_name}[/green]")

    def set_step_failed(self, step_id: str, step_name: str) -> None:
        """Mark a step as failed."""
        self.update_step(step_id, f"{Icons.ERROR} [red]{step_name}[/red]")

    def set_step_skipped(self, step_id: str, step_name: str) -> None:
        """Mark a step as skipped."""
        self.update_step(step_id, f"{Icons.SKIPPED} [yellow]{step_name}[/yellow]")

    def handle_event(self, message) -> None:
        """Handle workflow events generically."""
        from titan_cli.ui.tui.textual_workflow_executor import TextualWorkflowExecutor

        if isinstance(message, TextualWorkflowExecutor.WorkflowStarted):
            # If it's a nested workflow, save current state and show nested steps
            if message.is_nested:
                # Save current state
                self._workflow_stack.append({
                    'steps': self.steps,
                    'widgets': self._step_widgets.copy()
                })
                # Clear current widgets
                for widget in self._step_widgets.values():
                    widget.remove()
                self._step_widgets.clear()
                # Set nested workflow steps
                self.set_steps(message.steps)

        elif isinstance(message, TextualWorkflowExecutor.WorkflowCompleted):
            # If nested workflow completed, restore parent workflow steps
            if message.is_nested and self._workflow_stack:
                # Clear nested widgets
                for widget in self._step_widgets.values():
                    widget.remove()
                self._step_widgets.clear()

                # Restore parent workflow state
                parent_state = self._workflow_stack.pop()
                self.steps = parent_state['steps']
                self._step_widgets = parent_state['widgets']

                # Re-mount parent widgets
                for widget in self._step_widgets.values():
                    self.mount(widget)

        elif isinstance(message, TextualWorkflowExecutor.StepStarted):
            self.update_step(message.step_id, f"{Icons.RUNNING} [cyan]{message.step_name}[/cyan]")
        elif isinstance(message, TextualWorkflowExecutor.StepCompleted):
            self.update_step(message.step_id, f"{Icons.SUCCESS} [green]{message.step_name}[/green]")
        elif isinstance(message, TextualWorkflowExecutor.StepFailed):
            self.update_step(message.step_id, f"{Icons.ERROR} [red]{message.step_name}[/red]")
        elif isinstance(message, TextualWorkflowExecutor.StepSkipped):
            self.update_step(message.step_id, f"{Icons.SKIPPED} [yellow]{message.step_name}[/yellow]")


class WorkflowExecutionContent(Widget):
    """Widget to display workflow execution output."""

    # Allow children to receive focus (for input widgets)
    can_focus_children = True

    DEFAULT_CSS = """
    WorkflowExecutionContent {
        width: 100%;
        height: auto;
        layout: vertical;
    }

    WorkflowExecutionContent > Static {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._workflow_depth = 0  # Track nested workflow depth

    def compose(self) -> ComposeResult:
        """Compose the execution content."""
        # Don't yield anything - content will be mounted dynamically
        return
        yield  # Make this a generator

    def append_output(self, text: str) -> None:
        """Append text to the output."""
        # Mount each line as a separate Static widget to preserve order
        try:
            text_widget = Static(text)
            self.mount(text_widget)
            # Auto-scroll to show new content
            self._scroll_to_end()
        except Exception:
            pass

    def _scroll_to_end(self) -> None:
        """Scroll the parent container to show the end."""
        try:
            # Get the parent VerticalScroll container
            parent = self.parent
            if parent and hasattr(parent, 'scroll_end'):
                parent.scroll_end(animate=False)
        except Exception:
            pass

    def on_descendant_mount(self, event) -> None:
        """Auto-scroll when step containers are mounted."""
        from titan_cli.ui.tui.widgets import StepContainer

        # ONLY auto-scroll for StepContainers (new steps)
        # Interactive widgets (PromptChoice, PromptInput, etc.) handle their own scroll
        # Passive content (Panel, Markdown, Text) should NOT trigger scroll
        if isinstance(event.widget, StepContainer):
            self._scroll_to_end()

    def handle_event(self, message) -> None:
        """Handle workflow events generically."""
        from titan_cli.ui.tui.textual_workflow_executor import TextualWorkflowExecutor

        if isinstance(message, TextualWorkflowExecutor.WorkflowStarted):
            # Track nested workflow depth
            if message.is_nested:
                self._workflow_depth += 1
            self.append_output(f"\n[bold cyan]🚀 Starting workflow: {message.workflow_name}[/bold cyan]")

        elif isinstance(message, TextualWorkflowExecutor.StepStarted):
            # StepContainer now handles step titles, so we don't display anything here
            pass

        elif isinstance(message, TextualWorkflowExecutor.StepCompleted):
            # StepContainer now handles step completion (green border), so we don't display anything here
            pass

        elif isinstance(message, TextualWorkflowExecutor.StepFailed):
            # Steps handle their own error display via ctx.textual
            # Executor only coordinates execution, no visual output needed
            pass

        elif isinstance(message, TextualWorkflowExecutor.StepSkipped):
            # StepContainer now handles step skips (yellow border), so we don't display the panel
            pass

        elif isinstance(message, TextualWorkflowExecutor.WorkflowCompleted):
            # Track nested workflow depth
            if message.is_nested and self._workflow_depth > 0:
                self._workflow_depth -= 1

            # DEBUG: Log receipt
            # with open("/tmp/titan_debug.log", "a") as f:
            #     f.write(f"[{time.time():.3f}] SCREEN: Received WorkflowCompleted, is_nested={message.is_nested}\n")

            # Show success toast instead of inline message
            try:
                # with open("/tmp/titan_debug.log", "a") as f:
                #     f.write(f"[{time.time():.3f}] SCREEN: About to call notify\n")
                self.app.notify(f"✨ Workflow completed: {message.workflow_name}", severity="information", timeout=5)
                # with open("/tmp/titan_debug.log", "a") as f:
                #     f.write(f"[{time.time():.3f}] SCREEN: notify called successfully\n")
            except Exception:
                # with open("/tmp/titan_debug.log", "a") as f:
                #     f.write(f"[{time.time():.3f}] SCREEN: notify failed: {e}\n")
                # Fallback if notify fails
                self.append_output(f"\n[bold green]✨ Workflow completed: {message.workflow_name}[/bold green]")

            # Schedule auto-back after a short delay (only if not nested)
            if not message.is_nested:
                # with open("/tmp/titan_debug.log", "a") as f:
                #     f.write(f"[{time.time():.3f}] SCREEN: Setting timer for auto-back flag\n")
                # Don't pop immediately - wait for worker to finish, then pop
                self.set_timer(3.0, self._schedule_auto_back)
            else:
                # with open("/tmp/titan_debug.log", "a") as f:
                #     f.write(f"[{time.time():.3f}] SCREEN: Workflow is nested, skipping auto-back\n")
                pass

        elif isinstance(message, TextualWorkflowExecutor.WorkflowFailed):
            # Steps handle their own error display via ctx.textual
            # Just show a simple notification without duplicating the error message
            self.app.notify(f"❌ Workflow failed at step: {message.step_name}", severity="error", timeout=10)
