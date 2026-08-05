"""Tests for the declare_ai_usage decorator."""

import pytest

from titan_cli.ai.router import (
    AIProviderType,
    AITask,
    declare_ai_usage,
    declared_ai_usage_enforces,
    get_declared_ai_policy,
)


def test_declaration_stashes_policy_without_wrapping():
    @declare_ai_usage(task=AITask.COMMIT_MESSAGE, preferred=[AIProviderType.REMOTE])
    def step(value):
        return value * 2

    # The function itself is returned untouched - no wrapper.
    assert step(3) == 6
    assert step.__name__ == "step"

    policy = get_declared_ai_policy(step)
    assert policy is not None
    assert policy.task == AITask.COMMIT_MESSAGE
    assert policy.preferred == [AIProviderType.REMOTE]


def test_declaration_defaults_to_empty_preferred_and_not_enforcing():
    @declare_ai_usage(task="community_task")
    def step():
        return None

    policy = get_declared_ai_policy(step)
    assert policy.task == "community_task"
    assert policy.preferred == []
    assert declared_ai_usage_enforces(step) is False


def test_declaration_records_enforcement_claim():
    @declare_ai_usage(task=AITask.GENERIC_ASSISTANT, enforces=True)
    def step():
        return None

    assert declared_ai_usage_enforces(step) is True


def test_undeclared_function_has_no_policy():
    def step():
        return None

    assert get_declared_ai_policy(step) is None
    assert declared_ai_usage_enforces(step) is False


def test_executes_defaults_to_preferred_when_they_coincide():
    """The common case declares one list and gets both meanings."""

    @declare_ai_usage(task="t", preferred=[AIProviderType.REMOTE])
    def step():
        return None

    policy = get_declared_ai_policy(step)
    assert policy.executes == [AIProviderType.REMOTE]
    assert policy.preferred == [AIProviderType.REMOTE]


def test_preferred_defaults_to_executes_order():
    @declare_ai_usage(
        task="t", executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS]
    )
    def step():
        return None

    policy = get_declared_ai_policy(step)
    assert policy.preferred == [AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS]


def test_can_run_more_than_it_defaults_to():
    """A step that CAN use a CLI but should default to remote declares both."""

    @declare_ai_usage(
        task="t",
        executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
        preferred=[AIProviderType.REMOTE],
    )
    def step():
        return None

    policy = get_declared_ai_policy(step)
    assert policy.executes == [AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS]
    assert policy.preferred == [AIProviderType.REMOTE]


def test_defaulting_to_something_unexecutable_fails_at_import_time():
    with pytest.raises(ValueError, match="not in executes"):

        @declare_ai_usage(
            task="t",
            executes=[AIProviderType.REMOTE],
            preferred=[AIProviderType.CLI_HEADLESS],
        )
        def step():
            return None
