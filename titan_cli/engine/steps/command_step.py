import os
from subprocess import Popen, PIPE
import re
import shlex
from titan_cli.core.security import redact
from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, WorkflowResult
from titan_cli.engine.utils import get_poetry_venv_env

# Environment a command step starts from. Deliberately small: anything in the
# parent environment that is not on this list (or on a step/project allowlist)
# never reaches the subprocess, so a credential exported in the user's shell
# cannot leak into a workflow command by inheritance.
BASE_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "COLORTERM",
    "LANG", "LANGUAGE", "TZ",
    # git over ssh needs the agent socket; it is a socket path, not a value.
    "SSH_AUTH_SOCK",
    # Corporate proxies, both spellings.
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
})

# Variable-name prefixes passed through wholesale: locale settings and the
# XDG base dirs that CLI tools read their config from.
BASE_ENV_PREFIXES = ("LC_", "XDG_")


def _project_env_allowlist(ctx: WorkflowContext) -> list[str]:
    """Extra allowed variables from the project's [security] config block."""
    config = getattr(ctx, "titan_config", None)
    project = getattr(config, "project_config", None)
    if not isinstance(project, dict):
        return []
    security = project.get("security", {})
    if not isinstance(security, dict):
        return []
    values = security.get("command_env_allowlist", [])
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def build_command_env(step: WorkflowStepModel, ctx: WorkflowContext) -> dict:
    """
    Minimal environment for a command step's subprocess.

    Base allowlist + the project's `[security] command_env_allowlist` + the
    step's `env_allowlist` param. Never `os.environ.copy()`.
    """
    allowed = set(BASE_ENV_ALLOWLIST)
    allowed.update(_project_env_allowlist(ctx))
    step_allowlist = step.params.get("env_allowlist", [])
    if isinstance(step_allowlist, list):
        allowed.update(value for value in step_allowlist if isinstance(value, str))

    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed or key.startswith(BASE_ENV_PREFIXES)
    }


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
        process_env = build_command_env(step, ctx)
        cwd = ctx.get("cwd") or os.getcwd()

        if use_venv:
            ctx.textual.dim_text("Activating poetry virtual environment for step...")

            venv_env = get_poetry_venv_env(cwd=cwd)
            if venv_env:
                # Only the venv's PATH — not the full inherited environment
                # that get_poetry_venv_env builds it from.
                process_env["PATH"] = venv_env["PATH"]
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

