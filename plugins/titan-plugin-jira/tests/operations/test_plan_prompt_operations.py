"""
Tests for Plan Prompt Operations

Tests for pure business logic that builds the AI prompt used to plan JIRA issue work.
"""

from titan_plugin_jira.models.view import UIJiraComment, UIJiraIssue
from titan_plugin_jira.operations.plan_prompt_operations import (
    format_jira_issue_context,
    build_jira_plan_prompt,
)


def _make_issue(**overrides):
    defaults = dict(
        key="TEST-123",
        id="10123",
        summary="Sample test issue",
        description="This is a test issue description",
        status="In Progress",
        status_icon="🔵",
        status_category="In Progress",
        issue_type="Bug",
        issue_type_icon="🐛",
        assignee="John Doe",
        assignee_email="john.doe@example.com",
        reporter="Jane Doe",
        priority="High",
        priority_icon="🔴",
        formatted_created_at="01/01/2025 12:00:00",
        formatted_updated_at="02/01/2025 12:00:00",
        labels=[],
        components=[],
        fix_versions=[],
        is_subtask=False,
        parent_key=None,
        subtask_count=0,
    )
    defaults.update(overrides)
    return UIJiraIssue(**defaults)


def _make_comment(**overrides):
    defaults = dict(
        id="1",
        author_name="Alice",
        author_email="alice@example.com",
        body="This needs a closer look.",
        formatted_created_at="01/01/2025 12:00:00",
        formatted_updated_at=None,
    )
    defaults.update(overrides)
    return UIJiraComment(**defaults)


class TestFormatJiraIssueContext:
    """Tests for format_jira_issue_context function."""

    def test_includes_core_issue_fields(self):
        issue = _make_issue()

        result = format_jira_issue_context(issue, [])

        assert "TEST-123: Sample test issue" in result
        assert "Type: Bug" in result
        assert "Status: In Progress" in result
        assert "Priority: High" in result
        assert "Assignee: John Doe" in result
        assert "Reporter: Jane Doe" in result
        assert "This is a test issue description" in result

    def test_includes_optional_fields_when_present(self):
        issue = _make_issue(
            labels=["backend", "urgent"],
            components=["API"],
            fix_versions=["v2.0.0"],
            is_subtask=True,
            parent_key="TEST-100",
        )

        result = format_jira_issue_context(issue, [])

        assert "Labels: backend, urgent" in result
        assert "Components: API" in result
        assert "Fix versions: v2.0.0" in result
        assert "Parent issue: TEST-100" in result

    def test_omits_optional_fields_when_absent(self):
        issue = _make_issue()

        result = format_jira_issue_context(issue, [])

        assert "Labels:" not in result
        assert "Components:" not in result
        assert "Fix versions:" not in result
        assert "Parent issue:" not in result

    def test_no_comments_shows_placeholder(self):
        issue = _make_issue()

        result = format_jira_issue_context(issue, [])

        assert "Comments (0)" in result
        assert "No comments." in result

    def test_comments_are_rendered_in_order(self):
        issue = _make_issue()
        comments = [
            _make_comment(author_name="Alice", body="First comment"),
            _make_comment(author_name="Bob", body="Second comment"),
        ]

        result = format_jira_issue_context(issue, comments)

        assert "Comments (2)" in result
        assert result.index("Alice") < result.index("Bob")
        assert "First comment" in result
        assert "Second comment" in result

    def test_falls_back_to_no_description(self):
        issue = _make_issue(description="")

        result = format_jira_issue_context(issue, [])

        assert "No description" in result


class TestBuildJiraPlanPrompt:
    """Tests for build_jira_plan_prompt function."""

    def test_embeds_issue_context_in_instructions(self):
        issue = _make_issue()
        comments = [_make_comment()]

        prompt = build_jira_plan_prompt(issue, comments)

        # Instructional wrapper is present
        assert "PLANNING ONLY" in prompt
        assert "confirm" in prompt.lower()
        # Issue context is embedded
        assert "TEST-123: Sample test issue" in prompt
        assert "This needs a closer look." in prompt

    def test_does_not_start_implementing_before_confirmation(self):
        issue = _make_issue()

        prompt = build_jira_plan_prompt(issue, [])

        assert "Do not start implementing until the user has confirmed the plan" in prompt
