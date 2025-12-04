# plugins/titan-plugin-git/titan_plugin_git/steps/prompt_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_plugin_git.messages import msg # Use absolute import

def prompt_for_commit_message_step(ctx: WorkflowContext, **kwargs) -> WorkflowResult:
    """
    Prompts the user for a commit message and saves it to the context.

    Sets:
        ctx.data['commit_message']: The message entered by the user.
    """
    try:
        # Using a generic prompt message, can be customized if needed
        message = ctx.views.prompts.ask_text(msg.Prompts.ENTER_COMMIT_MESSAGE)
        if not message:
            return Error(msg.Steps.Commit.COMMIT_MESSAGE_REQUIRED)
        return Success(
            message="Commit message captured",
            metadata={"commit_message": message}
        )
    except (KeyboardInterrupt, EOFError):
        return Error("User cancelled.")
    except Exception as e:
        return Error(f"Failed to prompt for commit message: {e}", exception=e)
