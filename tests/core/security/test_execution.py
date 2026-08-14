"""Use-primitives: the secret crosses into an effect, never back to the caller."""

import os
import stat
from unittest.mock import patch

import pytest

from titan_cli.core.security import SecretBroker, redaction
from titan_cli.core.security._vault import SecretManager


@pytest.fixture(autouse=True)
def clean_redaction_registry():
    redaction.clear_registry()
    yield
    redaction.clear_registry()


@pytest.fixture
def keyring_store():
    """In-memory keyring so tests never touch the real OS keyring."""
    store = {}
    with patch('keyring.get_password', side_effect=lambda ns, k: store.get((ns, k))), \
         patch('keyring.set_password', side_effect=lambda ns, k, v: store.__setitem__((ns, k), v)), \
         patch('keyring.delete_password', side_effect=lambda ns, k: store.pop((ns, k), None)):
        yield store


@pytest.fixture
def vault(tmp_path, keyring_store):
    return SecretManager(project_path=tmp_path)


NS = "titan.plugins.demo"


# --- run_with_secret_stdin ---

def test_stdin_feeds_the_secret_and_redacts_output(vault, keyring_store):
    keyring_store[(NS, "passphrase")] = "stdin_secret_value"
    broker = SecretBroker(vault, NS)

    result = broker.run_with_secret_stdin("passphrase", "Enter passphrase", ["cat"])

    assert result.succeeded
    # cat echoes the secret back - the caller only ever sees it masked.
    assert result.stdout == redaction.REDACTED
    assert "stdin_secret_value" not in result.stdout


def test_stdin_prompts_and_stores_when_missing(vault, keyring_store):
    broker = SecretBroker(vault, NS, prompter=lambda prompt: "typed_value")

    result = broker.run_with_secret_stdin("passphrase", "Enter passphrase", ["cat"])

    assert result.succeeded
    assert keyring_store[(NS, "passphrase")] == "typed_value"


def test_stdin_stale_stored_secret_is_deleted_and_reprompted(vault, keyring_store):
    keyring_store[(NS, "passphrase")] = "stale_wrong_value"
    broker = SecretBroker(vault, NS, prompter=lambda prompt: "correct_value")
    check = ["sh", "-c", 'test "$(cat)" = "correct_value"']

    result = broker.run_with_secret_stdin("passphrase", "Enter passphrase", check)

    assert result.succeeded
    assert keyring_store[(NS, "passphrase")] == "correct_value"


def test_stdin_no_retry_when_disabled(vault, keyring_store):
    keyring_store[(NS, "passphrase")] = "stale_wrong_value"
    prompts = []

    def prompter(prompt):
        prompts.append(prompt)
        return "correct_value"

    broker = SecretBroker(vault, NS, prompter=prompter)
    check = ["sh", "-c", 'test "$(cat)" = "correct_value"']

    result = broker.run_with_secret_stdin(
        "passphrase", "Enter passphrase", check, retry_on_failure=False
    )

    assert not result.succeeded
    assert prompts == []
    assert keyring_store[(NS, "passphrase")] == "stale_wrong_value"


def test_stdin_cancelled_prompt_runs_nothing(vault, keyring_store):
    broker = SecretBroker(vault, NS, prompter=lambda prompt: None)

    result = broker.run_with_secret_stdin("passphrase", "Enter passphrase", ["cat"])

    assert result.cancelled
    assert not result.succeeded
    assert (NS, "passphrase") not in keyring_store


# --- run_with_secret_env ---

def test_env_injects_only_the_secret_into_a_minimal_env(vault, keyring_store):
    keyring_store[(NS, "api_token")] = "env_secret_value"
    broker = SecretBroker(vault, NS)

    with patch.dict(os.environ, {"UNRELATED_SHELL_SECRET": "should_not_leak"}):
        result = broker.run_with_secret_env(
            "api_token",
            "MY_TOKEN",
            ["sh", "-c", 'printf "%s|%s" "$MY_TOKEN" "$UNRELATED_SHELL_SECRET"'],
        )

    assert result.succeeded
    # The injected value comes back redacted; the shell secret never arrived.
    assert result.stdout == f"{redaction.REDACTED}|"


def test_env_allowlist_passes_extra_variables(vault, keyring_store):
    keyring_store[(NS, "api_token")] = "env_secret_value"
    broker = SecretBroker(vault, NS)

    with patch.dict(os.environ, {"NEEDED_VAR": "needed"}):
        result = broker.run_with_secret_env(
            "api_token",
            "MY_TOKEN",
            ["sh", "-c", 'printf "%s" "$NEEDED_VAR"'],
            env_allowlist=["NEEDED_VAR"],
        )

    assert result.succeeded
    assert result.stdout == "needed"


def test_env_missing_secret_without_prompt_is_cancelled(vault, keyring_store):
    broker = SecretBroker(vault, NS)

    result = broker.run_with_secret_env("missing", "MY_TOKEN", ["true"])

    assert result.cancelled


# --- with_secret_tempfile ---

def test_tempfile_has_0600_content_and_guaranteed_deletion(vault, keyring_store):
    keyring_store[(NS, "sa_json")] = '{"type": "service_account"}'
    broker = SecretBroker(vault, NS)
    seen = {}

    def callback(path):
        seen["path"] = path
        seen["mode"] = stat.S_IMODE(path.stat().st_mode)
        seen["content"] = path.read_text()
        return "callback_result"

    result = broker.with_secret_tempfile("sa_json", callback)

    assert result == "callback_result"
    assert seen["mode"] == 0o600
    assert seen["content"] == '{"type": "service_account"}'
    assert not seen["path"].exists()


def test_tempfile_deleted_even_when_callback_raises(vault, keyring_store):
    keyring_store[(NS, "sa_json")] = "secret_content"
    broker = SecretBroker(vault, NS)
    seen = {}

    def callback(path):
        seen["path"] = path
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        broker.with_secret_tempfile("sa_json", callback)

    assert not seen["path"].exists()


def test_tempfile_missing_secret_returns_none_without_calling_back(vault, keyring_store):
    broker = SecretBroker(vault, NS)
    called = []

    result = broker.with_secret_tempfile("missing", lambda path: called.append(path))

    assert result is None
    assert called == []


# --- Fixes from the PR #261 second review round ---

def test_run_redacted_times_out_instead_of_hanging():
    from titan_cli.core.security.execution import run_redacted
    result = run_redacted(["sleep", "5"], timeout=0.2)
    assert result.exit_code == 124
    assert not result.succeeded


def test_run_redacted_devnull_stdin_when_no_input():
    """A tool reading stdin must see EOF, not wait on the parent's terminal."""
    from titan_cli.core.security.execution import run_redacted
    result = run_redacted(["cat"], timeout=5)
    assert result.exit_code == 0
    assert result.stdout == ""


def test_stderr_is_redacted(vault):
    from titan_cli.core.security.execution import run_redacted
    from titan_cli.core.security.redaction import register_secret, REDACTED
    register_secret("stderr-secret-value")
    result = run_redacted(
        ["python3", "-c", "import sys; sys.stderr.write('leak stderr-secret-value here')"]
    )
    assert "stderr-secret-value" not in result.stderr
    assert REDACTED in result.stderr
