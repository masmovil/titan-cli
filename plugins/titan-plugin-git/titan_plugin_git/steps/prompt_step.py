# plugins/titan-plugin-git/titan_plugin_git/steps/prompt_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_plugin_git.messages import msg

def prompt_for_commit_message_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Prompts the user for a commit message and saves it to the context.
    Skips if the working directory is clean.

    Requires:
        ctx.views.prompts: A PromptsRenderer instance.

    Requires (from ctx.data):
        git_status (GitStatus): The git status object, used to check if the working directory is clean.

    Outputs (saved to ctx.data):
        commit_message (str): The message entered by the user.
    
    Returns:
        Success: If the commit message was captured.
        Error: If the user cancels or the message is empty.
        Skip: If the working directory is clean.
    """
    # Skip if there's nothing to commit
    git_status = ctx.data.get("git_status")
    if git_status and git_status.is_clean:
        return Skip(msg.Steps.Prompt.WORKING_DIRECTORY_CLEAN)

    try:
        # Using a generic prompt message, can be customized if needed
        message = ctx.views.prompts.ask_text(msg.Prompts.ENTER_COMMIT_MESSAGE)
        if not message:
            return Error(msg.Steps.Commit.COMMIT_MESSAGE_REQUIRED)
        return Success(
            message=msg.Steps.Prompt.COMMIT_MESSAGE_CAPTURED,
            metadata={"commit_message": message}
        )
    except (KeyboardInterrupt, EOFError):
        return Error(msg.Steps.Prompt.USER_CANCELLED)
    except Exception as e:
        return Error(msg.Steps.Prompt.PROMPT_FAILED.format(e=e), exception=e)
