"""
Operations for building the AI prompt used to plan work for a JIRA issue.
"""

from typing import List

from ..constants import JIRA_PLAN_PROMPT_TEMPLATE
from ..models.view import UIJiraComment, UIJiraIssue


def format_jira_issue_context(issue: UIJiraIssue, comments: List[UIJiraComment]) -> str:
    """
    Format a JIRA issue and its comments into a single markdown text block.

    Args:
        issue: The issue details
        comments: The issue's comments, in display order

    Returns:
        Formatted markdown combining the issue's fields, description and comments
    """
    lines = [
        f"# {issue.key}: {issue.summary}",
        "",
        f"- Type: {issue.issue_type}",
        f"- Status: {issue.status}",
        f"- Priority: {issue.priority}",
        f"- Assignee: {issue.assignee}",
        f"- Reporter: {issue.reporter}",
    ]
    if issue.labels:
        lines.append(f"- Labels: {', '.join(issue.labels)}")
    if issue.components:
        lines.append(f"- Components: {', '.join(issue.components)}")
    if issue.fix_versions:
        lines.append(f"- Fix versions: {', '.join(issue.fix_versions)}")
    if issue.is_subtask and issue.parent_key:
        lines.append(f"- Parent issue: {issue.parent_key}")

    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(issue.description or "No description")

    lines.append("")
    lines.append(f"## Comments ({len(comments)})")
    if not comments:
        lines.append("")
        lines.append("No comments.")
    else:
        for comment in comments:
            lines.append("")
            lines.append(f"### {comment.author_name} — {comment.formatted_created_at}")
            lines.append(comment.body)

    return "\n".join(lines)


def build_jira_plan_prompt(issue: UIJiraIssue, comments: List[UIJiraComment]) -> str:
    """
    Build the full instructional prompt for an AI CLI to study a JIRA issue and plan the work.

    Args:
        issue: The issue details
        comments: The issue's comments, in display order

    Returns:
        The complete prompt text, ready to hand off to an external AI coding CLI
    """
    issue_context = format_jira_issue_context(issue, comments)
    return JIRA_PLAN_PROMPT_TEMPLATE.format(context=issue_context)


__all__ = ["format_jira_issue_context", "build_jira_plan_prompt"]
