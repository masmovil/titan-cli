import pytest
from unittest.mock import MagicMock, patch
import os

from titan_cli.engine.steps.command_step import execute_command_step
from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error

# --- Fixtures ---

@pytest.fixture
def mock_context():
    """Provides a mock WorkflowContext."""
    ctx = MagicMock(spec=WorkflowContext)
    ctx.textual = MagicMock()
    ctx.get.side_effect = lambda key, default=None: {"cwd": "/tmp/mock_cwd"}.get(key, default)
    return ctx

@pytest.fixture
def mock_get_poetry_venv_env():
    """Mocks get_poetry_venv_env to return a dummy env."""
    with patch('titan_cli.engine.steps.command_step.get_poetry_venv_env') as mock_venv:
        mock_venv.return_value = {"PATH": "/mock/venv/bin:" + os.environ["PATH"], "MOCK_VENV": "1"}
        yield mock_venv

@pytest.fixture
def mock_popen():
    """Mocks subprocess.Popen to control command output."""
    with patch('titan_cli.engine.steps.command_step.Popen') as mock_popen_class:
        mock_process = MagicMock()
        mock_process.communicate.return_value = ("mock stdout", "mock stderr")
        mock_process.returncode = 0
        mock_popen_class.return_value = mock_process
        yield mock_popen_class

# --- Tests for execute_command_step() ---

def test_execute_command_step_success(mock_context, mock_popen):
    """Tests successful command execution."""
    mock_process = mock_popen.return_value
    mock_process.communicate.return_value = ("hello\n", "")
    mock_process.returncode = 0
    step_model = WorkflowStepModel(command="echo hello", id="test_echo", name="Echo Command")
    result = execute_command_step(step_model, mock_context)

    assert isinstance(result, Success)
    assert result.message == "Command 'echo hello' executed successfully."
    assert "hello\n" == result.metadata["command_output"]
    mock_context.textual.text.assert_any_call("Executing command: echo hello")
    mock_context.textual.text.assert_any_call("hello\n")
    mock_popen.assert_called_once()

def test_execute_command_step_failure(mock_context, mock_popen):
    """Tests command execution that results in a non-zero exit code."""
    mock_process = mock_popen.return_value
    mock_process.communicate.return_value = ("error stdout", "error stderr")
    mock_process.returncode = 1
    step_model = WorkflowStepModel(command="exit 1", id="test_exit", name="Exit Command")
    result = execute_command_step(step_model, mock_context)

    assert isinstance(result, Error)
    assert "Command failed with exit code 1" in result.message
    assert "error stderr" in result.message
    mock_context.textual.text.assert_any_call("Executing command: exit 1")
    mock_context.textual.text.assert_any_call("error stdout")
    mock_popen.assert_called_once()


def test_execute_command_step_command_not_found(mock_context, mock_popen):
    """Tests command execution where the command is not found."""
    # Popen raises FileNotFoundError when the command doesn't exist.
    # This happens regardless of use_shell setting when the executable is missing.
    # We simulate this by making the mock raise FileNotFoundError.
    mock_popen.side_effect = FileNotFoundError("command not found")
    step_model = WorkflowStepModel(command="non_existent_command", id="test_non_existent", name="Non Existent Command")
    result = execute_command_step(step_model, mock_context)

    assert isinstance(result, Error)
    assert "Command not found: non_existent_command" in result.message
    mock_context.textual.text.assert_any_call("Executing command: non_existent_command")

def test_execute_command_step_with_venv(mock_context, mock_get_poetry_venv_env, mock_popen):
    """Tests command execution when use_venv is true."""
    mock_process = mock_popen.return_value
    mock_process.communicate.return_value = ("venv_activated\n", "")
    mock_process.returncode = 0
    step_model = WorkflowStepModel(command="echo venv_activated", id="test_venv", name="Venv Command", params={"use_venv": True})
    result = execute_command_step(step_model, mock_context)

    assert isinstance(result, Success)
    assert result.message == "Command 'echo venv_activated' executed successfully."
    mock_get_poetry_venv_env.assert_called_once_with(cwd="/tmp/mock_cwd")
    # Check that both UI messages were called
    mock_context.textual.dim_text.assert_any_call("Activating poetry virtual environment for step...")
    mock_context.textual.text.assert_any_call("venv_activated\n")
    mock_popen.assert_called_once()
    # Only the venv's PATH is taken - the rest of the env stays minimal
    passed_env = mock_popen.call_args[1]['env']
    assert passed_env["PATH"] == mock_get_poetry_venv_env.return_value["PATH"]
    assert "MOCK_VENV" not in passed_env

def test_execute_command_step_venv_not_found(mock_context, mock_get_poetry_venv_env, mock_popen):
    """Tests command execution when use_venv is true but venv is not found."""
    mock_get_poetry_venv_env.return_value = None # Simulate venv not found
    step_model = WorkflowStepModel(command="echo venv_fail", id="test_venv_fail", name="Venv Fail Command", params={"use_venv": True})
    result = execute_command_step(step_model, mock_context)

    assert isinstance(result, Error)
    assert "Could not determine poetry virtual environment." in result.message
    mock_context.textual.dim_text.assert_called_with("Activating poetry virtual environment for step...")
    mock_popen.assert_not_called() # Popen should not be called if venv not found

