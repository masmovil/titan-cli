"""Tests for the AIExecutor façade."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from titan_cli.ai.headless_generator import HeadlessGenerator
from titan_cli.ai.models import AIResponse
from titan_cli.ai.router import (
    AIExecutionError,
    AIExecutionSuccess,
    AIProviderType,
    AIRouteDecision,
    AIRoutePolicy,
    AITask,
    declare_ai_usage,
)
from titan_cli.ai.router.executor import DEFAULT_PREFERRED, AIExecutor
from titan_cli.core.interrupt import WorkflowAborted
from titan_cli.ai.router.resolver import AIRouteNeedsInput
from titan_cli.external_cli.adapters.base import HeadlessResponse


@declare_ai_usage(
    task=AITask.COMMIT_MESSAGE,
    preferred=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
    enforces=True,
)
def declared_step():
    """Stand-in for a real step function that declares its routing."""
    return None


class FakeAIClient:
    def __init__(self, response=None, error=None, connection_id="work-litellm"):
        self.connection_id = connection_id
        self._response = response or AIResponse(content="generated text", model="fake-model")
        self._error = error
        self.calls = []

    def generate(self, messages, max_tokens=None, temperature=None):
        self.calls.append((messages, max_tokens, temperature))
        if self._error:
            raise self._error
        return self._response


class FakeAdapter:
    def __init__(self, response=None, error=None, available=True):
        self._response = response or HeadlessResponse(stdout="cli text", stderr="", exit_code=0)
        self._error = error
        self._available = available
        self.calls = []

    def is_available(self):
        return self._available

    def execute(self, prompt, cwd=None, timeout=60, json_schema=None, model=None):
        self.calls.append(
            {
                "prompt": prompt,
                "cwd": cwd,
                "timeout": timeout,
                "json_schema": json_schema,
                "model": model,
            }
        )
        if self._error:
            raise self._error
        return self._response


def _executor(resolution, *, headless=("claude",)):
    """An executor whose resolution is pinned, so tests exercise execution only."""
    executor = AIExecutor(ai_config=None, secrets=None)
    executor.resolver.resolve = lambda **kwargs: resolution  # type: ignore[method-assign]
    executor.availability.available_headless_clis = lambda: [  # type: ignore[method-assign]
        type("Candidate", (), {"identifier": cli, "provider": AIProviderType.CLI_HEADLESS})()
        for cli in headless
    ]
    return executor


# --- policy normalization -------------------------------------------------


def test_policy_read_from_decorated_callable():
    executor = AIExecutor(ai_config=None, secrets=None)
    seen = {}
    executor.resolver.resolve = lambda **kwargs: seen.update(kwargs) or AIRouteNeedsInput(  # type: ignore[method-assign]
        reason="stub"
    )

    executor.resolve(policy=declared_step)

    assert seen["task"] == AITask.COMMIT_MESSAGE
    assert seen["policy"].preferred == [AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS]


def test_policy_object_passed_directly():
    executor = AIExecutor(ai_config=None, secrets=None)
    seen = {}
    executor.resolver.resolve = lambda **kwargs: seen.update(kwargs) or AIRouteNeedsInput(  # type: ignore[method-assign]
        reason="stub"
    )
    policy = AIRoutePolicy(task="custom_task", preferred=[AIProviderType.CLI_HEADLESS])

    executor.resolve(policy=policy)

    assert seen["task"] == "custom_task"
    assert seen["policy"] is policy


def test_policy_synthesized_when_none_given():
    executor = AIExecutor(ai_config=None, secrets=None)
    seen = {}
    executor.resolver.resolve = lambda **kwargs: seen.update(kwargs) or AIRouteNeedsInput(  # type: ignore[method-assign]
        reason="stub"
    )

    executor.resolve(task="ad_hoc_task")

    assert seen["task"] == "ad_hoc_task"
    assert seen["policy"].preferred == DEFAULT_PREFERRED


def test_explicit_task_overrides_declared_task_but_keeps_preferred():
    executor = AIExecutor(ai_config=None, secrets=None)
    seen = {}
    executor.resolver.resolve = lambda **kwargs: seen.update(kwargs) or AIRouteNeedsInput(  # type: ignore[method-assign]
        reason="stub"
    )

    executor.resolve(policy=declared_step, task="secondary_task")

    assert seen["task"] == "secondary_task"
    assert seen["policy"].preferred == [AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS]


def test_undecorated_callable_falls_back_to_default_preferred():
    def plain_step():
        return None

    executor = AIExecutor(ai_config=None, secrets=None)
    seen = {}
    executor.resolver.resolve = lambda **kwargs: seen.update(kwargs) or AIRouteNeedsInput(  # type: ignore[method-assign]
        reason="stub"
    )

    executor.resolve(policy=plain_step, task="fallback_task")

    assert seen["policy"].preferred == DEFAULT_PREFERRED


def test_undecorated_callable_without_task_is_refused():
    def plain_step():
        return None

    executor = AIExecutor(ai_config=None, secrets=None)

    with pytest.raises(ValueError, match="declare_ai_usage"):
        executor.resolve(policy=plain_step)


# --- remote execution -----------------------------------------------------


def test_remote_success_returns_generated_content():
    executor = _executor(
        AIRouteDecision(provider=AIProviderType.REMOTE, connection_id="work-litellm")
    )
    client = FakeAIClient()
    executor.remote_client = lambda decision: client  # type: ignore[method-assign]

    result = executor.generate_text(
        "write a commit message",
        policy=declared_step,
        system_prompt="you are terse",
        max_tokens=256,
        temperature=0.2,
    )

    assert isinstance(result, AIExecutionSuccess)
    assert result.data == "generated text"
    messages, max_tokens, temperature = client.calls[0]
    assert [m.role for m in messages] == ["system", "user"]
    assert (max_tokens, temperature) == (256, 0.2)


def test_remote_exception_becomes_execution_failed():
    executor = _executor(AIRouteDecision(provider=AIProviderType.REMOTE))
    executor.remote_client = lambda decision: FakeAIClient(error=RuntimeError("429 rate limited"))  # type: ignore[method-assign]

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "EXECUTION_FAILED"
    assert "429 rate limited" in result.error_message


def test_remote_without_usable_client_is_provider_unavailable():
    executor = _executor(AIRouteDecision(provider=AIProviderType.REMOTE))
    executor.remote_client = lambda decision: None  # type: ignore[method-assign]

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_UNAVAILABLE"


# --- headless execution ---------------------------------------------------


def test_headless_success_passes_through_execution_options(monkeypatch):
    executor = _executor(
        AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude")
    )
    adapter = FakeAdapter()
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.get_headless_adapter", lambda cli: adapter
    )

    result = executor.generate_text(
        "review this",
        policy=declared_step,
        system_prompt="be strict",
        cwd="/tmp/worktree",
        timeout=42,
        json_schema={"type": "object"},
        model="sonnet",
    )

    assert isinstance(result, AIExecutionSuccess)
    assert result.data == "cli text"
    call = adapter.calls[0]
    assert call["cwd"] == "/tmp/worktree"
    assert call["timeout"] == 42
    assert call["json_schema"] == {"type": "object"}
    assert call["model"] == "sonnet"
    assert call["prompt"].startswith("be strict")


def test_headless_without_a_resolved_cli_never_picks_one(monkeypatch):
    """
    Resolution attaches the configured CLI, so a decision arriving without one is a bug -
    and guessing which of the installed CLIs to run would be choosing for the user.
    """
    executor = _executor(
        AIRouteDecision(provider=AIProviderType.CLI_HEADLESS), headless=("gemini",)
    )

    def fail_if_called(cli):  # pragma: no cover - asserts it is never reached
        raise AssertionError(f"should not have picked a CLI, got '{cli}'")

    monkeypatch.setattr("titan_cli.ai.router.executor.get_headless_adapter", fail_if_called)

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "NO_PROVIDER_AVAILABLE"


def test_headless_without_any_installed_cli_reports_no_provider():
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS), headless=())

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "NO_PROVIDER_AVAILABLE"


def test_headless_nonzero_exit_returns_stderr(monkeypatch):
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude"))
    adapter = FakeAdapter(
        response=HeadlessResponse(stdout="", stderr="model overloaded", exit_code=1)
    )
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.get_headless_adapter", lambda cli: adapter
    )

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "EXECUTION_FAILED"
    assert result.error_message == "model overloaded"
    assert result.details["exit_code"] == 1


def test_headless_exception_becomes_execution_failed(monkeypatch):
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude"))
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.get_headless_adapter",
        lambda cli: FakeAdapter(error=TimeoutError("timed out after 180s")),
    )

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "EXECUTION_FAILED"
    assert "timed out" in result.error_message


def test_headless_missing_binary_is_provider_unavailable(monkeypatch):
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude"))
    adapter = FakeAdapter(available=False)
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.get_headless_adapter",
        lambda cli: adapter,
    )

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_UNAVAILABLE"
    assert "'claude' is not installed" in result.error_message
    assert adapter.calls == []


def test_headless_workflow_aborted_propagates(monkeypatch):
    """
    WorkflowAborted is a BaseException so that quitting the TUI unwinds the
    workflow thread; the executor's `except Exception` must let it through
    instead of converting it into an AIExecutionError.
    """
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude"))
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.get_headless_adapter",
        lambda cli: FakeAdapter(error=WorkflowAborted("app closed mid-call")),
    )

    with pytest.raises(WorkflowAborted):
        executor.generate_text("prompt", policy=declared_step)


def test_unknown_cli_is_provider_unavailable(monkeypatch):
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="nope"))

    def raise_unknown(cli):
        raise ValueError(f"No headless adapter registered for '{cli}'")

    monkeypatch.setattr("titan_cli.ai.router.executor.get_headless_adapter", raise_unknown)

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_UNAVAILABLE"


# --- non-executing resolutions -------------------------------------------


def test_off_reports_ai_disabled_at_info_level():
    executor = _executor(AIRouteDecision(provider=AIProviderType.OFF))

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "AI_DISABLED"
    assert result.log_level == "info"


def test_interactive_cli_is_not_capable_of_one_shot_text():
    executor = _executor(
        AIRouteDecision(provider=AIProviderType.CLI_INTERACTIVE, cli="claude")
    )

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_NOT_CAPABLE"


def test_needs_input_with_candidates_is_provider_unavailable():
    candidate = type("Candidate", (), {"identifier": "claude"})()
    executor = _executor(
        AIRouteNeedsInput(reason="task preference is no longer available", candidates=[candidate])
    )

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_UNAVAILABLE"
    assert result.details["candidates"] == ["claude"]


def test_needs_input_without_candidates_is_no_provider_available():
    executor = _executor(AIRouteNeedsInput(reason="nothing configured", candidates=[]))

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "NO_PROVIDER_AVAILABLE"


# --- observability --------------------------------------------------------


def test_resolved_route_is_logged_with_task_and_identifier(monkeypatch):
    """
    "Did my configured CLI actually run?" must be answerable from the log alone.
    """
    logged = []
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.logger",
        type("L", (), {
            "info": lambda self, event, **kw: logged.append((event, kw)),
            "warning": lambda self, event, **kw: None,
            "error": lambda self, event, **kw: None,
        })(),
    )
    executor = _executor(
        AIRouteDecision(
            provider=AIProviderType.CLI_HEADLESS, cli="claude", reason="task preference"
        )
    )
    adapter = FakeAdapter()
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.get_headless_adapter", lambda cli: adapter
    )

    executor.generate_text("prompt", policy=declared_step)

    events = dict(logged)
    assert events["ai_route_resolved"]["provider"] == AIProviderType.CLI_HEADLESS
    assert events["ai_route_resolved"]["identifier"] == "claude"
    assert events["ai_route_resolved"]["task"] == AITask.COMMIT_MESSAGE
    assert events["ai_headless_execute_ok"]["cli"] == "claude"


def test_unresolved_route_is_logged(monkeypatch):
    logged = []
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.logger",
        type("L", (), {
            "info": lambda self, event, **kw: logged.append((event, kw)),
            "warning": lambda self, event, **kw: None,
            "error": lambda self, event, **kw: None,
        })(),
    )
    executor = _executor(AIRouteNeedsInput(reason="nothing configured", candidates=[]))

    executor.generate_text("prompt", policy=declared_step)

    assert "ai_route_unresolved" in dict(logged)


# --- resolve_generator (agent-based steps) --------------------------------


def test_resolve_generator_returns_the_configured_connection():
    decision = AIRouteDecision(provider=AIProviderType.REMOTE, connection_id="work-litellm")
    executor = _executor(decision)
    client = FakeAIClient()
    executor.remote_client = lambda d: client  # type: ignore[method-assign]

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionSuccess)
    assert result.data is client


def test_resolve_generator_honours_a_cli_preference():
    """An agent runs on whichever transport the user picked - that is the point."""
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude"))

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionSuccess)
    assert isinstance(result.data, HeadlessGenerator)
    assert result.data.adapter.cli_name.value == "claude"


def test_resolve_generator_passes_the_working_directory_to_the_cli():
    """Running in the repo is what lets the model read the code it is discussing."""
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude"))

    result = executor.resolve_generator(policy=declared_step, cwd="/repo", timeout=42)

    assert result.data.cwd == "/repo"
    assert result.data.timeout == 42


def test_resolve_generator_reports_ai_disabled():
    executor = _executor(AIRouteDecision(provider=AIProviderType.OFF))

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "AI_DISABLED"


def test_resolve_generator_refuses_an_interactive_cli():
    """An interactive session captures no output, so an agent has nothing to read."""
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_INTERACTIVE, cli="claude"))

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_NOT_CAPABLE"


def test_resolve_generator_reports_unusable_connection():
    executor = _executor(AIRouteDecision(provider=AIProviderType.REMOTE, connection_id="gone"))
    executor.remote_client = lambda d: None  # type: ignore[method-assign]

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_UNAVAILABLE"


def test_resolve_generator_reports_an_unknown_cli():
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="nope"))

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_UNAVAILABLE"


def test_resolve_generator_reports_a_cli_that_is_not_installed():
    """Better to say so now than to discover it as an exit code a minute in."""
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude"))

    with patch(
        "titan_cli.ai.router.executor.get_headless_adapter",
        return_value=SimpleNamespace(is_available=lambda: False),
    ):
        result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "PROVIDER_UNAVAILABLE"
    assert "claude" in result.error_message


def test_resolve_generator_refuses_a_headless_decision_with_no_cli():
    executor = _executor(AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli=None))

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "NO_PROVIDER_AVAILABLE"


def test_resolve_generator_surfaces_needs_input():
    executor = _executor(AIRouteNeedsInput(reason="nothing configured", candidates=[]))

    result = executor.resolve_generator(policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "NO_PROVIDER_AVAILABLE"


# --- remote_client --------------------------------------------------------


def test_remote_client_caches_per_connection(monkeypatch):
    from titan_cli.core.models import AIConfig

    built = []

    class RecordingClient:
        def __init__(self, ai_config, secrets, connection_id=None):
            built.append(connection_id)
            self.connection_id = connection_id

    monkeypatch.setattr("titan_cli.ai.router.executor.AIClient", RecordingClient)
    executor = AIExecutor(ai_config=AIConfig(), secrets=object())

    first = executor.remote_client(AIRouteDecision(provider=AIProviderType.REMOTE, connection_id="a"))
    second = executor.remote_client(AIRouteDecision(provider=AIProviderType.REMOTE, connection_id="a"))
    third = executor.remote_client(AIRouteDecision(provider=AIProviderType.REMOTE, connection_id="b"))

    assert first is second
    assert third is not first
    assert built == ["a", "b"]


def test_remote_client_without_config_returns_none():
    executor = AIExecutor(ai_config=None, secrets=None)

    assert executor.remote_client(AIRouteDecision(provider=AIProviderType.REMOTE)) is None


def test_remote_client_returns_none_when_connection_misconfigured(monkeypatch):
    from titan_cli.ai.exceptions import AIConfigurationError
    from titan_cli.core.models import AIConfig

    def raise_config_error(ai_config, secrets, connection_id=None):
        raise AIConfigurationError("no such connection")

    monkeypatch.setattr("titan_cli.ai.router.executor.AIClient", raise_config_error)
    executor = AIExecutor(ai_config=AIConfig(), secrets=object())

    assert executor.remote_client(AIRouteDecision(provider=AIProviderType.REMOTE)) is None


# --- announcing the route to the user -------------------------------------


def test_announce_names_the_provider_and_instance(monkeypatch):
    """Watching a run should be enough to notice the wrong AI answered."""
    executor = _executor(
        AIRouteDecision(provider=AIProviderType.CLI_HEADLESS, cli="claude", reason="pref")
    )
    monkeypatch.setattr(
        "titan_cli.ai.router.executor.get_headless_adapter", lambda cli: FakeAdapter()
    )
    said = []

    executor.generate_text("prompt", policy=declared_step, announce=said.append)

    assert said == ["claude · CLI, automatic"]


def test_announce_says_when_the_task_is_off():
    executor = _executor(AIRouteDecision(provider=AIProviderType.OFF, reason="pref"))
    said = []

    executor.generate_text("prompt", policy=declared_step, announce=said.append)

    assert said == ["AI is off for this task"]


def test_nothing_is_announced_when_the_route_cannot_be_resolved():
    """An unresolved route already returns an error explaining itself."""
    executor = _executor(AIRouteNeedsInput(reason="no default CLI is configured"))
    said = []

    result = executor.generate_text("prompt", policy=declared_step, announce=said.append)

    assert isinstance(result, AIExecutionError)
    assert said == []


def test_announce_is_optional():
    """Steps that say it themselves - or say nothing - must keep working."""
    executor = _executor(AIRouteDecision(provider=AIProviderType.OFF, reason="pref"))

    result = executor.generate_text("prompt", policy=declared_step)

    assert isinstance(result, AIExecutionError)
    assert result.error_code == "AI_DISABLED"
