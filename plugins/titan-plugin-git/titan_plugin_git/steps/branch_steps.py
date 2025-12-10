# plugins/titan-plugin-git/titan_plugin_git/steps/branch_steps.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_plugin_git.messages import msg

def get_current_branch_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Retrieves the current git branch name and saves it to the context.

    Requires:
        ctx.git: An initialized GitClient.

    Outputs (saved to ctx.data):
        pr_head_branch (str): The name of the current branch, to be used as the head branch for a PR.

    Returns:
        Success: If the current branch was retrieved successfully.
        Error: If the GitClient is not available or the git command fails.
    """
    if not ctx.git:
        return Error(msg.Steps.Status.GIT_CLIENT_NOT_AVAILABLE)
    
    try:
        current_branch = ctx.git.get_current_branch()
        return Success(
            msg.Steps.Branch.GET_CURRENT_BRANCH_SUCCESS.format(branch=current_branch),
            metadata={"pr_head_branch": current_branch}
        )
    except Exception as e:
        return Error(msg.Steps.Branch.GET_CURRENT_BRANCH_FAILED.format(e=e), exception=e)

def get_base_branch_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Retrieves the configured main/base branch name and saves it to the context.

    Requires:
        ctx.git: An initialized GitClient.

    Outputs (saved to ctx.data):
        pr_base_branch (str): The name of the base branch, to be used as the base branch for a PR.

    Returns:
        Success: If the base branch was retrieved successfully.
        Error: If the GitClient is not available or the git command fails.
    """
    if not ctx.git:
        return Error(msg.Steps.Status.GIT_CLIENT_NOT_AVAILABLE)

    try:
        base_branch = ctx.git.main_branch
        return Success(
            msg.Steps.Branch.GET_BASE_BRANCH_SUCCESS.format(branch=base_branch),
            metadata={"pr_base_branch": base_branch}
        )
    except Exception as e:
        return Error(msg.Steps.Branch.GET_BASE_BRANCH_FAILED.format(e=e), exception=e)
