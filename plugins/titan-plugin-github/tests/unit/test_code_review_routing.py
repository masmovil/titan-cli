"""
Routing tests for the code-review steps.

These steps run a headless CLI themselves (their own timeouts, structured output,
tool restrictions and batching), so they resolve WHO runs them through the façade
and keep their own execution. What is pinned here is that resolution: the user's
per-task preference decides the CLI, and every way it can fail comes back with a
reason instead of a silent swap.
"""

from unittest.mock import Mock

import pytest

from titan_cli.ai.router.enums import AIProviderType, AITask
from titan_cli.ai.router.executor import AIExecutor
from titan_cli.ai.router.availability import AIProviderAvailability
from titan_cli.core.models import (
    AIConfig,
    AIConnectionConfig,
    AIConnectionType,
    AIDirectProvider,
    AIPreferences,
    AIProviderPreference,
)
from titan_cli.engine import WorkflowContext
import titan_plugin_github.steps.code_review_steps as code_review_steps
from titan_plugin_github.steps.code_review_steps import (
    ai_review_findings,
    ai_review_plan,
    ai_thread_resolution,
    verify_findings,
)


class _FakeAdapter:
    """Stand-in for a headless adapter — only its identity matters here."""

    def __init__(self, cli_name="claude"):
        self.cli_name = cli_name


def _executor(
    *,
    task_preferences=None,
    default_cli="claude",
    installed=("claude", "gemini"),
    default_connection="work-llm",
) -> AIExecutor:
    """
    A real executor (real resolver) with availability pinned.

    Availability is primed rather than probed so a test never depends on which
    CLIs the machine running it happens to have installed.
    """
    connection = AIConnectionConfig(
        name="Test connection",
        connection_type=AIConnectionType.DIRECT_PROVIDER,
        provider=AIDirectProvider.ANTHROPIC,
    )
    config = AIConfig(
        default_connection=default_connection,
        default_cli=default_cli,
        connections={default_connection: connection} if default_connection else {},
        preferences=AIPreferences(tasks=task_preferences or {}),
    )
    executor = AIExecutor(ai_config=config, secrets=None)
    executor.availability._cache["headless"] = [
        AIProviderAvailability(provider=AIProviderType.CLI_HEADLESS, identifier=cli)
        for cli in installed
    ]
    executor.availability._cache["interactive"] = []
    executor.availability._cache["remote"] = (
        [AIProviderAvailability(provider=AIProviderType.REMOTE, identifier=default_connection)]
        if default_connection
        else []
    )
    return executor


def _ctx(executor) -> WorkflowContext:
    ctx = WorkflowContext(secrets=Mock())
    ctx.ai_router = executor
    return ctx


@pytest.fixture(autouse=True)
def stub_adapter_lookup(monkeypatch):
    """Resolve a CLI name to a fake adapter instead of a real installed binary."""
    monkeypatch.setattr(
        code_review_steps,
        "_resolve_headless_adapter",
        lambda cli: _FakeAdapter(cli) if cli in ("auto", "claude", "gemini") else None,
    )


# --- the configured CLI is used -------------------------------------------


@pytest.mark.parametrize(
    "step",
    [ai_review_plan, ai_review_findings, verify_findings, ai_thread_resolution],
)
def test_every_review_step_uses_the_global_default_cli(step):
    adapter, note = code_review_steps._resolve_review_adapter(_ctx(_executor()), step)

    assert adapter.cli_name == "claude"
    assert note is None


def test_a_task_preference_for_a_cli_is_honored_over_nothing():
    executor = _executor(
        task_preferences={
            AITask.CODE_REVIEW_FINDINGS: AIProviderPreference(provider=AIProviderType.CLI_HEADLESS)
        },
        default_cli="gemini",
    )

    adapter, note = code_review_steps._resolve_review_adapter(_ctx(executor), ai_review_findings)

    assert adapter.cli_name == "gemini"
    assert note is None


def test_findings_and_verification_share_one_task_setting():
    """verify_findings is part of the findings pass, so one preference governs both."""
    executor = _executor(default_cli="gemini")

    findings_adapter, _ = code_review_steps._resolve_review_adapter(
        _ctx(executor), ai_review_findings
    )
    verify_adapter, _ = code_review_steps._resolve_review_adapter(_ctx(executor), verify_findings)

    assert findings_adapter.cli_name == verify_adapter.cli_name == "gemini"


# --- every failure names its reason ---------------------------------------


def test_off_reports_that_the_task_is_disabled():
    executor = _executor(
        task_preferences={AITask.CODE_REVIEW_PLAN: AIProviderPreference(provider=AIProviderType.OFF)}
    )

    adapter, note = code_review_steps._resolve_review_adapter(_ctx(executor), ai_review_plan)

    assert adapter is None
    assert "turned off" in note


def test_a_remote_preference_is_refused_by_name_not_silently_run_on_a_cli():
    """A leftover 'remote' preference predates these steps declaring CLI-only."""
    executor = _executor(
        task_preferences={
            AITask.CODE_REVIEW_FINDINGS: AIProviderPreference(provider=AIProviderType.REMOTE)
        }
    )

    adapter, note = code_review_steps._resolve_review_adapter(_ctx(executor), ai_review_findings)

    assert adapter is None
    assert "remote" in note
    assert "AI Configuration" in note


def test_no_default_cli_configured_says_so():
    executor = _executor(default_cli=None)

    adapter, note = code_review_steps._resolve_review_adapter(_ctx(executor), ai_review_plan)

    assert adapter is None
    assert "no default CLI is configured" in note


def test_a_configured_cli_that_is_not_installed_is_named():
    executor = _executor(default_cli="codex", installed=("claude",))

    adapter, note = code_review_steps._resolve_review_adapter(_ctx(executor), ai_review_plan)

    assert adapter is None
    assert "codex" in note


def test_no_router_keeps_the_first_available_cli_behavior():
    """A step called without the façade wired (outside a workflow run)."""
    adapter, note = code_review_steps._resolve_review_adapter(WorkflowContext(secrets=Mock()), ai_review_plan)

    assert adapter.cli_name == "auto"
    assert note is None


# --- the declarations the preferences screen reads ------------------------


@pytest.mark.parametrize(
    "step, task",
    [
        (ai_review_plan, AITask.CODE_REVIEW_PLAN),
        (ai_review_findings, AITask.CODE_REVIEW_FINDINGS),
        (verify_findings, AITask.CODE_REVIEW_FINDINGS),
        (ai_thread_resolution, "thread_resolution"),
    ],
)
def test_steps_declare_cli_only_and_enforce_it(step, task):
    assert step.ai_policy.task == task
    assert step.ai_policy.executes == [AIProviderType.CLI_HEADLESS]
    assert step.ai_enforces is True
