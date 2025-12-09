# plugins/titan-plugin-git/titan_plugin_git/steps/ai_commit_message_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_plugin_git.exceptions import GitCommandError
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
    # Check if AI is configured
    if not ctx.ai or not ctx.ai.is_available():
        return Skip("AI not configured. Run 'titan ai configure' to enable AI features.")

    # Get git client
    if not ctx.git:
        return Error(msg.Steps.CommitMessage.GIT_CLIENT_NOT_AVAILABLE)

    # Get git status
    git_status = ctx.get('git_status')
    if not git_status or git_status.is_clean:
        return Skip("No changes to commit")

    try:
        # Get diff of uncommitted changes
        if ctx.ui:
            ctx.ui.text.info("📊 Analyzing uncommitted changes...")

        # Get all uncommitted changes (staged + unstaged)
        all_files = git_status.modified_files + git_status.untracked_files

        if not all_files:
            return Skip("No files to analyze")

        # Get diff of all uncommitted changes
        diff_text = ctx.git.get_uncommitted_diff()

        if not diff_text or diff_text.strip() == "":
            return Error("No diffs available for analysis")

        # Build AI prompt
        files_summary = "\n".join([f"  - {f}" for f in all_files])

        # Limit diff size to avoid token overflow (keep first 4000 chars)
        diff_preview = diff_text[:4000] if len(diff_text) > 4000 else diff_text
        if len(diff_text) > 4000:
            diff_preview += "\n\n... (diff truncated for brevity)"

        prompt = f"""Analyze these code changes and generate a conventional commit message.

## Changed Files ({len(all_files)} total)
{files_summary}

## Diff
```diff
{diff_preview}
```

## Instructions
Generate a single conventional commit message following this format:
- type(scope): description
- Types: feat, fix, refactor, docs, test, chore, style, perf
- Scope: area affected (e.g., auth, api, ui)
- Description: brief summary in imperative mood (max 72 chars)

Examples:
- feat(auth): add OAuth2 integration
- fix(api): resolve race condition in cache
- refactor(ui): simplify menu component structure

Return ONLY the commit message, nothing else."""

        if ctx.ui:
            ctx.ui.text.info("🤖 Generating commit message with AI...")

        # Call AI
        from titan_cli.ai.models import AIMessage

        messages = [AIMessage(role="user", content=prompt)]
        response = ctx.ai.generate(messages, max_tokens=150, temperature=0.7)

        commit_message = response.content.strip()

        # Clean up the message (remove quotes if present)
        commit_message = commit_message.strip('"').strip("'").strip()

        # Validate message length
        if len(commit_message) > 72:
            # Try to truncate intelligently
            commit_message = commit_message[:69] + "..."

        # Show preview to user
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle("📝 AI Generated Commit Message:")
            ctx.ui.text.body(f"  {commit_message}", style="bold cyan")
            ctx.ui.spacer.small()

            # Ask user if they want to use it
            use_ai = ctx.views.prompts.ask_confirm(
                "Use this commit message?",
                default=True
            )

            if not use_ai:
                return Skip("User declined AI-generated commit message")

        # Success - save to context
        return Success(
            "AI generated commit message",
            metadata={"commit_message": commit_message}
        )

    except Exception as e:
        if ctx.ui:
            ctx.ui.text.warning(f"AI generation failed: {e}")
            ctx.ui.text.info("Falling back to manual commit message...")

        return Skip(f"AI generation failed: {e}")


# Export for plugin registration
__all__ = ["ai_generate_commit_message"]
