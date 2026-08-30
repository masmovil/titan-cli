"""
Select Issue Priority Step

Lists available priorities from Jira and lets user select one.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ports.protocol import InteractionOption
from titan_plugin_jira.constants import (
    StepTitles,
    ErrorMessages,
    SuccessMessages,
    InfoMessages,
    DEFAULT_PRIORITIES,
)


def select_issue_priority(ctx: WorkflowContext) -> WorkflowResult:
    """
    Select priority for the new issue from available priorities in Jira.

    Stores in:
    - ctx.data["priority"] = str (e.g., "Medium", "High", "Low")

    Returns:
        WorkflowResult
    """
    ctx.textual.begin_step(StepTitles.PRIORITY)

    # Verify Jira client is available
    if not ctx.jira:
        ctx.interaction.panel(ErrorMessages.JIRA_CLIENT_UNAVAILABLE, panel_type="error")
        ctx.textual.end_step("error")
        return Error("jira_client_unavailable")

    ctx.textual.dim_text(InfoMessages.GETTING_PRIORITIES)
    ctx.textual.text("")

    # Get priorities from Jira
    priorities = None
    result = ctx.jira.get_priorities()

    match result:
        case ClientSuccess(data=fetched_priorities):
            if not fetched_priorities:
                # Fallback to standard priorities if none found
                ctx.interaction.panel(
                    f"{ErrorMessages.NO_PRIORITIES_FOUND}\n\n{InfoMessages.USING_STANDARD_PRIORITIES}",
                    panel_type="warning",
                )
                priorities = DEFAULT_PRIORITIES
            else:
                priorities = fetched_priorities

        case ClientError(error_message=err):
            ctx.interaction.panel(
                f"{ErrorMessages.FAILED_TO_GET_PRIORITIES.format(error=err)}\n\n{InfoMessages.USING_STANDARD_PRIORITIES}",
                panel_type="warning",
            )
            priorities = DEFAULT_PRIORITIES

    priorities.sort(key=lambda priority: priority.name == "-")

    option_items = [
        InteractionOption(
            id=priority.name,
            value=priority,
            label=priority.label,
        )
        for priority in priorities
    ]

    selected_priority = ctx.textual.ask_option(
        InfoMessages.AVAILABLE_PRIORITIES,
        option_items,
    )

    if not selected_priority:
        ctx.textual.end_step("error")
        return Error("no_priority_selected")

    # Store in context
    ctx.data["priority"] = selected_priority.name

    ctx.textual.success_text(
        SuccessMessages.PRIORITY_SELECTED.format(priority=selected_priority.name)
    )
    ctx.textual.text("")

    ctx.textual.end_step("success")

    return Success(
        f"Priority selected: {selected_priority.name}",
        metadata={"priority": selected_priority.name},
    )
