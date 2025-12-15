# plugins/titan-plugin-git/titan_plugin_git/steps/ai_commit_message_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_plugin_git.messages import msg


def ai_generate_commit_message(ctx: WorkflowContext) -> WorkflowResult:
    """
    Generate a commit message using AI based on the current changes.

    Uses AI to analyze the diff of uncommitted changes and generate a
    conventional commit message (type(scope): description).

    Requires:
        ctx.git: An initialized GitClient.
        ctx.ai: An initialized AIClient.

    Inputs (from ctx.data):
        git_status: Current git status with changes.

    Outputs (saved to ctx.data):
        commit_message (str): AI-generated commit message.

    Returns:
        Success: If the commit message was generated successfully.
        Error: If the operation fails.
        Skip: If no changes, AI not configured, or user declined.
    """
    # Show step header
    if ctx.views:
        ctx.views.step_header("ai_commit_message", ctx.current_step, ctx.total_steps)

    # Check if AI is configured
    if not ctx.ai or not ctx.ai.is_available():
        if ctx.ui:
            ctx.ui.panel.print(
                msg.Steps.AICommitMessage.AI_NOT_CONFIGURED,
                panel_type="info"
            )
            ctx.ui.spacer.small()
        return Skip(msg.Steps.AICommitMessage.AI_NOT_CONFIGURED)

    # Get git client
    if not ctx.git:
        return Error(msg.Steps.AICommitMessage.GIT_CLIENT_NOT_AVAILABLE)

    # Get git status
    git_status = ctx.get('git_status')
    if not git_status or git_status.is_clean:
        if ctx.ui:
            ctx.ui.panel.print(
                msg.Steps.AICommitMessage.NO_CHANGES_TO_COMMIT,
                panel_type="info"
            )
            ctx.ui.spacer.small()
        return Skip(msg.Steps.AICommitMessage.NO_CHANGES_TO_COMMIT)

    try:
        # Get diff of uncommitted changes
        if ctx.ui:
            ctx.ui.text.info(msg.Steps.AICommitMessage.ANALYZING_CHANGES)

        # Get diff of all uncommitted changes
        diff_text = ctx.git.get_uncommitted_diff()

        if not diff_text or diff_text.strip() == "":
            return Skip(msg.Steps.AICommitMessage.NO_UNCOMMITTED_CHANGES)

        # Build AI prompt
        # Get list of modified files for the summary
        all_files = git_status.modified_files + git_status.untracked_files + git_status.staged_files
        files_summary = "\n".join([f"  - {f}" for f in all_files]) if all_files else "(checking diff)"

        # Limit diff size to avoid token overflow (keep first 4000 chars)
        diff_preview = diff_text[:4000] if len(diff_text) > 4000 else diff_text
        if len(diff_text) > 4000:
            diff_preview += f"\n\n{msg.Steps.AICommitMessage.DIFF_TRUNCATED}"

        prompt = f"""Analyze these code changes and generate a conventional commit message.

## Changed Files ({len(all_files)} total)
{files_summary}

## Diff
```diff
{diff_preview}
```

## CRITICAL Instructions
Generate ONE single-line conventional commit message following this EXACT format:
- type(scope): description
- Types: feat, fix, refactor, docs, test, chore, style, perf
- Scope: area affected (e.g., auth, api, ui)
- Description: clear summary in imperative mood (be descriptive but concise)
- NO line breaks, NO body, NO additional explanation

Examples (notice they are all one line):
- feat(auth): add OAuth2 integration with Google provider
- fix(api): resolve race condition in cache invalidation
- refactor(ui): simplify menu component and remove unused props

Return ONLY the single-line commit message, absolutely nothing else."""

        if ctx.ui:
            ctx.ui.text.info(msg.Steps.AICommitMessage.GENERATING_MESSAGE)

        # Call AI
        from titan_cli.ai.models import AIMessage

        messages = [AIMessage(role="user", content=prompt)]
        response = ctx.ai.generate(messages, max_tokens=150, temperature=0.7)

        commit_message = response.content.strip()

        # Clean up the message (remove quotes, newlines, extra whitespace)
        commit_message = commit_message.strip('"').strip("'").strip()
        # Take only the first line if AI returned multiple lines
        commit_message = commit_message.split('\n')[0].strip()

        # Show preview to user
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle(msg.Steps.AICommitMessage.GENERATED_MESSAGE_TITLE)
            ctx.ui.text.body(f"  {commit_message}", style="bold cyan")

            # Warn if message is too long
            if len(commit_message) > 72:
                ctx.ui.text.warning(msg.Steps.AICommitMessage.MESSAGE_LENGTH_WARNING.format(length=len(commit_message)))

            ctx.ui.spacer.small()

            # Ask user if they want to use it
            use_ai = ctx.views.prompts.ask_confirm(
                msg.Steps.AICommitMessage.CONFIRM_USE_MESSAGE,
                default=True
            )

            if not use_ai:
                return Skip(msg.Steps.AICommitMessage.USER_DECLINED)

        # Show success panel
        if ctx.ui:
            ctx.ui.panel.print(
                "AI commit message generated successfully",
                panel_type="success"
            )
            ctx.ui.spacer.small()

        # Success - save to context
        return Success(
            msg.Steps.AICommitMessage.SUCCESS_MESSAGE,
            metadata={"commit_message": commit_message}
        )

    except Exception as e:
        if ctx.ui:
            ctx.ui.text.warning(msg.Steps.AICommitMessage.GENERATION_FAILED.format(e=e))
            ctx.ui.text.info(msg.Steps.AICommitMessage.FALLBACK_TO_MANUAL)

        return Skip(msg.Steps.AICommitMessage.GENERATION_FAILED.format(e=e))


# Export for plugin registration
__all__ = ["ai_generate_commit_message"]
