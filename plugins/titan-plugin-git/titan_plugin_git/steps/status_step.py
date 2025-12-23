# plugins/titan-plugin-git/titan_plugin_git/steps/status_step.py
from titan_cli.engine import (
    WorkflowContext,
    WorkflowResult,
    Success,
    Error
)
from titan_cli.messages import msg as global_msg
from ..messages import msg

def get_git_status_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Retrieves the current git status and saves it to the context.

    Requires:
        ctx.git: An initialized GitClient.

    Outputs (saved to ctx.data):
        git_status (GitStatus): The full git status object, which includes the `is_clean` flag.

    Returns:
        Success: If the status was retrieved successfully.
        Error: If the GitClient is not available or the git command fails.
        Skip: If user cancels when uncommitted changes are detected.
    """
    # Show step header
    if ctx.views:
        ctx.views.step_header(
            name="Check Git Status",
            step_type="plugin",
            step_detail="git.get_status"
        )

    if not ctx.git:
        return Error(msg.Steps.Status.GIT_CLIENT_NOT_AVAILABLE)

    try:
        status = ctx.git.get_status()

        # If there are uncommitted changes, show warning panel
        if not status.is_clean:
            # Show warning panel if UI is available
            if ctx.ui:
                # Warning panel for uncommitted changes (don't pass title to use default with emoji)
                ctx.ui.panel.print(
                    global_msg.Workflow.UNCOMMITTED_CHANGES_WARNING,
                    panel_type="warning"
                )
                ctx.ui.spacer.small()
            message = msg.Steps.Status.STATUS_RETRIEVED_WITH_UNCOMMITTED
        else:
            # Show success panel for clean working directory
            if ctx.ui:
                ctx.ui.panel.print(
                    msg.Steps.Status.WORKING_DIRECTORY_IS_CLEAN,
                    panel_type="success"
                )
                ctx.ui.spacer.small()
            message = msg.Steps.Status.WORKING_DIRECTORY_IS_CLEAN

        return Success(
            message=message,
            metadata={"git_status": status}
        )
    except Exception as e:
        return Error(msg.Steps.Status.FAILED_TO_GET_STATUS.format(e=e))
