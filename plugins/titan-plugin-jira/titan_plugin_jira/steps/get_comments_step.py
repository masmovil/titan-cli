"""
Get JIRA issue comments step
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from ..messages import msg


def get_comments_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Get all comments for a JIRA issue.

    Requires:
        ctx.jira: An initialized JiraClient.

    Inputs (from ctx.data):
        jira_issue_key (str): JIRA issue key (e.g., "PROJ-123")

    Outputs (saved to ctx.data):
        jira_comments (list[UIJiraComment]): Comments for the issue, oldest first

    Returns:
        Success: Comments retrieved (empty list if the issue has none)
        Error: JIRA client not available, issue key missing, or the request failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Get Issue Comments")

    # Check if JIRA client is available
    if not ctx.jira:
        ctx.textual.error_text(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)
        ctx.textual.end_step("error")
        return Error(msg.Plugin.CLIENT_NOT_AVAILABLE_IN_CONTEXT)

    # Get issue key
    issue_key = ctx.get("jira_issue_key")
    if not issue_key:
        ctx.textual.error_text("JIRA issue key is required")
        ctx.textual.end_step("error")
        return Error("JIRA issue key is required")

    # Get comments with loading indicator
    with ctx.textual.loading(f"Fetching comments for JIRA issue: {issue_key}"):
        result = ctx.jira.get_comments(issue_key)

    # Pattern match on Result
    match result:
        case ClientSuccess(data=comments):
            ctx.textual.text("")  # spacing

            if not comments:
                ctx.textual.dim_text(f"No comments found for {issue_key}")
                ctx.textual.end_step("success")
                return Success(
                    f"No comments found for {issue_key}",
                    metadata={"jira_comments": []}
                )

            ctx.textual.success_text(f"Retrieved {len(comments)} comment(s) for {issue_key}")
            for comment in comments:
                ctx.textual.text(f"  {comment.author_name} ({comment.formatted_created_at}):")
                ctx.textual.dim_text(f"    {comment.body}")
            ctx.textual.text("")

            ctx.textual.end_step("success")
            return Success(
                f"Retrieved {len(comments)} comment(s) for {issue_key}",
                metadata={"jira_comments": comments}
            )

        case ClientError(error_message=err):
            error_msg = f"Failed to get comments for {issue_key}: {err}"
            ctx.textual.error_text(error_msg)
            ctx.textual.end_step("error")
            return Error(error_msg)


__all__ = ["get_comments_step"]
