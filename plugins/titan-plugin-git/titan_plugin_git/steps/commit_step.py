# plugins/titan-plugin-git/titan_plugin_git/steps/commit_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.engine.results import Skip
from titan_plugin_git.exceptions import GitClientError, GitCommandError
from titan_plugin_git.messages import msg


def create_git_commit_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Creates a git commit.
    Skips if the working directory is clean.

    Requires:
        ctx.git: An initialized GitClient.

    Inputs (from ctx.data):
        git_status (GitStatus): The git status object, used to check if the working directory is clean.
        commit_message (str): The message for the commit.
        all_files (bool, optional): Whether to commit all modified and new files. Defaults to True.

    Outputs (saved to ctx.data):
        commit_hash (str): The hash of the created commit.

    Returns:
        Success: If the commit was created successfully.
        Error: If the GitClient is not available, or the commit operation fails.
        Skip: If there are no changes to commit.
    """
    # Skip if there's nothing to commit
    git_status = ctx.data.get("git_status")
    if git_status and git_status.is_clean:
        return Skip("Working directory is clean, skipping commit.")

    if not ctx.git:
        return Error(msg.Steps.Commit.GIT_CLIENT_NOT_AVAILABLE)

    commit_message = ctx.get('commit_message')
    if not commit_message:
        return Error(msg.Steps.Commit.COMMIT_MESSAGE_REQUIRED)
        
    all_files = ctx.get('all_files', True)

    try:
        commit_hash = ctx.git.commit(message=commit_message, all=all_files)
            
        return Success(
            message=msg.Steps.Commit.COMMIT_SUCCESS.format(commit_hash=commit_hash),
            metadata={"commit_hash": commit_hash}
        )
    except GitClientError as e:
        return Error(msg.Steps.Commit.CLIENT_ERROR_DURING_COMMIT.format(e=e))
    except GitCommandError as e:
        return Error(msg.Steps.Commit.COMMAND_FAILED_DURING_COMMIT.format(e=e))
    except Exception as e:
        return Error(msg.Steps.Commit.UNEXPECTED_ERROR_DURING_COMMIT.format(e=e))
