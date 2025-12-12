from __future__ import annotations

from typing import Any, Dict, List, Optional
from titan_cli.core.workflows import ParsedWorkflow
from titan_cli.core.workflows.workflow_exceptions import WorkflowExecutionError
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import WorkflowResult, Success, Error, Skip, is_error, is_skip
from titan_cli.core.plugins.plugin_registry import PluginRegistry

# Assuming run_shell_command returns stdout, stderr, exit_code
# This needs actual implementation/import of run_shell_command or similar utility.
# For now, let's use subprocess directly.
from subprocess import run, CalledProcessError, TimeoutExpired

class WorkflowExecutor:
    """
    Executes a ParsedWorkflow by iterating through its steps,
    resolving plugins, and performing parameter substitution.
    """

    def __init__(self, plugin_registry: PluginRegistry):
        self._plugin_registry = plugin_registry

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
        ctx.total_steps = len([s for s in workflow.steps if not ("hook" in s and len(s) == 1)])

        ctx.ui.text.styled_text(("Starting workflow: ", "info"), (workflow.name, "info bold"))
        ctx.ui.text.body(workflow.description, style="dim")
        ctx.ui.spacer.small()

        step_index = 0
        for step_config in workflow.steps:
            # If the step is just a hook placeholder, skip it.
            # The registry has already handled merging.
            if "hook" in step_config and len(step_config) == 1:
                continue

            # Inject current step number into context
            step_index += 1
            ctx.current_step = step_index

            step_id = step_config.get("id", "anonymous_step")
            step_name = step_config.get("name", step_id)
            on_error = step_config.get("on_error", "fail") # Default to fail

            step_result: WorkflowResult = Success("Step not executed (default)", {}) # Default result

            try:
                if "plugin" in step_config and "step" in step_config:
                    # Execute plugin step
                    step_result = self._execute_plugin_step(step_config, ctx)
                elif "command" in step_config:
                    # Execute shell command
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

    def _execute_plugin_step(self, step_config: Dict[str, Any], ctx: WorkflowContext) -> WorkflowResult:
        plugin_name = step_config["plugin"]
        step_func_name = step_config["step"]
        step_params = step_config.get("params", {})

        # Validate required context variables
        required_vars = step_config.get("requires", [])
        for var in required_vars:
            if var not in ctx.data:
                return Error(f"Step '{step_func_name}' is missing required context variable: '{var}'")

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

        # Execute the step function (only pass ctx, parameters are in ctx.data)
        try:
            return step_func(ctx)
        except Exception as e:
            return Error(f"Error executing plugin step '{step_func_name}' from plugin '{plugin_name}': {e}", e)


    def _execute_command_step(self, step_config: Dict[str, Any], ctx: WorkflowContext) -> WorkflowResult:
        command_template = step_config["command"]

        # Validate required context variables
        required_vars = step_config.get("requires", [])
        for var in required_vars:
            if var not in ctx.data:
                return Error(f"Command step '{step_config.get('id', 'anonymous_command')}' is missing required context variable: '{var}'")

        # Resolve command parameters first
        resolved_command = self._resolve_parameters_in_string(command_template, ctx)

        ctx.ui.text.body(f"Running command: {resolved_command}", style="dim")
        
        try:
            # shell=True is generally discouraged due to security, but often needed for CLI tools
            # For a development tool, it's often acceptable.
            result = run(resolved_command, shell=True, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            if result.stderr:
                ctx.ui.text.warning(f"Command stderr: {result.stderr.strip()}")
            return Success("Command executed successfully.", {"command_output": output})
        except CalledProcessError as e:
            return Error(f"Command failed with exit code {e.returncode}: {e.stderr.strip()}", e)
        except TimeoutExpired as e:
            return Error(f"Command timed out: {e.stdout.strip()} {e.stderr.strip()}", e)
        except FileNotFoundError as e:
            return Error(f"Command not found: {e}", e)
        except Exception as e:
            return Error(f"Unhandled error during command execution: {e}", e)

    def _resolve_parameters(self, params: Dict[str, Any], ctx: WorkflowContext) -> Dict[str, Any]:
        """
        Resolves parameter values by substituting placeholders from context data.
        All workflow params are already in ctx.data.
        """
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = self._resolve_parameters_in_string(value, ctx)
            else:
                resolved[key] = value # Keep non-string parameters as is
        return resolved

    def _resolve_parameters_in_string(self, text: str, ctx: WorkflowContext) -> str:
        """
        Substitutes placeholders in a string using values from ctx.data.
        Supports both ${placeholder} and {{ params.key }} or {{ key }} syntax.
        All workflow params are already in ctx.data.
        """
        import re

        def replace_placeholder(match):
            # Extract the placeholder - could be from ${var} or {{ var }} or {{ params.var }}
            placeholder = match.group(1).strip()

            # Handle params.key format (remove "params." prefix)
            if placeholder.startswith("params."):
                placeholder = placeholder[7:]  # Remove "params."

            # Check ctx.data (all params including workflow-level are here)
            if placeholder in ctx.data:
                return str(ctx.data[placeholder])

            # Check config (e.g., config.git.main_branch) - requires more complex path parsing
            # For now, we will not implement full config path resolution here, but it's a future enhancement

            # If not found, return original placeholder or raise an error
            return match.group(0) # Keep placeholder if not resolved

        # Replace both ${placeholder} and {{ placeholder }} or {{ params.placeholder }}
        # First handle Jinja2-style {{ ... }}
        text = re.sub(r'\{\{\s*([\w.]+)\s*\}\}', replace_placeholder, text)
        # Then handle shell-style ${...}
        text = re.sub(r'\$\{(\w+)\}', replace_placeholder, text)

        return text
