"""
Select JIRA issue step (by number, full key, or Ready to Dev list)
"""

import re

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ui.tui.widgets import Table
from ..messages import msg
from ..utils import SAVED_QUERIES, IssueSorter
from ..operations import build_issue_table_data

_NUMERIC_RE = re.compile(r"^\d+$")
_FULL_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")


def select_jira_issue_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Resolve a JIRA issue key from user input: a plain number, a full key, or a board search.

    A plain number (e.g. "123") is composed with the default project configured on the
    JIRA client (ctx.jira.project_key) into a full key (e.g. "PROJ-123"). A full key
    (e.g. "OTHERPROJ-45") is used as-is, which also covers issues from other boards.
    Leaving the input empty lists the "Ready to Dev" issues in the default project,
    letting the user pick from that list.

    Requires:
        ctx.jira: An initialized JiraClient.

    Outputs (saved to ctx.data):
        jira_issue_key (str): The resolved JIRA issue key
        selected_issue (UIJiraIssue, optional): Set only when resolved via the Ready to Dev list

    Returns:
        Success: An issue key was resolved
        Error: JIRA client not available, invalid input, search failed, or no selection made
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Select JIRA Issue")

    if not ctx.jira:
        ctx.textual.error_text(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)
        ctx.textual.end_step("error")
        return Error(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)

    ctx.textual.text("")
    raw_input_value = ctx.textual.ask_text(
        "Enter Jira issue number or key (e.g. 123 or PROJ-456), or leave empty to list Ready to Dev issues",
        default=""
    )
    raw_input_value = (raw_input_value or "").strip()

    if raw_input_value:
        if _NUMERIC_RE.match(raw_input_value):
            project_key = getattr(ctx.jira, "project_key", None)
            if not project_key:
                error_msg = (
                    "No default JIRA project configured, so a plain number can't be resolved to an issue key. "
                    "Enter the full issue key instead (e.g. PROJ-123), or configure default_project in .titan/config.toml."
                )
                ctx.textual.error_text(error_msg)
                ctx.textual.end_step("error")
                return Error(error_msg)
            issue_key = f"{project_key}-{raw_input_value}"
        elif _FULL_KEY_RE.match(raw_input_value):
            issue_key = raw_input_value.upper()
        else:
            error_msg = (
                f"Invalid issue key format: '{raw_input_value}'. "
                "Use a number (e.g. 123) or a full key (e.g. PROJ-123)."
            )
            ctx.textual.error_text(error_msg)
            ctx.textual.end_step("error")
            return Error(error_msg)

        ctx.textual.success_text(f"Using issue: {issue_key}")
        ctx.textual.end_step("success")
        return Success(f"Using issue: {issue_key}", metadata={"jira_issue_key": issue_key})

    # Empty input: list the board's "Ready to Dev" issues instead of asking for free text
    project_key = getattr(ctx.jira, "project_key", None)
    if not project_key:
        error_msg = (
            "No default JIRA project configured, so the Ready to Dev issues can't be listed. "
            "Enter the full issue key instead (e.g. PROJ-123), or configure default_project in .titan/config.toml."
        )
        ctx.textual.error_text(error_msg)
        ctx.textual.end_step("error")
        return Error(error_msg)

    jql = SAVED_QUERIES.format("ready_to_dev_issues", project=project_key)

    with ctx.textual.loading("Searching Ready to Dev issues..."):
        result = ctx.jira.search_issues(jql=jql, max_results=25, fields=["*all"])

    match result:
        case ClientSuccess(data=issues):
            if not issues:
                error_msg = f"No Ready to Dev issues found in project {project_key}"
                ctx.textual.dim_text(error_msg)
                ctx.textual.end_step("error")
                return Error(error_msg)

            sorter = IssueSorter()
            sorted_issues = sorter.sort(issues)

            ctx.textual.text("")
            ctx.textual.success_text(f"Found {len(sorted_issues)} issue(s)")
            ctx.textual.text("")

            headers, rows = build_issue_table_data(sorted_issues, summary_max_length=60)
            ctx.textual.mount(
                Table(headers=headers, rows=rows, title="Ready to Dev Issues")
            )

        case ClientError(error_message=err):
            error_msg = f"Failed to search JIRA issues: {err}"
            ctx.textual.error_text(error_msg)
            ctx.textual.end_step("error")
            return Error(error_msg)

    ctx.textual.text("")
    response = ctx.textual.ask_text("Enter issue number to select", default="")
    response = (response or "").strip()
    if not response:
        error_msg = "No issue selected"
        ctx.textual.error_text(error_msg)
        ctx.textual.end_step("error")
        return Error(error_msg)

    try:
        selected_index = int(response)
    except ValueError:
        error_msg = f"Invalid input: '{response}' is not a number"
        ctx.textual.error_text(error_msg)
        ctx.textual.end_step("error")
        return Error(error_msg)

    if selected_index < 1 or selected_index > len(sorted_issues):
        error_msg = f"Invalid selection: must be between 1 and {len(sorted_issues)}"
        ctx.textual.error_text(error_msg)
        ctx.textual.end_step("error")
        return Error(error_msg)

    selected_issue = sorted_issues[selected_index - 1]

    ctx.textual.success_text(f"Selected: {selected_issue.key} - {selected_issue.summary}")
    ctx.textual.end_step("success")
    return Success(
        f"Using issue: {selected_issue.key}",
        metadata={"jira_issue_key": selected_issue.key, "selected_issue": selected_issue}
    )


__all__ = ["select_jira_issue_step"]
