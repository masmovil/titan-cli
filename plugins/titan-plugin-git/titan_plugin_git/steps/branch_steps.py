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
    # Show step header
    if ctx.views:
        ctx.views.step_header(
            name="Get Current Branch",
            step_type="plugin",
            step_detail="git.get_current_branch"
        )

    if not ctx.git:
        error_msg = msg.Steps.Status.GIT_CLIENT_NOT_AVAILABLE
        ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg)

    try:
        current_branch = ctx.git.get_current_branch()
        success_msg = msg.Steps.Branch.GET_CURRENT_BRANCH_SUCCESS.format(branch=current_branch)
        ctx.ui.panel.print(success_msg, panel_type="success")
        return Success(
            success_msg,
            metadata={"pr_head_branch": current_branch}
        )
    except Exception as e:
        error_msg = msg.Steps.Branch.GET_CURRENT_BRANCH_FAILED.format(e=e)
        ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg, exception=e)

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
        error_msg = msg.Steps.Status.GIT_CLIENT_NOT_AVAILABLE
        ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg)

    try:
        base_branch = ctx.git.main_branch
        success_msg = msg.Steps.Branch.GET_BASE_BRANCH_SUCCESS.format(branch=base_branch)
        ctx.ui.panel.print(success_msg, panel_type="success")
        return Success(
            success_msg,
            metadata={"pr_base_branch": base_branch}
        )
    except Exception as e:
        error_msg = msg.Steps.Branch.GET_BASE_BRANCH_FAILED.format(e=e)
        ctx.ui.panel.print(error_msg, panel_type="error")
        return Error(error_msg, exception=e)
