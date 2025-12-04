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

    def execute(self, workflow: ParsedWorkflow, ctx: WorkflowContext) -> WorkflowResult:
        """
        Executes the given ParsedWorkflow.
        
        Args:
            workflow: The ParsedWorkflow object to execute.
            ctx: The WorkflowContext for the execution.
            
        Returns:
            A WorkflowResult indicating the overall outcome.
        """
        ctx.ui.text.styled_text(("Starting workflow: ", "info"), (workflow.name, "info bold"))
        ctx.ui.text.body(workflow.description, style="dim")
        ctx.ui.spacer.small()

        for step_config in workflow.steps:
            # If the step is just a hook placeholder, skip it.
            # The registry has already handled merging.
            if "hook" in step_config and len(step_config) == 1:
                continue

            step_id = step_config.get("id", "anonymous_step")
            step_name = step_config.get("name", step_id)
            on_error = step_config.get("on_error", "fail") # Default to fail

            ctx.ui.text.styled_text(("Executing step: ", "info"), (step_name, "info bold"), (f" ({step_id})", "info dim"))


            step_result: WorkflowResult = Success("Step not executed (default)", {}) # Default result

            try:
                if "plugin" in step_config and "step" in step_config:
                    # Execute plugin step
                    step_result = self._execute_plugin_step(step_config, ctx, workflow.params)
                elif "command" in step_config:
                    # Execute shell command
                    step_result = self._execute_command_step(step_config, ctx, workflow.params)
                else:
                    step_result = Error(f"Invalid step configuration for '{step_id}': Missing 'plugin/step' or 'command'.", WorkflowExecutionError("Invalid step config"))

            except Exception as e:
                step_result = Error(f"An unexpected error occurred in step '{step_name}': {e}", e)

            # Handle step result
            if is_error(step_result):
                ctx.ui.text.error(f"Step '{step_name}' failed: {step_result.message}")
                if on_error == "fail":
                    ctx.ui.text.error(f"Workflow '{workflow.name}' stopped due to step failure.")
                    return Error(f"Workflow failed at step '{step_name}'", step_result.exception)
            elif is_skip(step_result):
                ctx.ui.text.warning(f"Step '{step_name}' skipped: {step_result.message}")
            else:
                ctx.ui.text.success(f"Step '{step_name}' completed: {step_result.message}")
                # Merge step metadata into workflow context data
                if step_result.metadata:
                    ctx.data.update(step_result.metadata)
            
            ctx.ui.spacer.small() # Add a small space after each step

        ctx.ui.text.success(f"Workflow '{workflow.name}' completed successfully.")
        return Success(f"Workflow '{workflow.name}' finished.", {})

    def _execute_plugin_step(self, step_config: Dict[str, Any], ctx: WorkflowContext, workflow_params: Dict[str, Any]) -> WorkflowResult:
        plugin_name = step_config["plugin"]
        step_func_name = step_config["step"]
        step_params = step_config.get("params", {})

        plugin_instance = self._plugin_registry.get_plugin(plugin_name)
        if not plugin_instance:
            return Error(f"Plugin '{plugin_name}' not found or not initialized.", WorkflowExecutionError(f"Plugin '{plugin_name}' not found"))
        
        step_functions = plugin_instance.get_steps()
        step_func = step_functions.get(step_func_name)
        if not step_func:
            return Error(f"Step '{step_func_name}' not found in plugin '{plugin_name}'.", WorkflowExecutionError(f"Step '{step_func_name}' not found"))

        # Prepare parameters for the step function
        resolved_params = self._resolve_parameters(step_params, ctx, workflow_params)
        
        # Execute the step function. Assuming step functions take ctx and **kwargs
        try:
            return step_func(ctx=ctx, **resolved_params)
        except Exception as e:
            # Need to get the actual function name for the error message
            # step_func_name is the key, but we need the actual func's name for consistency if it's different.
            # However, step_func_name should suffice for logging where it came from.
            return Error(f"Error executing plugin step '{step_func_name}' from plugin '{plugin_name}': {e}", e)


    def _execute_command_step(self, step_config: Dict[str, Any], ctx: WorkflowContext, workflow_params: Dict[str, Any]) -> WorkflowResult:
        command_template = step_config["command"]
        # Resolve command parameters first
        resolved_command = self._resolve_parameters_in_string(command_template, ctx, workflow_params)

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

    def _resolve_parameters(self, params: Dict[str, Any], ctx: WorkflowContext, workflow_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolves parameter values by substituting placeholders from context data and workflow params.
        Priority: ctx.data > workflow_params
        """
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = self._resolve_parameters_in_string(value, ctx, workflow_params)
            else:
                resolved[key] = value # Keep non-string parameters as is
        return resolved

    def _resolve_parameters_in_string(self, text: str, ctx: WorkflowContext, workflow_params: Dict[str, Any]) -> str:
        """
        Substitutes ${placeholder} in a string using values from ctx.data and workflow_params.
        """
        import re
        
        def replace_placeholder(match):
            placeholder = match.group(1) # e.g., "commit_message"
            
            # 1. Check ctx.data (highest priority, dynamically updated by steps)
            if placeholder in ctx.data:
                return str(ctx.data[placeholder])
            
            # 2. Check workflow-level params (static for the workflow)
            if placeholder in workflow_params:
                return str(workflow_params[placeholder])

            # 3. Check config (e.g., config.git.main_branch) - requires more complex path parsing
            # For now, we will not implement full config path resolution here, but it's a future enhancement
            
            # If not found, return original placeholder or raise an error
            return match.group(0) # Keep placeholder if not resolved

        # Regex to find ${placeholder} patterns
        return re.sub(r'\$\{(\w+)\}', replace_placeholder, text)
