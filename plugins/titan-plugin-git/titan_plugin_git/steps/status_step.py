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
    A workflow step that retrieves the current git status.
    
    Requires:
        ctx.git: An initialized GitClient.
    
    Sets:
        ctx.data['git_status']: The GitStatus object.
    
    Returns:
        Success: If the status was retrieved successfully.
        Error: If the GitClient is not available.
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
