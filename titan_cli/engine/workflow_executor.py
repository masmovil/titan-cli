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
        """
        # Merge workflow params into ctx.data with optional overrides
        effective_params = {**workflow.params}
        if params_override:
            effective_params.update(params_override)

        # Load params into ctx.data so steps can access them
        ctx.data.update(effective_params)

        # Inject workflow metadata into context
        ctx.workflow_name = workflow.name
        ctx.total_steps = len([s for s in workflow.steps if not s.get("hook")])

        if ctx.ui:
            # Show workflow banner
            ctx.ui.spacer.line()
            ctx.ui.text.styled_text(("═" * 60, "bold cyan"))
            ctx.ui.text.styled_text((f"  🚀 {workflow.name}", "bold cyan"))
            if workflow.description:
                ctx.ui.text.styled_text((f"  {workflow.description}", "dim"))
            if workflow.source:
                ctx.ui.text.styled_text((f"  Source: {workflow.source}", "dim italic"))
            ctx.ui.text.styled_text(("═" * 60, "bold cyan"))
            ctx.ui.spacer.small()

        ctx.enter_workflow(workflow.name)
        try:
            step_index = 0
            for step_data in workflow.steps:
                # Hooks are resolved by the registry, so we just skip the placeholder.
                if step_data.get("hook") and len(step_data) == 1:
                    continue

                step_index += 1
                ctx.current_step = step_index
                
                step_config = WorkflowStepModel(**step_data)

                step_id = step_config.id
                step_name = step_config.name or step_id
                
                try:
                    if step_config.workflow:
                        step_result = self._execute_workflow_step(step_config, ctx)
                    elif step_config.plugin and step_config.step:
                        step_result = self._execute_plugin_step(step_config, ctx)
                    elif step_config.command:
                        step_result = self._execute_command_step(step_config, ctx)
                    else:
                        # This should be caught by model validation, but as a safeguard:
                        step_result = Error(f"Invalid step configuration for '{step_id}'.")
                except Exception as e:
                    step_result = Error(f"An unexpected error occurred in step '{step_name}': {e}", e)

                # Handle step result
                if is_error(step_result):
                    if ctx.ui:
                        # Show error panel for the failed step
                        ctx.ui.spacer.small()
                        ctx.ui.panel.print(
                            f"Step failed: {step_result.message}",
                            panel_type="error",
                            title=f"❌ {step_name}"
                        )
                        ctx.ui.spacer.small()

                    if step_config.on_error == "fail":
                        if ctx.ui:
                            # Show workflow failure banner
                            ctx.ui.spacer.small()
                            ctx.ui.text.styled_text(("═" * 60, "bold red"))
                            ctx.ui.text.styled_text((f"  ❌ Workflow Failed: {workflow.name}", "bold red"))
                            ctx.ui.text.styled_text((f"  Failed at step: {step_name}", "red"))
                            if step_result.message:
                                ctx.ui.text.styled_text((f"  Error: {step_result.message}", "dim"))
                            ctx.ui.text.styled_text(("═" * 60, "bold red"))
                            ctx.ui.spacer.line()
                        return Error(f"Workflow failed at step '{step_name}'", step_result.exception)
                    else:
                        # on_error == "continue" - show warning but continue
                        if ctx.ui:
                            ctx.ui.text.styled_text(("  ⚠️  Continuing despite error (on_error: continue)", "yellow"))
                            ctx.ui.spacer.small()
                elif is_skip(step_result):
                    if step_result.metadata:
                        ctx.data.update(step_result.metadata)
                else: # Success
                    if step_result.metadata:
                        ctx.data.update(step_result.metadata)

        finally:
            ctx.exit_workflow(workflow.name)

        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.styled_text(("═" * 60, "bold green"))
            ctx.ui.text.styled_text((f"  ✅ Workflow Completed: {workflow.name}", "bold green"))
            ctx.ui.text.styled_text(("═" * 60, "bold green"))
            ctx.ui.spacer.line()
        return Success(f"Workflow '{workflow.name}' finished.", {})

    def _execute_workflow_step(self, step_config: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
        """Executes a nested workflow as a step."""
        workflow_name = step_config.workflow
        if not workflow_name:
            return Error("Workflow step is missing the 'workflow' name.")

        try:
            sub_workflow = self._workflow_registry.get_workflow(workflow_name)
            if not sub_workflow:
                return Error(f"Nested workflow '{workflow_name}' not found.")
        except Exception as e:
            return Error(f"Failed to load workflow '{workflow_name}': {e}", e)

        if ctx.ui:
            # Add indentation based on workflow nesting depth
            indent = "  " * len(ctx._workflow_stack)
            ctx.ui.text.info(f"{indent}→ Running nested workflow: {sub_workflow.name}")

        # We recursively call the main execute method.
        # Pass a copy of the context data to isolate it if needed, but for now, we share it.
        # The `enter_workflow` check will prevent infinite recursion.
        return self.execute(sub_workflow, ctx, params_override=step_config.params)


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
