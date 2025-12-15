"""
Prompt user to select an issue from search results
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from ..messages import msg


def prompt_select_issue_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Prompt user to select a JIRA issue from search results.

    Inputs (from ctx.data):
        jira_issues (List[JiraTicket]): List of issues from search

    Outputs (saved to ctx.data):
        jira_issue_key (str): Selected issue key
        selected_issue (JiraTicket): Selected issue object
    """
    if ctx.views:
        ctx.views.step_header("prompt_select_issue", ctx.current_step, ctx.total_steps)

    # Get issues from previous search
    issues = ctx.get("jira_issues")
    if not issues:
        return Error(msg.Steps.PromptSelectIssue.NO_ISSUES_AVAILABLE)

    if len(issues) == 0:
        return Error(msg.Steps.PromptSelectIssue.NO_ISSUES_AVAILABLE)

    # Build choices list
    choices = []
    for issue in issues:
        assignee = issue.assignee or "Unassigned"
        # Format: "KEY [STATUS] Summary (Assignee | Type)"
        choice = f"{issue.key} [{issue.status}] {issue.summary[:60]} ({assignee} | {issue.issue_type})"
        choices.append(choice)

    # Prompt user to select issue
    if ctx.views:
        # Ask for selection (issues already displayed in table from previous step)
        if ctx.ui:
            ctx.ui.spacer.small()

        selected_index = ctx.views.prompts.ask_int(
            msg.Steps.PromptSelectIssue.ASK_ISSUE_NUMBER,
            min_value=1,
            max_value=len(choices)
        )

        if selected_index is None:
            return Error(msg.Steps.PromptSelectIssue.NO_ISSUE_SELECTED)

        # Convert to 0-based index
        selected_issue = issues[selected_index - 1]

        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.panel.print(
                msg.Steps.PromptSelectIssue.ISSUE_SELECTION_CONFIRM.format(
                    key=selected_issue.key,
                    summary=selected_issue.summary
                ),
                panel_type="success"
            )
            ctx.ui.spacer.small()

        return Success(
            msg.Steps.PromptSelectIssue.SELECT_SUCCESS.format(key=selected_issue.key),
            metadata={
                "jira_issue_key": selected_issue.key,
                "selected_issue": selected_issue
            }
        )
    else:
        return Error(msg.Steps.PromptSelectIssue.UI_NOT_AVAILABLE)


__all__ = ["prompt_select_issue_step"]
