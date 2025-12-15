from __future__ import annotations

from typing import Any, Dict, Optional
from titan_cli.core.workflows import ParsedWorkflow
from titan_cli.core.workflows.workflow_exceptions import WorkflowExecutionError
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import WorkflowResult, Success, Error, is_error, is_skip
from titan_cli.core.workflows.workflow_registry import WorkflowRegistry
from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.steps.command_step import execute_command_step as execute_external_command_step
from titan_cli.engine.steps.ai_assistant_step import execute_ai_assistant_step

# ... (the rest of the imports)

class WorkflowExecutor:
    """
    Executes a ParsedWorkflow by iterating through its steps,
    resolving plugins, and performing parameter substitution.
    """

    # Core steps available to all workflows
    CORE_STEPS = {
        "ai_code_assistant": execute_ai_assistant_step,
    }

    def __init__(self, plugin_registry: PluginRegistry, workflow_registry: WorkflowRegistry):
        self._plugin_registry = plugin_registry
        self._workflow_registry = workflow_registry

    def execute(self, workflow: ParsedWorkflow, ctx: WorkflowContext, params_override: Optional[Dict[str, Any]] = None) -> WorkflowResult:
        """
        Executes the given ParsedWorkflow.

        Args:
            workflow: The ParsedWorkflow object to execute.
            ctx: The WorkflowContext for the execution.
            params_override: Optional dictionary to override workflow params.

        Returns:
            A WorkflowResult indicating the overall outcome.
        """
        # Merge workflow params into ctx.data with optional overrides
        effective_params = {**workflow.params}
        if params_override:
            effective_params.update(params_override)

        # Load params into ctx.data so steps can access them
        ctx.data.update(effective_params)

        # Inject workflow metadata into context
        ctx.workflow_name = workflow.name
        # Only count actual steps, not hook placeholders
        ctx.total_steps = len([s for s in workflow.steps if not (s.get("hook") and len(s) == 1)])

        ctx.ui.text.styled_text(("Starting workflow: ", "info"), (workflow.name, "info bold"))
        ctx.ui.text.body(workflow.description, style="dim")
        ctx.ui.spacer.small()

        step_index = 0
        for step_config_dict in workflow.steps: # Renamed step_config to step_config_dict to clarify it's a dict
            # If the step is just a hook placeholder, skip it.
            # The registry has already handled merging.
            if step_config_dict.get("hook") and len(step_config_dict) == 1:
                continue

            # Inject current step number into context
            step_index += 1
            ctx.current_step = step_index

            # Parse the dictionary into a WorkflowStepModel for better type safety
            step_config = WorkflowStepModel(**step_config_dict)

            step_id = step_config.id if step_config.id else "anonymous_step"
            step_name = step_config.name if step_config.name else step_id
            on_error = step_config.on_error # Default is "fail" in model

            step_result: WorkflowResult = Success("Step not executed (default)", {}) # Default result

            try:
                if step_config.plugin and step_config.step:
                    # Execute plugin step
                    step_result = self._execute_plugin_step(step_config, ctx)
                elif step_config.command:
                    # Execute shell command using our new function
                    step_result = self._execute_command_step(step_config, ctx)
                else:
                    step_result = Error(f"Invalid step configuration for '{step_id}': Missing 'plugin/step' or 'command'.", WorkflowExecutionError("Invalid step config"))

            except Exception as e:
                step_result = Error(f"An unexpected error occurred in step '{step_name}': {e}", e)

            # Handle step result
            if is_error(step_result):
                # Steps may not show their own errors, so show it here
                ctx.ui.text.error(f"Step '{step_name}' failed: {step_result.message}")
                if on_error == "fail":
                    ctx.ui.text.error(f"Workflow '{workflow.name}' stopped due to step failure.")
                    return Error(f"Workflow failed at step '{step_name}'", step_result.exception)
            elif is_skip(step_result):
                # Skip result - step should handle its own UI
                # Just merge metadata into workflow context data
                if step_result.metadata:
                    ctx.data.update(step_result.metadata)
            else:
                # Success case - merge step metadata into workflow context data
                if step_result.metadata:
                    ctx.data.update(step_result.metadata)

        ctx.ui.text.success(f"Workflow '{workflow.name}' completed successfully.")
        return Success(f"Workflow '{workflow.name}' finished.", {})

    def _execute_plugin_step(self, step_config: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
        plugin_name = step_config.plugin
        step_func_name = step_config.step
        step_params = step_config.params

        # Validate required context variables
        # This was part of `command` originally, but it's good practice for plugin steps too.
        required_vars = step_config.params.get("requires", []) # Assuming 'requires' can be in params
        for var in required_vars:
            if var not in ctx.data:
                return Error(f"Step '{step_func_name}' is missing required context variable: '{var}'")

        step_func = None
        if plugin_name == "project":
            # Handle virtual 'project' plugin for project-specific steps
            step_func = self._workflow_registry.get_project_step(step_func_name)
            if not step_func:
                return Error(f"Project step '{step_func_name}' not found in '.titan/steps/'.", WorkflowExecutionError(f"Project step '{step_func_name}' not found"))
        elif plugin_name == "core":
            # Handle virtual 'core' plugin for built-in core steps
            step_func = self.CORE_STEPS.get(step_func_name)
            if not step_func:
                available = ", ".join(self.CORE_STEPS.keys())
                return Error(f"Core step '{step_func_name}' not found. Available: {available}", WorkflowExecutionError(f"Core step '{step_func_name}' not found"))
        else:
            # Handle regular plugins
            plugin_instance = self._plugin_registry.get_plugin(plugin_name)
            if not plugin_instance:
                return Error(f"Plugin '{plugin_name}' not found or not initialized.", WorkflowExecutionError(f"Plugin '{plugin_name}' not found"))
            
            step_functions = plugin_instance.get_steps()
            step_func = step_functions.get(step_func_name)
            if not step_func:
                return Error(f"Step '{step_func_name}' not found in plugin '{plugin_name}'.", WorkflowExecutionError(f"Step '{step_func_name}' not found"))

        # Execute the step function.
        try:
            if plugin_name == "core":
                # Core steps receive (step: WorkflowStepModel, ctx: WorkflowContext)
                return step_func(step_config, ctx)
            else:
                # Plugin and project steps receive (ctx, **params)
                resolved_params = self._resolve_parameters(step_params, ctx)
                return step_func(ctx=ctx, **resolved_params)
        except Exception as e:
            error_source = f"plugin '{plugin_name}'" if plugin_name not in ("project", "core") else f"{plugin_name} step"
            return Error(f"Error executing step '{step_func_name}' from {error_source}: {e}", e)


    def _execute_command_step(self, step_config: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult: # Changed type hint to WorkflowStepModel
        """
        Executes a shell command using the dedicated external function.
        """
        # Call the external function that handles command execution
        return execute_external_command_step(step_config, ctx)

    def _resolve_parameters(self, params: Dict[str, Any], ctx: WorkflowContext) -> Dict[str, Any]:
        """
        Resolves parameter values by substituting placeholders from context data.
        All workflow params are already in ctx.data.
        """
        from titan_cli.engine.steps.command_step import resolve_parameters_in_string

        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = resolve_parameters_in_string(value, ctx)
            else:
                resolved[key] = value # Keep non-string parameters as is
        return resolved
