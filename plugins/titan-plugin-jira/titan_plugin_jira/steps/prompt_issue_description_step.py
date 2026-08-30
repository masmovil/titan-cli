"""
Prompt Issue Description Step

Asks user for a brief description of the task/issue to create.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_plugin_jira.constants import StepTitles, UserPrompts, ErrorMessages, SuccessMessages
from titan_plugin_jira.utils import validate_non_empty_text


def prompt_issue_description(ctx: WorkflowContext) -> WorkflowResult:
    """
    Prompt user for brief description of the issue.

    Stores in:
    - ctx.data["brief_description"] = str

    Returns:
        WorkflowResult
    """
    ctx.textual.begin_step(StepTitles.DESCRIPTION)

    ctx.textual.dim_text(UserPrompts.DESCRIBE_TASK)
    ctx.textual.text("")

    # Ask for description
    description = ctx.textual.ask_multiline(UserPrompts.WHAT_TO_DO, default="")

    # Validate input
    is_valid, cleaned_text, _ = validate_non_empty_text(description)

    if not is_valid:
        ctx.interaction.panel(ErrorMessages.DESCRIPTION_EMPTY, panel_type="error")
        ctx.textual.end_step("error")
        return Error("description_required")

    # Store in context
    ctx.data["brief_description"] = cleaned_text

    ctx.textual.success_text(
        SuccessMessages.DESCRIPTION_CAPTURED.format(length=len(cleaned_text))
    )
    ctx.textual.text("")

    ctx.textual.end_step("success")

    return Success(
        f"Brief description captured: {len(cleaned_text)} characters",
        metadata={"description": cleaned_text},
    )
