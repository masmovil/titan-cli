"""
Tests for AIRouteResolver's three-level precedence chain:
runtime override -> persisted task preference -> the step's declared default.

A preference names only a KIND of provider; which connection or CLI serves it comes from the
global defaults, so most of these also assert that the resolved decision names the instance
that will actually run.
"""

import pytest

from titan_cli.ai.router import (
    AIProviderType,
    AIRouteDecision,
    AIRouteNeedsInput,
    AIRoutePolicy,
    AIRouteResolver,
)
from titan_cli.ai.router.availability import AIProviderAvailability
from titan_cli.core.models import (
    AIConfig,
    AIConnectionConfig,
    AIConnectionType,
    AIGatewayBackend,
    AIPreferences,
    AIProviderPreference,
)


class FakeAvailability:
    """Availability checker stub driven by explicit identifier lists."""

    def __init__(self, remote=(), headless=(), interactive=()):
        self._remote = list(remote)
        self._headless = list(headless)
        self._interactive = list(interactive)

    def available_remote_connections(self):
        return [
            AIProviderAvailability(provider=AIProviderType.REMOTE, identifier=i) for i in self._remote
        ]

    def available_headless_clis(self):
        return [
            AIProviderAvailability(provider=AIProviderType.CLI_HEADLESS, identifier=i)
            for i in self._headless
        ]

    def available_interactive_clis(self):
        return [
            AIProviderAvailability(provider=AIProviderType.CLI_INTERACTIVE, identifier=i)
            for i in self._interactive
        ]

    def is_provider_available(self, provider):
        if provider == AIProviderType.REMOTE:
            return bool(self._remote)
        if provider == AIProviderType.CLI_HEADLESS:
            return bool(self._headless)
        if provider == AIProviderType.CLI_INTERACTIVE:
            return bool(self._interactive)
        if provider == AIProviderType.OFF:
            return True
        return False


def _connection(name: str) -> AIConnectionConfig:
    return AIConnectionConfig(
        name=name,
        connection_type=AIConnectionType.GATEWAY,
        gateway_backend=AIGatewayBackend.OPENAI_COMPATIBLE,
        base_url="https://example.invalid",
    )


def _config(
    *,
    default_connection: str = "work-litellm",
    default_cli: str = "claude",
    **task_preferences,
) -> AIConfig:
    """Build an AIConfig with global defaults and type-only task preferences."""
    return AIConfig(
        default_connection=default_connection,
        default_cli=default_cli,
        connections={default_connection: _connection(default_connection)}
        if default_connection
        else {},
        preferences=AIPreferences(
            tasks={
                task: AIProviderPreference(provider=provider)
                for task, provider in task_preferences.items()
            }
        ),
    )


@pytest.fixture
def availability():
    return FakeAvailability(remote=["work-litellm"], headless=["claude"], interactive=["claude"])


def test_runtime_override_wins_over_persisted_preference(availability):
    resolver = AIRouteResolver(_config(commit_message="remote"), availability)

    decision = resolver.resolve(
        task="commit_message", runtime_override=AIProviderType.CLI_HEADLESS
    )

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.CLI_HEADLESS
    assert decision.cli == "claude"


def test_unavailable_runtime_override_needs_input():
    resolver = AIRouteResolver(_config(), FakeAvailability(remote=["work-litellm"]))

    resolution = resolver.resolve(
        task="commit_message", runtime_override=AIProviderType.CLI_HEADLESS
    )

    assert isinstance(resolution, AIRouteNeedsInput)


def test_task_preference_wins_over_declared_default(availability):
    resolver = AIRouteResolver(_config(commit_message="cli_headless"), availability)
    policy = AIRoutePolicy(task="commit_message", preferred=[AIProviderType.REMOTE])

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.CLI_HEADLESS
    assert decision.cli == "claude"


def test_declared_default_used_when_nothing_persisted(availability):
    resolver = AIRouteResolver(_config(), availability)
    policy = AIRoutePolicy(
        task="commit_message",
        preferred=[AIProviderType.CLI_HEADLESS, AIProviderType.REMOTE],
    )

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.CLI_HEADLESS
    assert decision.cli == "claude"


def test_declared_default_skips_unavailable_provider_types():
    resolver = AIRouteResolver(_config(), FakeAvailability(remote=["work-litellm"]))
    policy = AIRoutePolicy(
        task="commit_message",
        preferred=[AIProviderType.CLI_HEADLESS, AIProviderType.REMOTE],
    )

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.REMOTE
    assert decision.connection_id == "work-litellm"


