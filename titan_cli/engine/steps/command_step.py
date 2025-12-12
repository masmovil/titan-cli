import os
import json
from pathlib import Path
from subprocess import Popen, PIPE
import re
from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, WorkflowResult


def _render_ruff_output(output_json: str, ctx: WorkflowContext):
    """Parses ruff's JSON output and renders it with UI components."""
    if not ctx.ui:
        return

    try:
        errors = json.loads(output_json)
        if not errors:
            ctx.ui.text.success("Ruff found no issues.")
            return

        # Summary panel
        fixable_count = sum(1 for e in errors if e.get("fix"))
        summary = f"Ruff found {len(errors)} error(s)."
        if fixable_count > 0:
            summary += f" ({fixable_count} fixable)"
        
        ctx.ui.panel.print(summary, panel_type="warning" if errors else "success", title="Ruff Scan Results")
        ctx.ui.spacer.small()

        for error in errors:
            file_path = error.get("filename", "Unknown file")
            location = f"Line: {error.get('location', {}).get('row', '?')}, Col: {error.get('location', {}).get('column', '?')}"
            code = error.get('code', '')
            message = error.get('message', 'No message.')
            
            panel_content = f"{message}\n[dim]{location}[/dim]"
            panel_title = f"{file_path} ([bold]{code}[/bold])"
            
            ctx.ui.panel.print(panel_content, title=panel_title, panel_type="error")

    except json.JSONDecodeError:
        # If output is not JSON, just print it raw.
        ctx.ui.text.body(output_json)


def _resolve_parameters_in_string(text: str, ctx: WorkflowContext) -> str:
    """
    Substitutes ${placeholder} in a string using values from ctx.data.
    """
    def replace_placeholder(match):
        placeholder = match.group(1)
        if placeholder in ctx.data:
            return str(ctx.data[placeholder])
        return match.group(0)

    return re.sub(r'\$\{(\w+)\}', replace_placeholder, text)


def execute_command_step(step: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
    """
    Executes a shell command defined in a workflow step.
    """
    command_template = step.command
    if not command_template:
        return Error("Command step is missing the 'command' attribute.")

    command = _resolve_parameters_in_string(command_template, ctx)

    if ctx.ui:
        ctx.ui.text.info(f"Executing command: {command}")

    try:
        use_venv = step.params.get("use_venv", False)
        process_env = os.environ.copy()

        if use_venv:
            if ctx.ui:
                ctx.ui.text.body("Activating poetry virtual environment for step...", style="dim")
            
            env_proc = Popen(["poetry", "env", "info", "-p"], stdout=PIPE, stderr=PIPE, text=True, cwd=ctx.get("cwd"))
            venv_path, err = env_proc.communicate()
            
            if env_proc.returncode == 0 and venv_path.strip():
                bin_path = Path(venv_path.strip()) / "bin"
                process_env["PATH"] = f"{bin_path}:{process_env['PATH']}"
            else:
                return Error(f"Could not determine poetry virtual environment. Error: {err}")

        # We capture stdout now instead of streaming to be able to parse it.
        process = Popen(command, shell=True, stdout=PIPE, stderr=PIPE, text=True, cwd=ctx.get("cwd"), env=process_env)
        
        stdout_output, stderr_output = process.communicate()

        # Check if we should use the special ruff renderer
        is_ruff_json = "ruff" in command and "--output-format=json" in command

        if is_ruff_json and stdout_output:
            _render_ruff_output(stdout_output, ctx)
        elif stdout_output:
            # Fallback for non-ruff commands or non-json output
            print(stdout_output)
        
        if process.returncode != 0:
            error_message = f"Command failed with exit code {process.returncode}"
            # For ruff, the JSON is the important part. For others, stderr is.
            if not is_ruff_json and stderr_output:
                error_message += f"\n[stderr]{stderr_output}[/stderr]"

            return Error(error_message)

        return Success(
            message=f"Command '{command}' executed successfully.",
            metadata={"command_output": stdout_output}
        )

    except FileNotFoundError:
        return Error(f"Command not found: {command.split()[0]}")
    except Exception as e:
        return Error(f"An unexpected error occurred: {e}", exception=e)
