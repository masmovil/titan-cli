# plugins/titan-plugin-git/titan_plugin_git/steps/status_step.py
from titan_cli.engine import (
    WorkflowContext, 
    WorkflowResult, 
    Success, 
    Error
    )
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
    """
    if not ctx.git:
        return Error(msg.Steps.Status.GIT_CLIENT_NOT_AVAILABLE)

    try:
        status = ctx.git.get_status()
        
        message = msg.Steps.Status.STATUS_RETRIEVED_SUCCESS
        if not status.is_clean:
            message += msg.Steps.Status.WORKING_DIRECTORY_NOT_CLEAN
            
        return Success(
            message=message,
            metadata={"git_status": status}
        )
    except Exception as e:
        return Error(msg.Steps.Status.FAILED_TO_GET_STATUS.format(e=e))
