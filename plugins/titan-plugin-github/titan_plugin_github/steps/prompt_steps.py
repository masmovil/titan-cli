# plugins/titan-plugin-github/titan_plugin_github/steps/prompt_steps.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from ..messages import msg


def prompt_for_pr_title_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Interactively prompts the user for a Pull Request title.
    Skips if pr_title already exists.

    Requires:
        ctx.views.prompts: A PromptsRenderer instance.

    Outputs (saved to ctx.data):
        pr_title (str): The title entered by the user.

    Returns:
        Success: If the title was captured successfully.
        Error: If the user cancels or the title is empty.
        Skip: If pr_title already exists.
    """

    # Skip if title already exists (e.g., from AI generation)
    if ctx.get("pr_title"):
        return Skip("PR title already provided, skipping manual prompt.")

    try:
        # Show step header
        if ctx.views:
            ctx.views.step_header("prompt_pr_title", ctx.current_step, ctx.total_steps)
        title = ctx.views.prompts.ask_text(msg.Prompts.ENTER_PR_TITLE)
        if not title:
            return Error("PR title cannot be empty.")
        return Success("PR title captured", metadata={"pr_title": title})
    except (KeyboardInterrupt, EOFError):
        return Error("User cancelled.")
    except Exception as e:
        return Error(f"Failed to prompt for PR title: {e}", exception=e)


def prompt_for_pr_body_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Interactively prompts the user for a Pull Request body using an external editor.
    Skips if pr_body already exists.

    Requires:
        ctx.views.prompts: A PromptsRenderer instance.

    Outputs (saved to ctx.data):
        pr_body (str): The body/description entered by the user.

    Returns:
        Success: If the body was captured successfully.
        Error: If the user cancels.
        Skip: If pr_body already exists.
    """

    # Skip if body already exists (e.g., from AI generation)
    if ctx.get("pr_body"):
        return Skip("PR body already provided, skipping manual prompt.")

    try:
        # Show step header
        # if ctx.views:
        #     ctx.views.step_header("prompt_pr_body", ctx.current_step, ctx.total_steps)
        body = ctx.views.prompts.ask_multiline(msg.Prompts.ENTER_PR_BODY)
        # Body can be empty
        return Success("PR body captured", metadata={"pr_body": body})
    except (KeyboardInterrupt, EOFError):
        return Error("User cancelled.")
    except Exception as e:
        return Error(f"Failed to prompt for PR body: {e}", exception=e)