def test_no_preference_and_no_available_default_needs_input(availability):
    resolver = AIRouteResolver(_config(), availability)

    resolution = resolver.resolve(task="commit_message")

    assert isinstance(resolution, AIRouteNeedsInput)
    assert [c.identifier for c in resolution.candidates] == ["work-litellm", "claude", "claude"]


class TestGlobalInstanceResolution:
    """Which connection/CLI runs a task is a single global setting, not part of the preference."""

    def test_configured_default_cli_that_is_gone_never_swaps_to_another(self):
        """The one installed CLI is not silently substituted for the configured one."""
        resolver = AIRouteResolver(
            _config(default_cli="gemini", commit_message="cli_headless"),
            FakeAvailability(headless=["claude"]),
        )

        resolution = resolver.resolve(task="commit_message")

        assert isinstance(resolution, AIRouteNeedsInput)
        assert "gemini" in resolution.reason
        assert "not available" in resolution.reason

    def test_no_default_cli_configured_says_so(self):
        resolver = AIRouteResolver(
            _config(default_cli=None, commit_message="cli_headless"),
            FakeAvailability(headless=["claude"]),
        )

        resolution = resolver.resolve(task="commit_message")

        assert isinstance(resolution, AIRouteNeedsInput)
        assert "no default CLI is configured" in resolution.reason

    def test_no_default_connection_configured_says_so(self):
        resolver = AIRouteResolver(
            _config(default_connection=None, commit_message="remote"),
            FakeAvailability(remote=["work-litellm"]),
        )

        resolution = resolver.resolve(task="commit_message")

        assert isinstance(resolution, AIRouteNeedsInput)
        assert "no default AI connection is configured" in resolution.reason

    def test_changing_the_global_default_changes_every_task_using_that_kind(self):
        """The point of a single global instance: one edit, not one per task."""
        availability = FakeAvailability(headless=["claude", "gemini"])
        config = _config(default_cli="claude", commit_message="cli_headless", slack_summary="cli_headless")
        resolver = AIRouteResolver(config, availability)

        assert resolver.resolve(task="commit_message").cli == "claude"
        assert resolver.resolve(task="slack_summary").cli == "claude"

        config.default_cli = "gemini"

        assert resolver.resolve(task="commit_message").cli == "gemini"
        assert resolver.resolve(task="slack_summary").cli == "gemini"

    def test_a_missing_cli_default_is_reported_even_for_a_declared_default(self):
        """The step-default path reports the real obstacle, not a generic failure."""
        resolver = AIRouteResolver(
            _config(default_cli=None),
            FakeAvailability(interactive=["claude"]),
        )
        policy = AIRoutePolicy(
            task="generic_assistant", preferred=[AIProviderType.CLI_INTERACTIVE]
        )

        resolution = resolver.resolve(task="generic_assistant", policy=policy)

        assert isinstance(resolution, AIRouteNeedsInput)
        assert "no default CLI is configured" in resolution.reason

    def test_first_obstacle_wins_when_every_declared_default_fails(self):
        """With several failing candidates, the reason surfaced is the first one hit."""
        resolver = AIRouteResolver(
            _config(default_cli=None, default_connection=None),
            FakeAvailability(),
        )
        policy = AIRoutePolicy(
            task="generic_assistant",
            preferred=[AIProviderType.CLI_HEADLESS, AIProviderType.REMOTE],
        )

        resolution = resolver.resolve(task="generic_assistant", policy=policy)

        assert isinstance(resolution, AIRouteNeedsInput)
        assert "no default CLI is configured" in resolution.reason
        assert "connection" not in resolution.reason


def test_off_preference_resolves_to_off(availability):
    resolver = AIRouteResolver(_config(commit_message="off"), availability)

    decision = resolver.resolve(task="commit_message")

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.OFF


def test_off_needs_no_configured_instance():
    """Turning a task off must work even with nothing else configured."""
    resolver = AIRouteResolver(
        _config(default_connection=None, default_cli=None, commit_message="off"),
        FakeAvailability(),
    )

    decision = resolver.resolve(task="commit_message")

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.OFF


