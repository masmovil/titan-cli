"""
Select Issue Type Step

Lists available issue types in the project and lets user select one.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ports.protocol import InteractionOption
from titan_plugin_jira.models.enums import JiraIssueType
from titan_plugin_jira.constants import (
    StepTitles,
    ErrorMessages,
    SuccessMessages,
    InfoMessages,
)


def select_issue_type(ctx: WorkflowContext) -> WorkflowResult:
    """
    Select issue type for the new issue.

    Requires:
    - ctx.jira.project_key (from client config)

    Stores in:
    - ctx.data["issue_type"] = str (e.g., "Story", "Bug", "Task")
    - ctx.data["issue_type_id"] = str (e.g., "10001")

    Returns:
        WorkflowResult
    """
    ctx.textual.begin_step(StepTitles.ISSUE_TYPE)

    # Get project key from client
    project_key = ctx.jira.project_key
    if not project_key:
        ctx.interaction.panel(ErrorMessages.NO_PROJECT_CONFIGURED, panel_type="error")
        ctx.textual.end_step("error")
        return Error("no_default_project")

    ctx.textual.dim_text(InfoMessages.GETTING_ISSUE_TYPES.format(project=project_key))
    ctx.textual.text("")

    # Get issue types from Jira
    result = ctx.jira.get_issue_types(project_key)

    match result:
        case ClientSuccess(data=issue_types):
            if not issue_types:
                ctx.interaction.panel(ErrorMessages.NO_ISSUE_TYPES_FOUND, panel_type="error")
                ctx.textual.end_step("error")
                return Error("no_issue_types")

            # Filter out subtasks (we don't want to create subtasks directly)
            issue_types = [it for it in issue_types if not it.subtask]

            if not issue_types:
                ctx.interaction.panel(ErrorMessages.ONLY_SUBTASKS_AVAILABLE, panel_type="error")
                ctx.textual.end_step("error")
                return Error("only_subtasks")

            common_issue_type_order = {
                JiraIssueType.STORY.value: 0,
                JiraIssueType.TASK.value: 1,
                JiraIssueType.BUG.value: 2,
                JiraIssueType.EPIC.value: 3,
            }
            issue_types.sort(
                key=lambda issue_type: (
                    common_issue_type_order.get(issue_type.name, 999),
                    issue_type.name.lower(),
                )
            )

            option_items = []
            for issue_type in issue_types:
                description = issue_type.description or ""
                if len(description) > 80:
                    description = description[:77] + "..."
                option_items.append(
                    InteractionOption(
                        id=issue_type.id,
                        value=issue_type,
                        label=issue_type.label,
                        description=description,
                    )
                )

            selected_type = ctx.textual.ask_option(
                InfoMessages.AVAILABLE_ISSUE_TYPES,
                option_items,
            )

            if not selected_type:
                ctx.interaction.panel(ErrorMessages.SELECTED_TYPE_NOT_FOUND, panel_type="error")
                ctx.textual.end_step("error")
                return Error("no_issue_type_selected")

            # Store in context
            ctx.data["issue_type"] = selected_type.name
            ctx.data["issue_type_id"] = selected_type.id

            ctx.textual.success_text(SuccessMessages.TYPE_SELECTED.format(type=selected_type.name))
            ctx.textual.text("")

            ctx.textual.end_step("success")

            return Success(
                f"Issue type selected: {selected_type.name}",
                metadata={"issue_type": selected_type.name, "issue_type_id": selected_type.id},
            )

        case ClientError(error_message=err):
            ctx.interaction.panel(
                ErrorMessages.FAILED_TO_GET_ISSUE_TYPES.format(error=err), panel_type="error"
            )
            ctx.textual.end_step("error")
            return Error("failed_to_get_issue_types")
