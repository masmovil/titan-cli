"""
Tests for AIRouteResolver's three-level precedence chain:
runtime override -> persisted task preference -> the step's declared default.
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
from titan_cli.core.models import AIConfig, AIPreferences, AIProviderPreference


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


def _config(**task_preferences) -> AIConfig:
    return AIConfig(
        preferences=AIPreferences(
            tasks={
                task: AIProviderPreference(**pref) for task, pref in task_preferences.items()
            }
        )
    )


@pytest.fixture
def availability():
    return FakeAvailability(remote=["work-litellm"], headless=["claude"], interactive=["claude"])


def test_runtime_override_wins_over_persisted_preference(availability):
    resolver = AIRouteResolver(
        _config(commit_message={"provider": "remote", "connection_id": "work-litellm"}),
        availability,
    )

    decision = resolver.resolve(
        task="commit_message", runtime_override=AIProviderType.CLI_HEADLESS
    )

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.CLI_HEADLESS


def test_unavailable_runtime_override_needs_input(availability):
    resolver = AIRouteResolver(_config(), FakeAvailability(remote=["work-litellm"]))

    resolution = resolver.resolve(
        task="commit_message", runtime_override=AIProviderType.CLI_HEADLESS
    )

    assert isinstance(resolution, AIRouteNeedsInput)


def test_task_preference_wins_over_declared_default(availability):
    resolver = AIRouteResolver(
        _config(commit_message={"provider": "cli_headless", "cli": "claude"}),
        availability,
    )
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


def test_declared_default_skips_unavailable_provider_types():
    resolver = AIRouteResolver(_config(), FakeAvailability(remote=["work-litellm"]))
    policy = AIRoutePolicy(
        task="commit_message",
        preferred=[AIProviderType.CLI_HEADLESS, AIProviderType.REMOTE],
    )

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.REMOTE


def test_no_preference_and_no_available_default_needs_input(availability):
    resolver = AIRouteResolver(_config(), availability)

    resolution = resolver.resolve(task="commit_message")

    assert isinstance(resolution, AIRouteNeedsInput)
    assert [c.identifier for c in resolution.candidates] == ["work-litellm", "claude", "claude"]


def test_preference_for_unavailable_exact_cli_needs_input_without_swapping():
    """A remembered CLI that vanished must not silently become a different CLI."""
    resolver = AIRouteResolver(
        _config(commit_message={"provider": "cli_headless", "cli": "gemini"}),
        FakeAvailability(headless=["claude"]),
    )

    resolution = resolver.resolve(task="commit_message")

    assert isinstance(resolution, AIRouteNeedsInput)
    assert "no longer available" in resolution.reason


def test_off_preference_resolves_to_off(availability):
    resolver = AIRouteResolver(_config(commit_message={"provider": "off"}), availability)

    decision = resolver.resolve(task="commit_message")

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.OFF


def test_unknown_provider_value_falls_through_to_declared_default(availability):
    resolver = AIRouteResolver(
        _config(commit_message={"provider": "carrier_pigeon"}),
        availability,
    )
    policy = AIRoutePolicy(task="commit_message", preferred=[AIProviderType.REMOTE])

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.REMOTE


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

    resolver = AIRouteResolver(AIConfig(preferences=preferences), availability)
    policy = AIRoutePolicy(task="commit_message", preferred=[AIProviderType.REMOTE])

    decision = resolver.resolve(task="commit_message", policy=policy)

    assert isinstance(decision, AIRouteDecision)
    assert decision.provider == AIProviderType.REMOTE


def test_missing_ai_config_needs_input():
    resolver = AIRouteResolver(None, FakeAvailability())

    resolution = resolver.resolve(task="commit_message")

    assert isinstance(resolution, AIRouteNeedsInput)
    assert resolution.candidates == []
