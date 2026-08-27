"""
Confirm and assign JIRA issue to the current user
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from ..messages import msg


def confirm_and_assign_issue(ctx: WorkflowContext) -> WorkflowResult:
    """
    Ask the user if they want to assign the current JIRA issue to themselves, and do it.

    Meant to run after a plan/coding step, once the user has studied the issue and possibly
    started working on it, so they can claim it in JIRA without leaving the terminal.

    Inputs (from ctx.data):
        jira_issue_key (str): JIRA issue key to assign

    Outputs (saved to ctx.data):
        issue_assigned_to_me (bool): Whether the issue was assigned to the current user

    Returns:
        Success: Issue assigned, or user declined to assign it
        Error: JIRA client not available, issue key missing, or the assignment call failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Assign Issue")

    if not ctx.jira:
        ctx.textual.error_text(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)
        ctx.textual.end_step("error")
        return Error(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)

    issue_key = ctx.get("jira_issue_key")
    if not issue_key:
        error_msg = "JIRA issue key is required"
        ctx.textual.error_text(error_msg)
        ctx.textual.end_step("error")
        return Error(error_msg)

    user_result = ctx.jira.get_current_user()
    match user_result:
        case ClientSuccess(data=user):
            pass
        case ClientError(error_message=err):
            error_msg = f"Failed to get current user: {err}"
            ctx.textual.error_text(error_msg)
            ctx.textual.end_step("error")
            return Error(error_msg)

    want_to_assign = ctx.textual.ask_confirm(
        f"Assign {issue_key} to yourself ({user.display_name})?", default=True
    )

    if not want_to_assign:
        ctx.textual.dim_text("Issue left unassigned")
        ctx.textual.end_step("success")
        return Success("Issue left unassigned", metadata={"issue_assigned_to_me": False})

    with ctx.textual.loading(f"Assigning {issue_key} to {user.display_name}..."):
        assign_result = ctx.jira.assign_issue(issue_key=issue_key, account_id=user.account_id)

    match assign_result:
        case ClientSuccess():
            success_msg = f"Assigned {issue_key} to {user.display_name}"
            ctx.textual.success_text(success_msg)
            ctx.textual.end_step("success")
            return Success(success_msg, metadata={"issue_assigned_to_me": True})
        case ClientError(error_message=err):
            error_msg = f"Failed to assign {issue_key}: {err}"
            ctx.textual.error_text(error_msg)
            ctx.textual.end_step("error")
            return Error(error_msg)


__all__ = ["confirm_and_assign_issue"]