def test_unknown_provider_value_is_reported_not_silently_replaced(availability):
    """
    A typo'd or schema-stale stored preference must surface by name instead of
    silently falling through to the step's defaults.
    """
    resolver = AIRouteResolver(_config(commit_message="carrier_pigeon"), availability)
    policy = AIRoutePolicy(task="commit_message", preferred=[AIProviderType.REMOTE])

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteNeedsInput)
    assert "carrier_pigeon" in decision.reason
    assert "commit_message" in decision.reason


def test_leftover_instance_keys_in_a_stored_preference_are_ignored(availability):
    """
    A preference written before instances moved to global settings must resolve from the
    global defaults, not from the stale instance it still carries on disk.
    """
    preferences = AIPreferences.model_validate(
        {"tasks": {"commit_message": {"provider": "cli_headless", "cli": "gemini"}}}
    )
    assert not hasattr(preferences.tasks["commit_message"], "cli")

    config = _config(default_cli="claude")
    config.preferences = preferences
    resolver = AIRouteResolver(config, availability)

    decision = resolver.resolve(task="commit_message")

    assert isinstance(decision, AIRouteDecision)
    assert decision.cli == "claude"


def test_leftover_workflow_scope_in_config_has_no_effect(availability):
    """
    A config written before the workflow scope was removed must resolve exactly
    as if that section were absent - the task is the only scope.
    """
    preferences = AIPreferences.model_validate(
        {
            "tasks": {},
            "workflows": {
                "Commit with AI, Linter and Tests": {
                    "provider": "cli_headless",
                    "cli": "gemini",
                }
            },
        }
    )
    assert not hasattr(preferences, "workflows")

    config = _config()
    config.preferences = preferences
    resolver = AIRouteResolver(config, availability)
    policy = AIRoutePolicy(task="commit_message", preferred=[AIProviderType.REMOTE])

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.REMOTE


def test_persisted_preference_outside_executes_is_refused(availability):
    """
    A preference the step's code can't run must be refused by name, not handed
    over to fail later and further from the cause.
    """
    resolver = AIRouteResolver(_config(generic_assistant="remote"), availability)
    policy = AIRoutePolicy(
        task="generic_assistant",
        executes=[AIProviderType.CLI_INTERACTIVE],
        preferred=[AIProviderType.CLI_INTERACTIVE],
    )

    resolution = resolver.resolve(task="generic_assistant", policy=policy)

    assert isinstance(resolution, AIRouteNeedsInput)
    assert "cannot run" in resolution.reason


def test_runtime_override_outside_executes_is_refused(availability):
    """
    A runtime override comes from a caller that never consulted `executes`,
    so it gets the same guard as a persisted preference: refused by name
    rather than handed to a step that can't drive it.
    """
    resolver = AIRouteResolver(_config(), availability)
    policy = AIRoutePolicy(
        task="generic_assistant",
        executes=[AIProviderType.CLI_INTERACTIVE],
        preferred=[AIProviderType.CLI_INTERACTIVE],
    )

    resolution = resolver.resolve(
        task="generic_assistant",
        policy=policy,
        runtime_override=AIProviderType.REMOTE,
    )

    assert isinstance(resolution, AIRouteNeedsInput)
    assert "cannot run" in resolution.reason
    assert "requested" in resolution.reason


def test_off_preference_passes_the_executes_guard(availability):
    """Any step can skip - 'off' is honored regardless of executes."""
    resolver = AIRouteResolver(_config(generic_assistant="off"), availability)
    policy = AIRoutePolicy(
        task="generic_assistant", executes=[AIProviderType.CLI_INTERACTIVE]
    )

    decision = resolver.resolve(task="generic_assistant", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.OFF


def test_preference_within_executes_passes_the_guard(availability):
    resolver = AIRouteResolver(_config(commit_message="cli_headless"), availability)
    policy = AIRoutePolicy(
        task="commit_message",
        executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
        preferred=[AIProviderType.REMOTE],
    )

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.cli == "claude"


def test_no_declared_executes_means_no_guard(availability):
    """Steps that declare nothing keep the old behavior - no filtering."""
    resolver = AIRouteResolver(_config(thread_resolution="remote"), availability)

    decision = resolver.resolve(task="thread_resolution")

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.REMOTE


def test_missing_ai_config_needs_input():
    resolver = AIRouteResolver(None, FakeAvailability())

    resolution = resolver.resolve(task="commit_message")

    assert isinstance(resolution, AIRouteNeedsInput)
    assert resolution.candidates == []
