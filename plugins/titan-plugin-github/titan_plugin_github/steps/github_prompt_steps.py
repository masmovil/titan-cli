# plugins/titan-plugin-github/titan_plugin_github/steps/prompt_steps.py
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import WorkflowResult, Success, Error, Skip
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ui.tui.widgets import SelectionOption
from ..messages import msg
from ..operations import add_assignee_if_missing, parse_comma_separated_list


def prompt_for_pr_title_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Interactively prompts the user for a Pull Request title.
    Skips if pr_title already exists.

    Requires:
        ctx.textual: Textual UI components.

    Outputs (saved to ctx.data):
        pr_title (str): The title entered by the user.

    Returns:
        Success: If the title was captured successfully.
        Error: If the user cancels or the title is empty.
        Skip: If pr_title already exists.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Prompt for PR Title")

    # Skip if title already exists (e.g., from AI generation)
    if ctx.get("pr_title"):
        ctx.textual.dim_text("PR title already provided, skipping manual prompt.")
        ctx.textual.end_step("skip")
        return Skip("PR title already provided, skipping manual prompt.")

    try:
        title = ctx.textual.ask_text(msg.Prompts.ENTER_PR_TITLE)
        if not title:
            ctx.textual.end_step("error")
            return Error("PR title cannot be empty.")
        ctx.textual.end_step("success")
        return Success("PR title captured", metadata={"pr_title": title})
    except (KeyboardInterrupt, EOFError):
        ctx.textual.end_step("error")
        return Error("User cancelled.")
    except Exception as e:
        ctx.textual.end_step("error")
        return Error(f"Failed to prompt for PR title: {e}", exception=e)


def prompt_for_pr_body_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Interactively prompts the user for a Pull Request body.
    Skips if pr_body already exists.

    Requires:
        ctx.textual: Textual UI components.

    Outputs (saved to ctx.data):
        pr_body (str): The body/description entered by the user.

    Returns:
        Success: If the body was captured successfully.
        Error: If the user cancels.
        Skip: If pr_body already exists.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Prompt for PR Body")

    # Skip if body already exists (e.g., from AI generation)
    if ctx.get("pr_body"):
        ctx.textual.dim_text("PR body already provided, skipping manual prompt.")
        ctx.textual.end_step("skip")
        return Skip("PR body already provided, skipping manual prompt.")

    try:
        body = ctx.textual.ask_multiline(msg.Prompts.ENTER_PR_BODY, default="")
        # Body can be empty
        ctx.textual.end_step("success")
        return Success("PR body captured", metadata={"pr_body": body})
    except (KeyboardInterrupt, EOFError):
        ctx.textual.end_step("error")
        return Error("User cancelled.")
    except Exception as e:
        ctx.textual.end_step("error")
        return Error(f"Failed to prompt for PR body: {e}", exception=e)


def prompt_for_pr_draft_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Ask whether the pull request should be created as a draft.

    Requires:
        ctx.textual: Textual UI components.

    Inputs (from ctx.data):
        draft (bool | None, optional): Draft mode from workflow params. Use True/False to skip the prompt, or None to ask interactively.

    Outputs (saved to ctx.data):
        pr_is_draft (bool): Whether the PR should be created as a draft.

    Returns:
        Success: If the draft preference was resolved successfully.
        Error: If the user cancels or the prompt fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Choose PR Draft Mode")

    draft_mode = ctx.get("draft")

    if draft_mode is True:
        ctx.textual.dim_text("PR draft mode preset to draft, skipping prompt.")
        ctx.textual.end_step("success")
        return Success("PR draft preference preset", metadata={"pr_is_draft": True})

    if draft_mode is False:
        ctx.textual.dim_text("PR draft mode preset to ready for review, skipping prompt.")
        ctx.textual.end_step("success")
        return Success("PR draft preference preset", metadata={"pr_is_draft": False})

    try:
        is_draft = ctx.textual.ask_confirm(
            msg.Prompts.CREATE_PR_AS_DRAFT,
            default=False,
        )
        mode = "draft" if is_draft else "ready for review"
        ctx.textual.success_text(f"PR will be created as {mode}.")
        ctx.textual.end_step("success")
        return Success("PR draft preference captured", metadata={"pr_is_draft": is_draft})
    except (KeyboardInterrupt, EOFError):
        ctx.textual.end_step("error")
        return Error("User cancelled.")
    except Exception as e:
        ctx.textual.end_step("error")
        return Error(f"Failed to prompt for PR draft mode: {e}", exception=e)


