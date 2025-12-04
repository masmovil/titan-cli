# plugins/titan-plugin-git/titan_plugin_git/steps/push_step.py
from typing import Optional
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_plugin_git.exceptions import GitCommandError
from titan_plugin_git.messages import msg

def create_git_push_step(
    ctx: WorkflowContext, 
    remote: Optional[str] = None, 
    branch: Optional[str] = None, 
    set_upstream: bool = False, 
    **kwargs
) -> WorkflowResult:
    """
    A workflow step that pushes changes to a remote repository.
    
    Context Args:
        remote (str, optional): The name of the remote to push to. Defaults to the client's default.
        branch (str, optional): The name of the branch to push. Defaults to the current branch.
        set_upstream (bool, optional): Whether to set the upstream tracking branch. Defaults to False.

    Requires:
        ctx.git: An initialized GitClient.
    
    Returns:
        Success: If the push was successful.
        Error: If the push operation fails.
    """
    if not ctx.git:
        return Error(msg.Steps.Push.GIT_CLIENT_NOT_AVAILABLE)

    # Use defaults from the GitClient if not provided in the step
    remote_to_use = remote or ctx.git.default_remote
    branch_to_use = branch or ctx.git.get_current_branch()

    try:
        ctx.git.push(remote=remote_to_use, branch=branch_to_use, set_upstream=set_upstream)
        
        return Success(
            message=msg.Git.PUSH_SUCCESS.format(remote=remote_to_use, branch=branch_to_use)
        )
    except GitCommandError as e:
        return Error(msg.Steps.Push.PUSH_FAILED.format(e=e))
    except Exception as e:
        return Error(msg.Git.UNEXPECTED_ERROR.format(e=e))
