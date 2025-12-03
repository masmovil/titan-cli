# plugins/titan-plugin-git/titan_plugin_git/steps/commit_step.py
from titan_cli.engine import (
    WorkflowContext, 
    WorkflowResult, 
    Success, 
    Error
)
from titan_plugin_git.exceptions import GitClientError, GitCommandError
from ..messages import msg

def create_git_commit_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    A workflow step that creates a git commit.
    
    Requires:
        ctx.git: An initialized GitClient.
        ctx.data['commit_message']: The message for the commit (str).
        ctx.data['all_files']: Whether to commit all modified files (bool, default: False).
    
    Sets:
        ctx.data['commit_hash']: The hash of the created commit.
    
    Returns:
        Success: If the commit was created successfully.
        Error: If the GitClient is not available, or the commit operation fails.
    """
    if not ctx.git:
        return Error(msg.Steps.Commit.git_client_not_available)

    commit_message = ctx.get('commit_message')
    if not commit_message:
        return Error(msg.Steps.Commit.commit_message_required)
        
    all_files = ctx.get('all_files', False)

    try:
        commit_hash = ctx.git.commit(message=commit_message, all=all_files)
            
        return Success(
            message=msg.Steps.Commit.commit_success.format(commit_hash=commit_hash),
            metadata={"commit_hash": commit_hash}
        )
    except GitClientError as e:
        return Error(msg.Steps.Commit.client_error_during_commit.format(e=e))
    except GitCommandError as e:
        return Error(msg.Steps.Commit.command_failed_during_commit.format(e=e))
    except Exception as e:
        return Error(msg.Steps.Commit.unexpected_error_during_commit.format(e=e))
