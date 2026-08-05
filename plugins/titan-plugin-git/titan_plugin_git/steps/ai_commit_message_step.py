# plugins/titan-plugin-git/titan_plugin_git/steps/ai_commit_message_step.py
from titan_cli.ai.router.declaration import declare_ai_usage
from titan_cli.ai.router.enums import AIProviderType, AITask
from titan_cli.ai.router.models import AIExecutionError, AIExecutionSuccess
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_git.messages import msg
from ..operations import (
    build_ai_commit_prompt,
    process_ai_commit_message,
    validate_message_length,
)


@declare_ai_usage(
    task=AITask.COMMIT_MESSAGE,
    # A commit message is one prompt in, one text out: a remote connection or a
    # headless CLI can do it, an interactive session cannot.
    executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
    enforces=True,
)
def ai_generate_commit_message(ctx: WorkflowContext) -> WorkflowResult:
    """
    Generate a commit message using AI based on the current changes.

    Uses AI to analyze the diff of uncommitted changes and generate a
    conventional commit message (type: description).

    Requires:
        ctx.git: An initialized GitClient.
        ctx.ai_router: The AI execution façade.

    Inputs (from ctx.data):
        git_status: Current git status with changes.

    Outputs (saved to ctx.data):
        commit_message (str): AI-generated commit message.

    Returns:
        Success: If the commit message was generated successfully.
        Error: If the operation fails.
        Skip: If there are no changes, AI is turned off for this task, or the
            user declined the suggestion.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("AI Commit Message")

    if not ctx.ai_router:
        ctx.textual.error_text(msg.Steps.AICommitMessage.AI_NOT_CONFIGURED)
        ctx.textual.end_step("error")
        return Error(msg.Steps.AICommitMessage.AI_NOT_CONFIGURED)

    # Get git client
    if not ctx.git:
        ctx.textual.end_step("error")
        return Error(msg.Steps.AICommitMessage.GIT_CLIENT_NOT_AVAILABLE)

    # Get git status
    git_status = ctx.get('git_status')
    if not git_status or git_status.is_clean:
        ctx.textual.dim_text(msg.Steps.AICommitMessage.NO_CHANGES_TO_COMMIT)
        ctx.textual.end_step("skip")
        return Skip(msg.Steps.AICommitMessage.NO_CHANGES_TO_COMMIT)

    try:
        # Get diff of uncommitted changes
        ctx.textual.dim_text(msg.Steps.AICommitMessage.ANALYZING_CHANGES)

        files_for_commit = ctx.get("selected_files") or (
            git_status.modified_files + git_status.untracked_files + git_status.staged_files
        )

        # Keep AI context aligned with the exact files that will be committed.
        diff_result = ctx.git.get_uncommitted_diff_for_files(files_for_commit)

        match diff_result:
            case ClientSuccess(data=diff_text):
                if not diff_text or diff_text.strip() == "":
                    ctx.textual.end_step("skip")
                    return Skip(msg.Steps.AICommitMessage.NO_UNCOMMITTED_CHANGES)
            case ClientError(error_message=err):
                ctx.textual.end_step("error")
                return Error(f"Failed to get diff: {err}")

        # Build AI prompt using operations
        prompt = build_ai_commit_prompt(diff_text, files_for_commit, max_diff_chars=8000)

        project_root = ctx.get("project_root", ".")

        with ctx.textual.loading(msg.Steps.AICommitMessage.GENERATING_MESSAGE):
            result = ctx.ai_router.generate_text(
                prompt,
                policy=ai_generate_commit_message,
                cwd=project_root,
                timeout=180,
                max_tokens=1024,
                temperature=0.7,
            )

        match result:
            case AIExecutionSuccess(data=generated_text):
                # Normalize and capitalize whatever the provider returned.
                commit_message = process_ai_commit_message(generated_text)
            case AIExecutionError(error_code="AI_DISABLED", error_message=disabled_message):
                ctx.textual.dim_text(disabled_message)
                ctx.textual.end_step("skip")
                return Skip(disabled_message)
            case AIExecutionError(error_message=err):
                ctx.textual.error_text(err)
                ctx.textual.end_step("error")
                return Error(err)

        # Show preview to user
        ctx.textual.text("")  # spacing
        ctx.textual.bold_text(msg.Steps.AICommitMessage.GENERATED_MESSAGE_TITLE)
        ctx.textual.bold_primary_text(f"  {commit_message}")

        # Warn if message is too long using operations
        is_valid, length = validate_message_length(commit_message, max_length=72)
        if not is_valid:
            ctx.textual.warning_text(msg.Steps.AICommitMessage.MESSAGE_LENGTH_WARNING.format(length=length))

        ctx.textual.text("")  # spacing

        # Ask user if they want to use it
        use_ai = ctx.textual.ask_confirm(
            msg.Steps.AICommitMessage.CONFIRM_USE_MESSAGE,
            default=True
        )

        if not use_ai:
            try:
                manual_message = ctx.textual.ask_text(msg.Prompts.ENTER_COMMIT_MESSAGE)
                if not manual_message:
                    ctx.textual.end_step("error")
                    return Error(msg.Steps.Commit.COMMIT_MESSAGE_REQUIRED)

                # Overwrite the metadata to ensure the manual message is used
                ctx.textual.end_step("success")
                return Success(
                    message=msg.Steps.Prompt.COMMIT_MESSAGE_CAPTURED,
                    metadata={"commit_message": manual_message}
                )
            except (KeyboardInterrupt, EOFError):
                ctx.textual.end_step("error")
                return Error(msg.Steps.Prompt.USER_CANCELLED)

        # Success - save to context
        ctx.textual.end_step("success")
        return Success(
            msg.Steps.AICommitMessage.SUCCESS_MESSAGE,
            metadata={"commit_message": commit_message}
        )

    except Exception as e:
        ctx.textual.error_text(msg.Steps.AICommitMessage.GENERATION_FAILED.format(e=e))

        ctx.textual.end_step("error")
        return Error(msg.Steps.AICommitMessage.GENERATION_FAILED.format(e=e))


# Export for plugin registration
__all__ = ["ai_generate_commit_message"]
