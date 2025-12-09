# plugins/titan-plugin-git/titan_plugin_git/steps/handle_changes_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from titan_plugin_git.messages import msg


def handle_uncommitted_changes_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Handles uncommitted changes before creating a PR.

    If there are uncommitted changes, prompts the user to:
    1. Commit them (optionally with AI-generated message)
    2. Stash them
    3. Cancel the operation

    Requires:
        ctx.git: An initialized GitClient.
        ctx.views.prompts: A PromptsRenderer instance.

    Inputs (from ctx.data):
        git_status (GitStatus): The git status object.
        ai_available (bool, optional): Whether AI is available for commit messages.

    Outputs (saved to ctx.data):
        stashed_changes (bool): True if changes were stashed.
        commit_hash (str, optional): The hash of the created commit if user chose to commit.

    Returns:
        Success: If changes were handled successfully (committed or stashed).
        Error: If the operation fails or user cancels.
        Skip: If there are no uncommitted changes.
    """
    # Skip if working directory is clean
    git_status = ctx.data.get("git_status")
    if not git_status or git_status.is_clean:
        return Skip(msg.Steps.HandleChanges.NO_UNCOMMITTED_CHANGES, silent=True)

    if not ctx.git:
        return Error(msg.Steps.HandleChanges.GIT_CLIENT_NOT_AVAILABLE)

    # Show uncommitted changes summary
    changes_summary = []
    if git_status.staged_files:
        changes_summary.append(f"Staged files: {len(git_status.staged_files)}")
    if git_status.modified_files:
        changes_summary.append(f"Modified files: {len(git_status.modified_files)}")
    if git_status.untracked_files:
        changes_summary.append(f"Untracked files: {len(git_status.untracked_files)}")

    ctx.ui.text.warning(msg.Steps.HandleChanges.UNCOMMITTED_CHANGES_WARNING.format(
        summary=', '.join(changes_summary)
    ))

    # Generate AI commit message directly (no menu)
    try:
        # If AI available, generate commit message automatically
        if ctx.ai:
            # Get uncommitted diff
            diff = ctx.git.get_uncommitted_diff()
            if not diff:
                return Error(msg.Steps.HandleChanges.NO_CHANGES_TO_COMMIT)

            # Build AI prompt
            all_files = git_status.modified_files + git_status.untracked_files + git_status.staged_files
            files_summary = "\n".join([f"  - {f}" for f in all_files]) if all_files else "(checking diff)"

            # Limit diff size to avoid token overflow
            diff_preview = diff[:4000] if len(diff) > 4000 else diff
            if len(diff) > 4000:
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

            ctx.ui.text.info(msg.Steps.HandleChanges.AI_GENERATING)

            # Call AI
            from titan_cli.ai.models import AIMessage
            messages = [AIMessage(role="user", content=prompt)]
            response = ctx.ai.generate(messages, max_tokens=150, temperature=0.7)

            commit_message = response.content.strip().strip('"').strip("'").strip()

            # Show the message and ask for confirmation
            ctx.ui.text.info(msg.Steps.HandleChanges.AI_GENERATED_MESSAGE)
            ctx.ui.text.info(f"\n{commit_message}\n")

            confirm = ctx.views.prompts.ask_confirm(
                msg.Steps.HandleChanges.AI_CONFIRM_PROMPT,
                default=True
            )

            if confirm:
                # Commit with AI message
                commit_hash = ctx.git.commit(message=commit_message, all=True)
                ctx.ui.text.success(msg.Steps.HandleChanges.COMMIT_SUCCESS.format(
                    commit_hash_short=commit_hash[:8]
                ))
                return Success(
                    msg.Steps.HandleChanges.COMMIT_SUCCESS_AI.format(commit_hash=commit_hash),
                    metadata={"commit_hash": commit_hash, "commit_message": commit_message}
                )
            # If user rejects, fall through to manual commit below

        # Manual commit (fallback if no AI or user rejected AI suggestion)
        ctx.ui.text.info("Enter your commit message manually:")
        commit_message = ctx.views.prompts.ask_multiline(
            msg.Steps.HandleChanges.COMMIT_PROMPT,
            default_text=msg.Steps.HandleChanges.COMMIT_PROMPT_DEFAULT
        )

        if not commit_message or commit_message.strip().startswith("#"):
            return Error(msg.Steps.HandleChanges.COMMIT_MESSAGE_EMPTY)

        # Commit changes
        commit_hash = ctx.git.commit(message=commit_message, all=True)
        ctx.ui.text.success(msg.Steps.HandleChanges.COMMIT_SUCCESS.format(
            commit_hash_short=commit_hash[:8]
        ))
        return Success(
            msg.Steps.HandleChanges.COMMIT_SUCCESS_FULL.format(commit_hash=commit_hash),
            metadata={"commit_hash": commit_hash, "commit_message": commit_message}
        )

    except (KeyboardInterrupt, EOFError):
        return Error(msg.Steps.HandleChanges.USER_CANCELLED_OPERATION)
    except Exception as e:
        return Error(msg.Steps.HandleChanges.HANDLE_CHANGES_FAILED.format(e=e))
