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


# Names and explanations for humans. They live beside the enum, not in the screen that
# renders them, so the configuration screen and a running step call the same thing by the
# same name. The names describe WHO DRIVES rather than how it is wired: "headless" is an
# implementation word, and what a user actually needs to know is whether Titan runs the tool
# and keeps the answer, or hands them the terminal.
PROVIDER_TYPE_LABELS = {
    AIProviderType.REMOTE: "Remote model",
    AIProviderType.CLI_HEADLESS: "CLI, automatic",
    AIProviderType.CLI_INTERACTIVE: "CLI, interactive",
    AIProviderType.OFF: "Off",
}

PROVIDER_TYPE_DESCRIPTIONS = {
    AIProviderType.REMOTE: (
        "Sends the prompt to your AI connection. Fastest, but it cannot see your files."
    ),
    AIProviderType.CLI_HEADLESS: (
        "Titan runs your CLI in the background and keeps its answer. "
        "Slower, but it can read your repo."
    ),
    AIProviderType.CLI_INTERACTIVE: (
        "Opens your CLI so you work in it, then returns to Titan. "
        "For fixing things, not for producing text."
    ),
    AIProviderType.OFF: "Skip this task entirely.",
}


def provider_label(provider: AIProviderType) -> str:
    """A readable name for a provider type."""
    return PROVIDER_TYPE_LABELS.get(provider, str(provider))


def provider_description(provider: AIProviderType) -> str:
    """A one-line explanation of what choosing this provider type means."""
    return PROVIDER_TYPE_DESCRIPTIONS.get(provider, "")


__all__ = [
    "AITask",
    "AIProviderType",
    "PROVIDER_TYPE_LABELS",
    "PROVIDER_TYPE_DESCRIPTIONS",
    "provider_label",
    "provider_description",
]