def test_execute_command_step_parameter_substitution(mock_context, mock_popen):
    """Tests parameter substitution in the command string."""
    mock_process = mock_popen.return_value
    mock_process.communicate.return_value = ("substituted_value\n", "")
    mock_process.returncode = 0
    mock_context.data = {"my_var": "substituted_value"}
    step_model = WorkflowStepModel(command="echo ${my_var}", id="test_params", name="Params Command")
    result = execute_command_step(step_model, mock_context)

    assert isinstance(result, Success)
    assert result.message == "Command 'echo substituted_value' executed successfully."
    assert "substituted_value\n" == result.metadata["command_output"]
    mock_context.textual.text.assert_any_call("Executing command: echo substituted_value")
    mock_context.textual.text.assert_any_call("substituted_value\n")

def test_execute_command_step_no_command_template(mock_context, mock_popen):
    """Tests when command attribute is empty."""
    step_model = WorkflowStepModel(id="test_no_cmd", name="No Command", command="")
    result = execute_command_step(step_model, mock_context)
    assert isinstance(result, Error)
    assert "Command step is missing the 'command' attribute." in result.message
    mock_popen.assert_not_called()

def test_execute_command_step_cwd_from_context(mock_context, mock_popen):
    """Tests that cwd is taken from context if available."""
    mock_context.get.side_effect = lambda key, default=None: {"cwd": "/custom/path"}.get(key, default)
    mock_process = mock_popen.return_value
    mock_process.communicate.return_value = ("/custom/path\n", "")
    mock_process.returncode = 0
    step_model = WorkflowStepModel(command="pwd", id="test_cwd", name="CWD Command")
    result = execute_command_step(step_model, mock_context)
    assert isinstance(result, Success)
    assert "pwd" in result.message
    mock_popen.assert_called_once()
    assert mock_popen.call_args[1]['cwd'] == "/custom/path"


# --- Environment sanitization ---

def test_env_does_not_inherit_sensitive_variables(mock_context, mock_popen):
    """The subprocess env is minimal: parent-env secrets never reach it."""
    with patch.dict(os.environ, {"MY_SECRET_TOKEN": "tok_value", "PATH": "/usr/bin", "HOME": "/home/u"}):
        step_model = WorkflowStepModel(command="env", id="t", name="Env")
        execute_command_step(step_model, mock_context)

    passed_env = mock_popen.call_args[1]['env']
    assert "MY_SECRET_TOKEN" not in passed_env
    assert passed_env["PATH"] == "/usr/bin"
    assert passed_env["HOME"] == "/home/u"


def test_env_step_allowlist_passes_variables_through(mock_context, mock_popen):
    with patch.dict(os.environ, {"MY_SECRET_TOKEN": "tok_value", "OTHER_SECRET": "x"}):
        step_model = WorkflowStepModel(
            command="env", id="t", name="Env",
            params={"env_allowlist": ["MY_SECRET_TOKEN"]},
        )
        execute_command_step(step_model, mock_context)

    passed_env = mock_popen.call_args[1]['env']
    assert passed_env["MY_SECRET_TOKEN"] == "tok_value"
    assert "OTHER_SECRET" not in passed_env


def test_env_project_allowlist_passes_variables_through(mock_context, mock_popen):
    mock_context.titan_config.project_config = {
        "security": {"command_env_allowlist": ["PROJECT_ALLOWED"]}
    }
    with patch.dict(os.environ, {"PROJECT_ALLOWED": "yes", "NOT_ALLOWED": "no"}):
        step_model = WorkflowStepModel(command="env", id="t", name="Env")
        execute_command_step(step_model, mock_context)

    passed_env = mock_popen.call_args[1]['env']
    assert passed_env["PROJECT_ALLOWED"] == "yes"
    assert "NOT_ALLOWED" not in passed_env


def test_env_locale_and_xdg_prefixes_pass_through(mock_context, mock_popen):
    with patch.dict(os.environ, {"LC_ALL": "en_US.UTF-8", "XDG_CONFIG_HOME": "/home/u/.config"}):
        step_model = WorkflowStepModel(command="env", id="t", name="Env")
        execute_command_step(step_model, mock_context)

    passed_env = mock_popen.call_args[1]['env']
    assert passed_env["LC_ALL"] == "en_US.UTF-8"
    assert passed_env["XDG_CONFIG_HOME"] == "/home/u/.config"


# --- Redaction of the resolved command echo ---

def test_command_echo_is_redacted(mock_context, mock_popen):
    """A secret interpolated from ctx.data is masked in the UI echo."""
    from titan_cli.core.security import redaction
    redaction.clear_registry()
    try:
        redaction.register_secret("tok_secret_value")
        mock_context.data = {"api_token": "tok_secret_value"}
        step_model = WorkflowStepModel(command="curl -H 'Auth: ${api_token}'", id="t", name="Curl")
        result = execute_command_step(step_model, mock_context)

        mock_context.textual.text.assert_any_call(
            f"Executing command: curl -H 'Auth: {redaction.REDACTED}'"
        )
        # The subprocess still receives the real value.
        assert any("tok_secret_value" in arg for arg in mock_popen.call_args[1]['args'])
        # And the Success message is masked too.
        assert "tok_secret_value" not in result.message
    finally:
        redaction.clear_registry()


def test_command_stdout_echo_is_redacted(mock_context, mock_popen):
    from titan_cli.core.security import redaction
    redaction.clear_registry()
    try:
        redaction.register_secret("tok_secret_value")
        mock_process = mock_popen.return_value
        mock_process.communicate.return_value = ("token=tok_secret_value\n", "")
        mock_process.returncode = 0
        step_model = WorkflowStepModel(command="echo token", id="t", name="Echo")
        execute_command_step(step_model, mock_context)

        mock_context.textual.text.assert_any_call(f"token={redaction.REDACTED}\n")
    finally:
        redaction.clear_registry()
