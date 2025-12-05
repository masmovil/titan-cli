# plugins/titan-plugin-github/titan_plugin_github/steps/prompt_steps.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from ..messages import msg

def prompt_for_pr_title_step(ctx: WorkflowContext, **kwargs) -> WorkflowResult:
    """Prompts the user for a PR title and saves it to context."""
    try:
        title = ctx.views.prompts.ask_text(msg.Prompts.ENTER_PR_TITLE)
        if not title:
            return Error("PR title cannot be empty.")
        return Success("PR title captured", metadata={"pr_title": title})
    except (KeyboardInterrupt, EOFError):
        return Error("User cancelled.")
    except Exception as e:
        return Error(f"Failed to prompt for PR title: {e}", exception=e)

def prompt_for_pr_body_step(ctx: WorkflowContext, **kwargs) -> WorkflowResult:
    """Prompts the user for a PR body and saves it to context."""
    try:
        body = ctx.views.prompts.ask_multiline(msg.Prompts.ENTER_PR_BODY)
        # Body can be empty
        return Success("PR body captured", metadata={"pr_body": body})
    except (KeyboardInterrupt, EOFError):
        return Error("User cancelled.")
    except Exception as e:
        return Error(f"Failed to prompt for PR body: {e}", exception=e)
