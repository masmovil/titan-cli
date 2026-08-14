import os
from subprocess import Popen, PIPE
import re
import shlex
from titan_cli.core.security import redact
from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, WorkflowResult
from titan_cli.engine.utils import get_poetry_venv_env


def resolve_parameters_in_string(text: str, ctx: WorkflowContext) -> str:
    """
    Substitutes ${placeholder} in a string using values from ctx.data.
    Public function so it can be used by workflow_executor.
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

    command = resolve_parameters_in_string(command_template, ctx)

    # ${key} interpolation from ctx.data can carry a secret into the command
    # string; what the user sees goes through the redaction filter.
    ctx.textual.text(f"Executing command: {redact(command)}")

    try:
        use_venv = step.params.get("use_venv", False)
        # A command step runs whatever the user could type in their own
        # console, so it inherits the same environment their console has.
        # (Titan-managed project secrets are NOT in os.environ - the vault
        # keeps them in memory - so none of them ride along here.)
        process_env = os.environ.copy()
        cwd = ctx.get("cwd") or os.getcwd()

        if use_venv:
            ctx.textual.dim_text("Activating poetry virtual environment for step...")

            venv_env = get_poetry_venv_env(cwd=cwd)
            if venv_env:
                process_env = venv_env
            else:
                return Error("Could not determine poetry virtual environment.")

        # Determine command execution arguments based on security model
        if step.use_shell:
            # Insecure method for commands that need shell features (e.g., pipes)
            popen_args = {"args": command, "shell": True}
        else:
            # Secure method: split command into a list to avoid injection
            popen_args = {"args": shlex.split(command), "shell": False}

        process = Popen(
            **popen_args,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            cwd=cwd,
            env=process_env
        )
        
        stdout_output, stderr_output = process.communicate()

        if stdout_output:
            ctx.textual.text(redact(stdout_output))

        if process.returncode != 0:
            error_message = f"Command failed with exit code {process.returncode}"
            if stderr_output:
                error_message += f"\n{stderr_output}"

            return Error(redact(error_message))

        return Success(
            message=f"Command '{redact(command)}' executed successfully.",
            metadata={"command_output": stdout_output}
        )

    except FileNotFoundError:
        command_to_report = command.split()[0] if not step.use_shell else command
        return Error(f"Command not found: {command_to_report}")
    except Exception as e:
        return Error(f"An unexpected error occurred: {e}", exception=e)

