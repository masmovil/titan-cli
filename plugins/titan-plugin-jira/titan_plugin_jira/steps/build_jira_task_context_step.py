"""
Build JIRA task context step
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from ..operations import build_jira_implementation_prompt, build_jira_plan_prompt


def build_jira_task_context_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Build the AI prompts for planning and implementing work on a JIRA issue.

    Combines the issue and its comments into phase-specific prompts ready to be handed to
    external AI CLIs via the `ai_code_assistant` core step.

    Inputs (from ctx.data):
        jira_issue (UIJiraIssue): Issue details, from get_issue
        jira_comments (list[UIJiraComment], optional): Issue comments, from get_comments

    Outputs (saved to ctx.data):
        jira_task_context (str): Full prompt text (instructions + issue + comments)
        jira_implementation_context (str): Implementation and unit-test prompt

    Returns:
        Success: Prompt built
        Error: jira_issue is missing
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Task Context")

    issue = ctx.get("jira_issue")
    if not issue:
        error_msg = "JIRA issue is required to build the task context"
        ctx.textual.error_text(error_msg)
        ctx.textual.end_step("error")
        return Error(error_msg)

    comments = ctx.get("jira_comments") or []

    task_context = build_jira_plan_prompt(issue, comments)
    implementation_context = build_jira_implementation_prompt(issue, comments)

    ctx.textual.success_text(
        f"Task context ready for {issue.key} ({len(task_context)} characters)"
    )
    ctx.textual.end_step("success")
    return Success(
        f"Task context ready for {issue.key}",
        metadata={
            "jira_task_context": task_context,
            "jira_implementation_context": implementation_context,
        },
    )


__all__ = ["build_jira_task_context_step"]