def prompt_for_issue_body_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Interactively prompts the user for a GitHub issue body.
    Skips if issue_body already exists.

    Requires:
        ctx.textual: Textual UI components.

    Outputs (saved to ctx.data):
        issue_body (str): The body/description entered by the user.

    Returns:
        Success: If the body was captured successfully.
        Error: If the user cancels.
        Skip: If issue_body already exists.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Prompt for Issue Body")

    # Skip if body already exists (e.g., from AI generation)
    if ctx.get("issue_body"):
        ctx.textual.dim_text("Issue body already provided, skipping manual prompt.")
        ctx.textual.end_step("skip")
        return Skip("Issue body already provided, skipping manual prompt.")

    try:
        body = ctx.textual.ask_multiline(msg.Prompts.ENTER_ISSUE_BODY, default="")
        # Body can be empty
        ctx.textual.end_step("success")
        return Success("Issue body captured", metadata={"issue_body": body})
    except (KeyboardInterrupt, EOFError):
        ctx.textual.end_step("error")
        return Error("User cancelled.")
    except Exception as e:
        ctx.textual.end_step("error")
        return Error(f"Failed to prompt for issue body: {e}", exception=e)


def prompt_for_self_assign_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Asks the user if they want to assign the issue to themselves.

    Requires:
        ctx.github: An initialized GitHubClient.

    Outputs (saved to ctx.data):
        assignees (list[str]): Updated assignees list when the user chooses self-assignment.

    Returns:
        Success: If the assignment preference is captured successfully.
        Error: If the GitHub client is unavailable or the prompt fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Assign Issue")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    try:
        if ctx.textual.ask_confirm(msg.Prompts.ASSIGN_TO_SELF, default=True):
            result = ctx.github.get_current_user()
            match result:
                case ClientSuccess(data=current_user):
                    existing_assignees = ctx.get("assignees", [])
                    assignees = add_assignee_if_missing(current_user, existing_assignees)
                    ctx.set("assignees", assignees)
                    ctx.textual.success_text(f"Issue will be assigned to {current_user}")
                    ctx.textual.end_step("success")
                    return Success(f"Issue will be assigned to {current_user}")
                case ClientError(error_message=err):
                    ctx.textual.error_text(f"Failed to get current user: {err}")
                    ctx.textual.end_step("error")
                    return Error(f"Failed to get current user: {err}")
        ctx.textual.dim_text("Issue will not be assigned to current user")
        ctx.textual.end_step("success")
        return Success("Issue will not be assigned to current user")
    except (KeyboardInterrupt, EOFError):
        ctx.textual.end_step("error")
        return Error("User cancelled.")
    except Exception as e:
        ctx.textual.error_text(f"Failed to prompt for self-assign: {e}")
        ctx.textual.end_step("error")
        return Error(f"Failed to prompt for self-assign: {e}", exception=e)


def prompt_for_labels_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Prompt the user to select repository labels and save them to context.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        output_key (str, optional): Context key where selected labels should be stored. Defaults to "labels".
        prompt (str, optional): Prompt text shown to the user. Defaults to "Select labels:".
        default_selected_key (str, optional): Context key used to preselect labels. Defaults to output_key.

    Outputs (saved to ctx.data):
        <output_key> (list[str]): Labels selected by the user.

    Returns:
        Success: If label selection completes successfully.
        Skip: If the repository has no labels.
        Error: If the GitHub client is unavailable or the prompt fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Select Labels")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    output_key = ctx.get("output_key", "labels")
    prompt = ctx.get("prompt", msg.Prompts.SELECT_LABELS)
    default_selected_key = ctx.get("default_selected_key", output_key)

    try:
        result = ctx.github.list_labels()
        match result:
            case ClientSuccess(data=available_labels):
                if not available_labels:
                    ctx.textual.dim_text("No labels found in the repository.")
                    ctx.textual.end_step("skip")
                    return Skip("No labels found in the repository.")

                existing_labels = ctx.get(default_selected_key, [])
                if isinstance(existing_labels, str):
                    existing_labels = parse_comma_separated_list(existing_labels)
                if not isinstance(existing_labels, list):
                    existing_labels = []

                selected_set = set(existing_labels)
                options = [
                    SelectionOption(
                        value=label,
                        label=label,
                        selected=label in selected_set,
                    )
                    for label in available_labels
                ]

                selected_labels = ctx.textual.ask_multiselect(prompt, options)

                ctx.set(output_key, selected_labels)
                if selected_labels:
                    ctx.textual.success_text(f"Selected labels: {', '.join(selected_labels)}")
                else:
                    ctx.textual.dim_text("No labels selected")
                ctx.textual.end_step("success")
                return Success("Labels selected", metadata={output_key: selected_labels})
            case ClientError(error_message=err):
                ctx.textual.error_text(f"Failed to get labels: {err}")
                ctx.textual.end_step("error")
                return Error(f"Failed to get labels: {err}")
    except (KeyboardInterrupt, EOFError):
        ctx.textual.end_step("error")
        return Error("User cancelled.")
    except Exception as e:
        ctx.textual.error_text(f"Failed to prompt for labels: {e}")
        ctx.textual.end_step("error")
        return Error(f"Failed to prompt for labels: {e}", exception=e)
