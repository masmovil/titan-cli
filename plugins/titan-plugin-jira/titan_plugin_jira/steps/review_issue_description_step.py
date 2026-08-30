"""
Review Issue Description Step

Lets user review and optionally edit the AI-generated description.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_plugin_jira.constants import (
    StepTitles,
    UserPrompts,
    ErrorMessages,
    SuccessMessages,
    InfoMessages,
)


def review_issue_description(ctx: WorkflowContext) -> WorkflowResult:
    """
    Review and optionally edit the enhanced description.

    Requires:
    - ctx.data["enhanced_description"]

    Stores in:
    - ctx.data["final_description"] = str

    Returns:
        WorkflowResult
    """
    ctx.textual.begin_step(StepTitles.REVIEW)

    enhanced_description = ctx.data.get("enhanced_description")

    if not enhanced_description:
        ctx.interaction.panel(ErrorMessages.MISSING_ENHANCED_DESC, panel_type="error")
        ctx.textual.end_step("error")
        return Error("no_enhanced_description")

    # Show full description
    ctx.textual.bold_text(InfoMessages.GENERATED_DESC_LABEL)
    ctx.textual.text("")
    ctx.textual.markdown(enhanced_description)
    ctx.textual.text("")

    # Ask if user wants to edit
    should_edit = ctx.textual.ask_confirm(UserPrompts.WANT_TO_EDIT, default=False)

    final_description = enhanced_description

    if should_edit:
        ctx.textual.text("")
        ctx.textual.dim_text(UserPrompts.EDIT_DESCRIPTION_PROMPT)
        ctx.textual.text("")

        final_description = ctx.textual.ask_multiline(
            UserPrompts.FINAL_DESCRIPTION_LABEL, default=enhanced_description
        )

        if not final_description or not final_description.strip():
            ctx.interaction.panel(InfoMessages.EMPTY_DESC_USING_AI, panel_type="warning")
            final_description = enhanced_description
        else:
            final_description = final_description.strip()
            ctx.textual.success_text(SuccessMessages.DESCRIPTION_EDITED)

    # Store final description
    ctx.data["final_description"] = final_description

    ctx.textual.text("")
    ctx.textual.success_text(
        SuccessMessages.DESCRIPTION_READY.format(length=len(final_description))
    )
    ctx.textual.text("")

    ctx.textual.end_step("success")

    return Success(
        f"Final description ready ({len(final_description)} chars)",
        metadata={"length": len(final_description)},
    )
