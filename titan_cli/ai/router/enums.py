"""
Enums for the AI execution routing layer.

Vocabulary the routing layer is built on: an AI task (what the step wants
done) is routed to an execution provider (who does it), optionally pinned by
a persisted user preference.
"""

from enum import StrEnum


class AITask(StrEnum):
    """
    Recommended task vocabulary for official plugins.

    `AIRoutePolicy.task` is a plain `str`, not this enum, so community plugins
    can identify their own tasks (used as routing and preference-persistence
    keys) without needing a core code change. These members are the known
    values official plugins should reuse.
    """

    COMMIT_MESSAGE = "commit_message"
    PR_DESCRIPTION = "pr_description"
    ISSUE_GENERATION = "issue_generation"
    JIRA_ANALYSIS = "jira_analysis"
    CODE_REVIEW_PLAN = "code_review_plan"
    CODE_REVIEW_FINDINGS = "code_review_findings"
    RESPOND_PR_COMMENT = "respond_pr_comment"
    FIX_TEST_FAILURES = "fix_test_failures"
    FIX_LINT_FAILURES = "fix_lint_failures"
    GENERIC_ASSISTANT = "generic_assistant"


class AIProviderType(StrEnum):
    """Execution provider that can fulfill an AI task."""

    REMOTE = "remote"
    CLI_HEADLESS = "cli_headless"
    CLI_INTERACTIVE = "cli_interactive"
    OFF = "off"


__all__ = [
    "AITask",
    "AIProviderType",
]
