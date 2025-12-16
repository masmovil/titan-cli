"""
Get JIRA issue details step
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from ..exceptions import JiraAPIError
from ..messages import msg


def get_issue_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Get JIRA issue details by key.

    Inputs (from ctx.data):
        jira_issue_key (str): JIRA issue key (e.g., "PROJ-123")
        expand (list[str], optional): Additional fields to expand

    Outputs (saved to ctx.data):
        jira_issue (JiraTicket): Issue details

    Returns:
        Success: Issue retrieved
        Error: Failed to get issue
    """
    # Show step header
    # if ctx.views:
    #     ctx.views.step_header("get_issue", ctx.current_step, ctx.total_steps)

    # Check if JIRA client is available
    if not ctx.jira:
        if ctx.ui:
            ctx.ui.panel.print(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT, panel_type="error")
        return Error(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)

    # Get issue key
    issue_key = ctx.get("jira_issue_key")
    if not issue_key:
        if ctx.ui:
            ctx.ui.panel.print("JIRA issue key is required", panel_type="error")
        return Error("JIRA issue key is required")

    # Get optional expand fields
    expand = ctx.get("expand")

    try:
        # Show progress
        if ctx.ui:
            ctx.ui.text.info(msg.Steps.GetIssue.GETTING_ISSUE.format(issue_key=issue_key))

        # Get issue
        issue = ctx.jira.get_ticket(ticket_key=issue_key, expand=expand)

        # Show success
        if ctx.ui:
            ctx.ui.panel.print(
                msg.Steps.GetIssue.GET_SUCCESS.format(issue_key=issue_key),
                panel_type="success"
            )

            # Show issue details
            ctx.ui.text.body(f"  Title: {issue.summary}", style="cyan")
            ctx.ui.text.body(f"  Status: {issue.status}")
            ctx.ui.text.body(f"  Type: {issue.issue_type}")
            ctx.ui.text.body(f"  Assignee: {issue.assignee or 'Unassigned'}")

            ctx.ui.spacer.small()

        return Success(
            msg.Steps.GetIssue.GET_SUCCESS.format(issue_key=issue_key),
            metadata={"jira_issue": issue}
        )

    except JiraAPIError as e:
        if e.status_code == 404:
            error_msg = msg.Steps.GetIssue.ISSUE_NOT_FOUND.format(issue_key=issue_key)
            if ctx.ui:
                ctx.ui.panel.print(error_msg, panel_type="error")
            return Error(error_msg)
        error_msg = msg.Steps.GetIssue.GET_FAILED.format(e=e)
        if ctx.ui:
            ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error getting issue: {e}"
        if ctx.ui:
            ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg)


__all__ = ["get_issue_step"]
