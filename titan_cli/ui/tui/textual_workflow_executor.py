"""
Textual Workflow Executor

Workflow executor specifically designed for Textual TUI.
Emits Textual messages instead of using Rich UI components.
"""
import time
from typing import Any, Dict, Optional

from textual.message import Message

from titan_cli.core.workflows import ParsedWorkflow
from titan_cli.core.workflows.workflow_exceptions import WorkflowExecutionError
from titan_cli.core.workflows.workflow_registry import WorkflowRegistry
from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import WorkflowResult, Success, Error, is_error, is_skip, is_exit
from titan_cli.engine.steps.command_step import execute_command_step as execute_external_command_step
from titan_cli.engine.steps.ai_assistant_step import execute_ai_assistant_step
from titan_cli.core.logging import get_logger

logger = get_logger(__name__)


class TextualWorkflowExecutor:
    """
    Workflow executor for Textual TUI.

    Instead of using ctx.ui (Rich components), this executor emits
    Textual messages that the screen can listen to and display.
    """

    # Core steps available to all workflows
    CORE_STEPS = {
        "ai_code_assistant": execute_ai_assistant_step,
    }

    # Message classes for communication with the screen
    class WorkflowStarted(Message):
        """Emitted when workflow execution starts."""
        def __init__(self, workflow_name: str, description: Optional[str], source: Optional[str], total_steps: int, steps: list = None, is_nested: bool = False) -> None:
            super().__init__()
            self.workflow_name = workflow_name
            self.description = description
            self.source = source
            self.total_steps = total_steps
            self.steps = steps or []
            self.is_nested = is_nested

    class WorkflowCompleted(Message):
        """Emitted when workflow completes successfully."""
        def __init__(self, workflow_name: str, message: str, is_nested: bool = False) -> None:
            super().__init__()
            self.workflow_name = workflow_name
            self.message = message
            self.is_nested = is_nested

    class WorkflowFailed(Message):
        """Emitted when workflow fails."""
        def __init__(self, workflow_name: str, step_name: str, error_message: str) -> None:
            super().__init__()
            self.workflow_name = workflow_name
            self.step_name = step_name
            self.error_message = error_message

    class StepStarted(Message):
        """Emitted when a step starts executing."""
        def __init__(self, step_index: int, step_id: str, step_name: str) -> None:
            super().__init__()
            self.step_index = step_index
            self.step_id = step_id
            self.step_name = step_name

    class StepCompleted(Message):
        """Emitted when a step completes successfully."""
        def __init__(self, step_index: int, step_id: str, step_name: str) -> None:
            super().__init__()
            self.step_index = step_index
            self.step_id = step_id
            self.step_name = step_name

    class StepFailed(Message):
        """Emitted when a step fails."""
        def __init__(self, step_index: int, step_id: str, step_name: str, error_message: str, on_error: str) -> None:
            super().__init__()
            self.step_index = step_index
            self.step_id = step_id
            self.step_name = step_name
            self.error_message = error_message
            self.on_error = on_error

    class StepSkipped(Message):
        """Emitted when a step is skipped."""
        def __init__(self, step_index: int, step_id: str, step_name: str) -> None:
            super().__init__()
            self.step_index = step_index
            self.step_id = step_id
            self.step_name = step_name

    class StepOutput(Message):
        """Emitted when a step produces output."""
        def __init__(self, step_index: int, step_id: str, output: str) -> None:
            super().__init__()
            self.step_index = step_index
            self.step_id = step_id
            self.output = output

    def __init__(
        self,
        plugin_registry: PluginRegistry,
        workflow_registry: WorkflowRegistry,
        message_target: Any = None
    ):
        """
        Initialize the Textual workflow executor.

        Args:
            plugin_registry: Plugin registry for resolving plugins
            workflow_registry: Workflow registry for resolving workflows
            message_target: Target to post messages to (typically a Textual Widget/Screen)
        """
        self._plugin_registry = plugin_registry
        self._workflow_registry = workflow_registry
        self._message_target = message_target

    def _post_message(self, message: Message) -> None:
        """Post a message to the target if available."""
        if self._message_target and hasattr(self._message_target, 'post_message'):
            self._message_target.post_message(message)

    def _post_message_sync(self, message: Message) -> None:
        """Post a message synchronously (blocks until processed)."""
        if self._message_target and hasattr(self._message_target, 'post_message'):
            def _post():
                self._message_target.post_message(message)

            # Use call_from_thread to block until message is posted
            if hasattr(self._message_target, 'app'):
                try:
                    self._message_target.app.call_from_thread(_post)
                except Exception:
                    # App is closing or worker was cancelled, fail silently
                    pass
            else:
                # Fallback to async post if no app available
                self._message_target.post_message(message)

    def execute(
        self,
        workflow: ParsedWorkflow,
        ctx: WorkflowContext,
        params_override: Optional[Dict[str, Any]] = None
    ) -> WorkflowResult:
        """
        Execute the given ParsedWorkflow.

        Args:
            workflow: The workflow to execute
            ctx: Workflow context
            params_override: Optional parameter overrides

        Returns:
            WorkflowResult indicating success or failure
        """
        # Inject Textual components into context if message_target is available
        if self._message_target and hasattr(self._message_target, 'app'):
            try:
                from titan_cli.ui.tui.textual_components import TextualComponents
                from titan_cli.ui.tui.screens.workflow_execution import WorkflowExecutionContent

                app = self._message_target.app
                output_widget = self._message_target.query_one("#execution-content", WorkflowExecutionContent)

                ctx.textual = TextualComponents(app, output_widget)
            except Exception:
                # If we can't get the components, steps will fall back to ctx.ui
                pass

        # Merge workflow params into ctx.data with optional overrides
        effective_params = {**workflow.params}
        if params_override:
            effective_params.update(params_override)

        # Load params into ctx.data so steps can access them
        ctx.data.update(effective_params)

        # Inject workflow metadata into context
        ctx.workflow_name = workflow.name
        ctx.total_steps = len([s for s in workflow.steps if not s.get("hook")])

        # Check if this is a nested workflow (called from another workflow)
        is_nested = len(ctx._workflow_stack) > 0

        # Log workflow start
        workflow_start_time = time.time()
        logger.info("workflow_started",
            workflow=workflow.name,
            source=workflow.source,
            total_steps=ctx.total_steps,
            is_nested=is_nested
        )

        # Emit workflow started event
        self._post_message(
            self.WorkflowStarted(
                workflow_name=workflow.name,
                description=workflow.description,
                source=workflow.source,
                total_steps=ctx.total_steps,
                steps=workflow.steps,
                is_nested=is_nested
            )
        )

        ctx.enter_workflow(workflow.name)
        try:
            step_index = 0
            for step_data in workflow.steps:
                step_config = WorkflowStepModel(**step_data)

                # Hooks are resolved by the registry, so we just skip the placeholder
                if step_config.hook:
                    continue

                step_index += 1
                ctx.current_step = step_index

                step_id = step_config.id
                step_name = step_config.name or step_id

                # Log step start
                step_start_time = time.time()
                logger.debug("step_started",
                    workflow=workflow.name,
                    step_index=step_index,
                    step_id=step_id,
                    step=step_config.step,
                    plugin=step_config.plugin
                )

                # Emit step started event
                self._post_message_sync(
                    self.StepStarted(
                        step_index=step_index,
                        step_id=step_id,
                        step_name=step_name
                    )
                )

                try:
                    if step_config.workflow:
                        step_result = self._execute_workflow_step(step_config, ctx)
                    elif step_config.plugin and step_config.step:
                        step_result = self._execute_plugin_step(step_config, ctx)
                    elif step_config.command:
                        step_result = self._execute_command_step(step_config, ctx)
                    else:
                        step_result = Error(f"Invalid step configuration for '{step_id}'.")
                except Exception as e:
                    logger.exception("step_exception",
                        workflow=workflow.name,
                        step_id=step_id,
                        step=step_config.step
                    )
                    step_result = Error(f"An unexpected error occurred in step '{step_name}': {e}", e)

                # Handle step result
                step_duration = time.time() - step_start_time

                if is_exit(step_result):
                    # Log step exit
                    logger.info("step_exit",
                        workflow=workflow.name,
                        step_id=step_id,
                        message=step_result.message,
                        duration=round(step_duration, 3)
                    )

                    # Exit workflow immediately (not an error)
                    if step_result.metadata:
                        ctx.data.update(step_result.metadata)

                    # Post completion message
                    self._post_message_sync(
                        self.StepCompleted(
                            step_index=step_index,
                            step_id=step_id,
                            step_name=step_name
                        )
                    )

                    # Calculate is_nested before exiting workflow
                    # (check if there are parent workflows in the stack)
                    is_nested = len(ctx._workflow_stack) > 1  # >1 because current workflow is still in stack

                    # Log workflow completed
                    workflow_duration = time.time() - workflow_start_time
                    logger.info("workflow_completed",
                        workflow=workflow.name,
                        status="exited",
                        steps_executed=step_index,
                        duration=round(workflow_duration, 3)
                    )

                    # Post workflow completed message and exit
                    self._post_message_sync(
                        self.WorkflowCompleted(
                            workflow_name=workflow.name,
                            message=step_result.message,
                            is_nested=is_nested
                        )
                    )
                    return Success(step_result.message, step_result.metadata)

                elif is_error(step_result):
                    # Log step failure
                    logger.error("step_failed",
                        workflow=workflow.name,
                        step_id=step_id,
                        error=step_result.message,
                        on_error=step_config.on_error,
                        duration=round(step_duration, 3)
                    )

                    self._post_message_sync(
                        self.StepFailed(
                            step_index=step_index,
                            step_id=step_id,
                            step_name=step_name,
                            error_message=step_result.message,
                            on_error=step_config.on_error
                        )
                    )

                    if step_config.on_error == "fail":
                        # Log workflow failure
                        workflow_duration = time.time() - workflow_start_time
                        logger.error("workflow_failed",
                            workflow=workflow.name,
                            failed_at_step=step_id,
                            error=step_result.message,
                            steps_completed=step_index,
                            duration=round(workflow_duration, 3)
                        )

                        self._post_message_sync(
                            self.WorkflowFailed(
                                workflow_name=workflow.name,
                                step_name=step_name,
                                error_message=step_result.message
                            )
                        )
                        return Error(f"Workflow failed at step '{step_name}'", step_result.exception)
                    # else: on_error == "continue" - continue to next step
                elif is_skip(step_result):
                    # Log step skipped
                    logger.info("step_skipped",
                        workflow=workflow.name,
                        step_id=step_id,
                        reason=step_result.message,
                        duration=round(step_duration, 3)
                    )
                    self._post_message_sync(
                        self.StepSkipped(
                            step_index=step_index,
                            step_id=step_id,
                            step_name=step_name
                        )
                    )
                    if step_result.metadata:
                        ctx.data.update(step_result.metadata)
                else:  # Success
                    # Log step success
                    logger.info("step_success",
                        workflow=workflow.name,
                        step_id=step_id,
                        message=step_result.message if hasattr(step_result, 'message') else None,
                        duration=round(step_duration, 3)
                    )

                    self._post_message_sync(
                        self.StepCompleted(
                            step_index=step_index,
                            step_id=step_id,
                            step_name=step_name
                        )
                    )
                    if step_result.metadata:
                        ctx.data.update(step_result.metadata)

        finally:
            ctx.exit_workflow(workflow.name)

        # Check if this is a nested workflow (called from another workflow)
        is_nested = len(ctx._workflow_stack) > 0

        # Log workflow completion
        workflow_duration = time.time() - workflow_start_time
        logger.info("workflow_completed",
            workflow=workflow.name,
            status="success",
            steps_executed=step_index,
            duration=round(workflow_duration, 3)
        )

        # Emit workflow completed event
        self._post_message(
            self.WorkflowCompleted(
                workflow_name=workflow.name,
                message=f"Workflow '{workflow.name}' finished.",
                is_nested=is_nested
            )
        )

        # with open("/tmp/titan_debug.log", "a") as f:
        #     f.write(f"[{time.time():.3f}] WorkflowCompleted message posted\n")

        return Success(f"Workflow '{workflow.name}' finished.", {})

    def _execute_workflow_step(self, step_config: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
        """Execute a nested workflow as a step."""
        workflow_name = step_config.workflow
        if not workflow_name:
            return Error("Workflow step is missing the 'workflow' name.")

        try:
            sub_workflow = self._workflow_registry.get_workflow(workflow_name)
            if not sub_workflow:
                return Error(f"Nested workflow '{workflow_name}' not found.")
        except Exception as e:
            return Error(f"Failed to load workflow '{workflow_name}': {e}", e)

        # Recursively execute the nested workflow
        return self.execute(sub_workflow, ctx, params_override=step_config.params)

    def _execute_plugin_step(self, step_config: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
        """Execute a plugin step."""
        plugin_name = step_config.plugin
        step_func_name = step_config.step
        step_params = step_config.params

        # Validate required context variables
        required_vars = step_config.requires or step_config.params.get("requires", [])
        for var in required_vars:
            if var not in ctx.data:
                return Error(f"Step '{step_func_name}' is missing required context variable: '{var}'")

        step_func = None
        if plugin_name == "project":
            # Handle virtual 'project' plugin for project-specific steps
            step_func = self._workflow_registry.get_project_step(step_func_name)
            if not step_func:
                return Error(
                    f"Project step '{step_func_name}' not found in '.titan/steps/'.",
                    WorkflowExecutionError(f"Project step '{step_func_name}' not found")
                )
        elif plugin_name == "user":
            # Handle virtual 'user' plugin for user-specific steps
            step_func = self._workflow_registry.get_user_step(step_func_name)
            if not step_func:
                return Error(
                    f"User step '{step_func_name}' not found in '~/.titan/steps/'.",
                    WorkflowExecutionError(f"User step '{step_func_name}' not found")
                )
        elif plugin_name == "core":
            # Handle virtual 'core' plugin for built-in core steps
            step_func = self.CORE_STEPS.get(step_func_name)
            if not step_func:
                available = ", ".join(self.CORE_STEPS.keys())
                return Error(
                    f"Core step '{step_func_name}' not found. Available: {available}",
                    WorkflowExecutionError(f"Core step '{step_func_name}' not found")
                )
        else:
            # Handle regular plugins
            plugin_instance = self._plugin_registry.get_plugin(plugin_name)
            if not plugin_instance:
                return Error(
                    f"Plugin '{plugin_name}' not found or not initialized.",
                    WorkflowExecutionError(f"Plugin '{plugin_name}' not found")
                )

            step_functions = plugin_instance.get_steps()
            step_func = step_functions.get(step_func_name)
            if not step_func:
                return Error(
                    f"Step '{step_func_name}' not found in plugin '{plugin_name}'.",
                    WorkflowExecutionError(f"Step '{step_func_name}' not found")
                )

        # Prepare parameters for the step function
        resolved_params = self._resolve_parameters(step_params, ctx)

        # Add resolved parameters to context data so step can access them via ctx.get()
        ctx.data.update(resolved_params)

        # Execute the step function
        try:
            if plugin_name == "core":
                # Core steps receive (step: WorkflowStepModel, ctx: WorkflowContext)
                return step_func(step_config, ctx)
            else:
                # Plugin and project steps receive only ctx (params are in ctx.data)
                return step_func(ctx)
        except Exception as e:
            error_source = f"plugin '{plugin_name}'" if plugin_name not in ("project", "user", "core") else f"{plugin_name} step"
            return Error(f"Error executing step '{step_func_name}' from {error_source}: {e}", e)

    def _execute_command_step(self, step_config: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
        """Execute a shell command using the dedicated external function."""
        return execute_external_command_step(step_config, ctx)

    def _resolve_parameters(self, params: Dict[str, Any], ctx: WorkflowContext) -> Dict[str, Any]:
        """
        Resolve parameter values by substituting placeholders from context data.
        All workflow params are already in ctx.data.
        """
        from titan_cli.engine.steps.command_step import resolve_parameters_in_string

        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = resolve_parameters_in_string(value, ctx)
            else:
                resolved[key] = value  # Keep non-string parameters as is
        return resolved
