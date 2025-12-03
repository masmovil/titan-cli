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
        return Error(msg.Steps.Status.git_client_not_available)

    try:
        status = ctx.git.get_status()
        
        message = msg.Steps.Status.status_retrieved_success
        if not status.is_clean:
            message += msg.Steps.Status.working_directory_not_clean
            
        return Success(
            message=message,
            metadata={"git_status": status}
        )
    except Exception as e:
        return Error(msg.Steps.Status.failed_to_get_status.format(e=e))
