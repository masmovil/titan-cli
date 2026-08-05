"""Tests for the declare_ai_usage decorator."""

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
