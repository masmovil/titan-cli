"""
Steps for reviewing and addressing PR comments.

This module contains steps for reviewing PR comments and UI helpers
to keep the main step functions clean and readable.
"""
import json
import os
import traceback
from typing import List, Dict
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Exit, Skip
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ports.protocol import InteractionAction, InteractionOption
from ..models import UICommentThread
from ..operations import (
    fetch_pr_threads,
    fetch_pr_general_comments,
    build_quote_reply,
    build_ai_review_context,
    build_ai_review_prompt,
    find_ai_response_file,
    create_commit_message,
    reply_to_comment_batch,
    prepare_replies_for_sending,
    build_pr_selection_description,
    build_pr_selection_title,
)
from titan_plugin_git.operations import format_diff_stat_display

def _show_thread_and_get_action(
    ctx: WorkflowContext,
    pr_thread: UICommentThread,
    thread_idx: int,
    total_threads: int
) -> str:
    """
    Display a comment thread and get user's action choice.

    Args:
        ctx: Workflow context
        pr_thread: The PR review thread (UI model)
        thread_idx: Current thread index (0-based)
        total_threads: Total number of threads

    Returns:
        User's choice: "ai_review", "reply", "skip", "resolve", or "exit"
    """

    actions = [
        InteractionAction(id="ai_review", label="AI Review", variant="primary"),
        InteractionAction(id="change_manually", label="Change"),
        InteractionAction(id="reply", label="Reply"),
        InteractionAction(id="skip", label="Skip"),
    ]

    # "Resolve" only applies to inline review threads, not general PR comments
    if not pr_thread.is_general_comment:
        actions.append(InteractionAction(id="resolve", label="Resolve", variant="success"))

    # Add "Exit" option if not the last thread
    if thread_idx < total_threads - 1:
        actions.append(InteractionAction(id="exit", label="Exit", variant="warning"))

    main = pr_thread.main_comment
    thread_title = f"Thread {thread_idx + 1} of {total_threads}"
    location = main.path or "General PR comment"
    if main.line is not None:
        location = f"{location}:{main.line}"

    ctx.interaction.display_structured_summary(
        title=thread_title,
        summary_lines=[
            f"{main.author_name or main.author_login} · {main.formatted_date}",
            location,
        ],
        sections=[],
        metadata={
            "presentation": "review_thread",
            "thread_id": pr_thread.thread_id,
            "resolved": pr_thread.is_resolved,
            "outdated": pr_thread.is_outdated,
        },
    )
    ctx.interaction.markdown(main.body)
    if main.diff_hunk:
        ctx.interaction.display_diff(
            main.diff_hunk,
            title=location,
            metadata={"presentation": "focused_hunk", "path": main.path, "line": main.line},
        )
    for reply in pr_thread.replies:
        ctx.interaction.display_structured_summary(
            title=f"Reply from {reply.author_name or reply.author_login}",
            summary_lines=[reply.formatted_date],
            sections=[],
            metadata={"presentation": "review_reply", "comment_id": reply.id},
        )
        ctx.interaction.markdown(reply.body)

    return ctx.interaction.action_list(
        interaction_id=f"review-thread:{pr_thread.thread_id}",
        message="What would you like to do?",
        actions=actions,
        state={
            "presentation": "review_thread_actions",
            "thread_id": pr_thread.thread_id,
            "thread_index": thread_idx,
            "total_threads": total_threads,
            "is_general_comment": pr_thread.is_general_comment,
        },
    )


def _commit_review_changes(
    ctx: WorkflowContext,
    main_comment,
    comment_commits: Dict[int, str]
) -> bool:
    """
    Show diff stat and commit uncommitted changes.

    Assumes changes are already detected. Shows the diff stat, then commits
    using the standard review commit message format.

    Args:
        ctx: Workflow context
        main_comment: The comment being addressed (for commit message)
        comment_commits: Dict to store commit hash (mutated in place)

    Returns:
        True if commit succeeded, False otherwise
    """
    stat_result = ctx.git.get_uncommitted_diff_stat()
    match stat_result:
        case ClientSuccess(data=stat_output) if stat_output.strip():
            formatted_files, formatted_summary = format_diff_stat_display(stat_output)
            ctx.textual.show_diff_stat(formatted_files, formatted_summary, use_panel=True)
        case _:
            ctx.textual.dim_text("Changes detected")

    ctx.textual.text("")
    commit_msg = create_commit_message(
        main_comment.body,
        main_comment.author_login,
        main_comment.path
    )

    with ctx.textual.loading("Committing changes..."):
        # no_verify=True: skip pre-commit hooks during AI review fixes to avoid
        # blocking on linting/formatting hooks mid-workflow
        commit_result = ctx.git.commit(commit_msg, all=True, no_verify=True)

    match commit_result:
        case ClientSuccess(data=commit_hash):
            ctx.textual.success_text(f"✓ Committed: {commit_hash[:8]}")
            comment_commits[main_comment.id] = commit_hash
            return True
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to commit: {err}")
            return False


def _handle_manual_reply(
    ctx: WorkflowContext,
    pr_thread: UICommentThread,
    pending_responses: Dict[int, str]
) -> bool:
    """
    Handle manual reply to a comment thread.

    Args:
        ctx: Workflow context
        pr_thread: The PR review thread
        pending_responses: Dict to accumulate responses for batch sending

    Returns:
        True if reply was added, False if skipped
    """
    ctx.textual.text("")
    reply_text = ctx.textual.ask_multiline(
        "Enter your reply:",
        default=""
    )

    if reply_text and reply_text.strip():
        main_comment_id = pr_thread.main_comment.id
        pending_responses[main_comment_id] = {"text": reply_text, "source": "manual"}
        ctx.textual.success_text("✓ Reply queued for review")
        return True
    else:
        ctx.textual.warning_text("Empty reply, skipping")
        return False


def _handle_ai_review(
    ctx: WorkflowContext,
    pr_thread: UICommentThread,
    pr_title: str,
    comment_commits: Dict[int, str],
    pending_responses: Dict[int, str],
    response_files: List[str]
) -> bool:
    """
    Handle AI review for a comment thread.

    Works directly on the current branch (no worktree).

    Args:
        ctx: Workflow context
        pr_thread: The PR review thread (UI model)
        pr_title: PR title for context
        comment_commits: Dict to track commits (will be updated)
        pending_responses: Dict to track responses (will be updated)
        response_files: List to track temp files (will be updated)

    Returns:
        True if processed successfully, False if failed
    """
    try:
        main_comment = pr_thread.main_comment

        # Build AI review context using operation
        review_context = build_ai_review_context(pr_thread, pr_title)

        # Store JSON context
        context_json = json.dumps(review_context, indent=2)
        ctx.data["pr_review_context"] = context_json

        # Prepare response file path for AI to save explanations
        response_file = f"/tmp/titan-ai-response-comment-{main_comment.id}.txt"
        response_files.append(response_file)

        # Clean up any existing response file
        if os.path.exists(response_file):
            os.remove(response_file)

        # Import and call ai_assistant_step
        from titan_cli.engine.steps.ai_assistant_step import execute_ai_assistant_step
        from titan_cli.core.workflows.models import WorkflowStepModel

        ai_step = WorkflowStepModel(
            id="ai_review_helper",
            plugin="core",
            step="ai_code_assistant",
            name="AI Code Review",
            params={
                "context_key": "pr_review_context",
                "prompt_template": build_ai_review_prompt(response_file),
                "ask_confirmation": False,
                "pre_launch_warning": "When you're done using the AI CLI, press Ctrl+C twice to exit and return to Titan.",
            }
        )

        # Launch AI assistant (works directly on current branch)
        execute_ai_assistant_step(ai_step, ctx)

        # Check if AI made any code changes
        ctx.textual.text("")

        has_changes_result = ctx.git.has_uncommitted_changes()
        match has_changes_result:
            case ClientSuccess(data=has_changes):
                pass
            case ClientError():
                has_changes = False

        if has_changes:
            if not _commit_review_changes(ctx, main_comment, comment_commits):
                return False

        else:
            # No code changes - check for text response
            response_found_at = find_ai_response_file(main_comment.id, response_file)

            if response_found_at:
                with open(response_found_at, 'r') as f:
                    ai_response = f.read().strip()

                ctx.textual.panel(
                    "No code changes — AI wrote a response, queued for review at the end",
                    panel_type="success",
                    show_icon=False,
                )
                pending_responses[main_comment.id] = {"text": ai_response, "source": "ai"}
            else:
                ctx.textual.panel(
                    "No code changes and no response file found — AI may have skipped this comment",
                    panel_type="warning",
                    show_icon=False,
                )
                return False

        return True

    except Exception as e:
        ctx.textual.error_text(f"AI review error: {e}")
        ctx.textual.dim_text(traceback.format_exc())
        return False


def _handle_manual_change(
    ctx: WorkflowContext,
    pr_thread: UICommentThread,
    comment_commits: Dict[int, str]
) -> bool:
    """
    Handle manual code changes by the user.

    Instructs the user to make changes, waits for confirmation,
    then detects and commits any changes found.

    Args:
        ctx: Workflow context
        pr_thread: The PR review thread being addressed
        comment_commits: Dict mapping comment ID → commit hash (mutated in place)

    Returns:
        True if changes were detected and committed, False otherwise
    """
    main_comment = pr_thread.main_comment
    if not main_comment:
        ctx.textual.error_text("No comment found in thread")
        return False

    ctx.textual.text("")
    ctx.textual.panel(
        "Go make your code changes in your editor, then come back here and confirm.",
        panel_type="warning",
        show_icon=False,
    )
    ctx.textual.text("")

    confirmed = ctx.textual.ask_confirm("I've made my changes", default=True)

    if not confirmed:
        ctx.textual.dim_text("Manual change cancelled")
        return False

    # Check for uncommitted changes
    has_changes_result = ctx.git.has_uncommitted_changes()
    match has_changes_result:
        case ClientSuccess(data=has_changes):
            pass
        case ClientError():
            has_changes = False

    if not has_changes:
        ctx.textual.panel(
            "No changes detected. Make sure you saved your files.",
            panel_type="warning",
            show_icon=False,
        )
        return False

    return _commit_review_changes(ctx, main_comment, comment_commits)


def _handle_resolve_thread(
    ctx: WorkflowContext,
    pr_thread: UICommentThread
) -> bool:
    """
    Handle resolving a review thread.

    Args:
        ctx: Workflow context
        pr_thread: The PR review thread to resolve

    Returns:
        True if resolved successfully, False if failed
    """
    thread_id = pr_thread.thread_id
    if not thread_id:
        ctx.textual.error_text("Cannot resolve thread: missing thread ID")
        return False

    with ctx.textual.loading("Resolving thread..."):
        result = ctx.github.resolve_review_thread(thread_id)

    match result:
        case ClientSuccess():
            ctx.textual.success_text("Thread resolved")
            return True
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to resolve thread: {err}")
            return False

def select_pr_for_review_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Select a PR from the user's open PRs to review comments.

    Outputs (saved to ctx.data):
        selected_pr_number (int): The selected PR number
        selected_pr_title (str): The selected PR title

    Returns:
        Success: PR selected successfully
        Exit: No PRs available or user cancelled
        Error: Failed to fetch PRs
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Select PR for Review")

    # Get GitHub client
    if not ctx.github:
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    # Fetch user's open PRs (returns ClientResult[List[UIPullRequest]])
    with ctx.textual.loading("Fetching your open PRs..."):
        result = ctx.github.list_my_prs(state="open")

    match result:
        case ClientSuccess(data=prs):
            if not prs:
                ctx.textual.dim_text("You don't have any open PRs.")
                ctx.textual.end_step("success")
                return Exit("No open PRs found")

            # Create options from PRs
            options = []
            for pr in prs:
                options.append(
                    InteractionOption(
                        id=str(pr.number),
                        value=pr.number,
                        label=build_pr_selection_title(pr),
                        description=f"Branch: {build_pr_selection_description(pr)}",
                    )
                )

            # Ask user to select a PR
            try:
                selected = ctx.textual.ask_option(
                    f"Select a PR to review comments ({len(prs)} open PR(s)):",
                    options
                )

                if not selected:
                    ctx.textual.warning_text("No PR selected")
                    ctx.textual.end_step("skip")
                    return Exit("User cancelled PR selection")

                pr_number = selected
                selected_pr = next((pr for pr in prs if pr.number == pr_number), None)

                if not selected_pr:
                    ctx.textual.end_step("error")
                    return Error(f"PR #{pr_number} not found")

                # Save to context
                metadata = {
                    "selected_pr_number": pr_number,
                    "selected_pr_title": selected_pr.title,
                    "selected_pr_head_branch": selected_pr.head_ref,
                    "selected_pr_base_branch": selected_pr.base_ref,
                }

                ctx.textual.success_text(f"Selected PR #{pr_number}: {selected_pr.title}")
                ctx.textual.end_step("success")

                return Success(
                    f"Selected PR #{pr_number}",
                    metadata=metadata
                )

            except Exception as e:
                ctx.textual.error_text(f"Failed during PR selection: {e}")
                ctx.textual.end_step("error")
                return Error(str(e))

        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to fetch PRs: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to fetch PRs: {err}")


def fetch_pending_comments_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Fetch unresolved review threads for the selected PR using GraphQL.

    Requires (from ctx.data):
        selected_pr_number (int): The PR number

    Outputs (saved to ctx.data):
        review_threads (List[UICommentThread]): Unresolved review threads

    Returns:
        Success: Threads fetched
        Exit: No unresolved threads
        Error: Failed to fetch threads
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Fetch Pending Comments")

    pr_number = ctx.get("selected_pr_number")
    if not pr_number:
        ctx.textual.end_step("error")
        return Error("No PR selected")

    if not ctx.github:
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    try:
        with ctx.textual.loading(f"Fetching comments for PR #{pr_number}..."):
            review_threads = fetch_pr_threads(ctx.github, pr_number, include_resolved=False)
            general_comments = fetch_pr_general_comments(ctx.github, pr_number)

        all_threads = general_comments + review_threads

        if not all_threads:
            ctx.textual.dim_text(f"No pending comments found for PR #{pr_number}")
            ctx.textual.end_step("skip")
            return Exit("No pending comments")

        parts = []
        if general_comments:
            parts.append(f"{len(general_comments)} general comment(s)")
        if review_threads:
            parts.append(f"{len(review_threads)} review thread(s)")
        ctx.textual.success_text(f"Found {', '.join(parts)}")

        metadata = {
            "review_threads": all_threads,
            "total_pending": len(all_threads),
        }

        ctx.textual.end_step("success")

        return Success(
            f"Found {len(all_threads)} comment(s)",
            metadata=metadata
        )

    except Exception as e:
        ctx.textual.error_text(f"Failed to fetch comments: {e}")
        ctx.textual.end_step("error")
        return Error(str(e))


def check_clean_state_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Check that the working tree is clean before checking out the PR branch.

    If there are uncommitted changes, the workflow exits with instructions
    for the user to stash them manually.

    Returns:
        Success: Working tree is clean
        Exit: Uncommitted changes detected — user must stash manually
        Error: Failed to check status
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Check Branch State")

    if not ctx.git:
        ctx.textual.end_step("error")
        return Error("Git client not available")

    result = ctx.git.has_uncommitted_changes()
    match result:
        case ClientSuccess(data=has_changes):
            if has_changes:
                ctx.textual.error_text("Your branch has uncommitted changes.")
                ctx.textual.text("")
                ctx.textual.dim_text("Please stash or commit them before switching to the PR branch:")
                ctx.textual.dim_text("  git stash")
                ctx.textual.end_step("error")
                return Exit("Uncommitted changes detected — stash them and try again")

            ctx.textual.success_text("✓ Branch is clean")
            ctx.textual.end_step("success")
            return Success("Branch is clean")

        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to check git status: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to check git status: {err}")


def checkout_pr_branch_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Save the current branch and checkout the PR branch.

    Requires (from ctx.data):
        selected_pr_number (int): The PR number
        selected_pr_head_branch (str): Branch to checkout

    Outputs (saved to ctx.data):
        original_branch (str): Branch to restore after review

    Returns:
        Success: PR branch checked out
        Error: Failed to fetch or checkout
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Checkout PR Branch")

    if not ctx.git:
        ctx.textual.end_step("error")
        return Error("Git client not available")

    pr_number = ctx.get("selected_pr_number")
    head_branch = ctx.get("selected_pr_head_branch", "")

    if not pr_number or not head_branch:
        ctx.textual.end_step("error")
        return Error("Missing PR number or branch")

    # Save current branch to restore later
    current_branch_result = ctx.git.get_current_branch()
    match current_branch_result:
        case ClientSuccess(data=current_branch):
            pass
        case ClientError(error_message=err):
            ctx.textual.end_step("error")
            return Error(f"Failed to get current branch: {err}")

    # Fetch the PR branch
    with ctx.textual.loading(f"Fetching {head_branch}..."):
        fetch_result = ctx.git.fetch("origin", head_branch)

    match fetch_result:
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to fetch branch: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to fetch {head_branch}: {err}")
        case ClientSuccess():
            pass

    # Checkout the PR branch
    with ctx.textual.loading(f"Checking out {head_branch}..."):
        checkout_result = ctx.git.checkout(head_branch)

    match checkout_result:
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to checkout {head_branch}: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to checkout: {err}")
        case ClientSuccess():
            pass

    # Pull to sync with origin
    with ctx.textual.loading(f"Pulling latest changes for {head_branch}..."):
        pull_result = ctx.git.pull("origin", head_branch)

    match pull_result:
        case ClientError(error_message=err):
            if "conflict" in err.lower():
                ctx.textual.error_text("Merge conflicts detected after pull.")
                ctx.textual.text("")
                ctx.textual.dim_text("Please resolve the conflicts manually and try again:")
                ctx.textual.dim_text("  git status")
                ctx.textual.dim_text("  git mergetool")
                ctx.textual.end_step("error")
                # Restore original branch before exiting
                ctx.git.checkout(current_branch)
                return Exit("Merge conflicts detected — resolve them and try again")
            else:
                ctx.textual.warning_text(f"Pull failed: {err}")
        case ClientSuccess():
            pass

    ctx.textual.success_text(f"✓ On branch {head_branch}, up to date")
    ctx.textual.end_step("success")
    return Success(
        f"Checked out {head_branch}",
        metadata={"original_branch": current_branch}
    )


def review_comments_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Review all unresolved comment threads one by one and take action.

    Works directly on the current branch (PR branch must already be checked out).

    Requires (from ctx.data):
        selected_pr_number (int): The PR number
        review_threads (List[UICommentThread]): Unresolved threads

    Returns:
        Success: All threads processed
        Error: Failed to process threads
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Review Comments")

    response_files = []  # Track temp files for cleanup (must be before try for finally)
    try:
        pr_number = ctx.get("selected_pr_number")
        review_threads: List[UICommentThread] = ctx.get("review_threads", [])
        pr_title = ctx.get("selected_pr_title", "")

        if not pr_number or not review_threads:
            ctx.textual.end_step("error")
            return Error("Missing required data")

        # Track state
        comment_commits = {}
        pending_responses = {}
        general_comment_ids = {
            t.main_comment.id
            for t in review_threads
            if t.is_general_comment and t.main_comment
        }
        processed_count = 0
        skipped_count = 0

        # Loop through all review threads
        for thread_idx, pr_thread in enumerate(review_threads):
            choice = _show_thread_and_get_action(ctx, pr_thread, thread_idx, len(review_threads))

            if choice == "exit":
                ctx.textual.warning_text(f"Exiting review. Processed {processed_count}, skipped {skipped_count}")
                ctx.textual.end_step("success")
                return Success(
                    "Review exited early",
                    metadata={
                        "processed_count": processed_count,
                        "skipped_count": skipped_count,
                        "total_threads": len(review_threads),
                        "comment_commits": comment_commits,
                        "pending_responses": pending_responses,
                        "general_comment_ids": list(general_comment_ids),
                    }
                )

            elif choice == "skip":
                skipped_count += 1

            elif choice == "change_manually":
                if _handle_manual_change(ctx, pr_thread, comment_commits):
                    processed_count += 1
                else:
                    skipped_count += 1

            elif choice == "reply":
                if _handle_manual_reply(ctx, pr_thread, pending_responses):
                    processed_count += 1
                else:
                    skipped_count += 1

            elif choice == "ai_review":
                if _handle_ai_review(
                    ctx, pr_thread, pr_title,
                    comment_commits, pending_responses, response_files
                ):
                    processed_count += 1
                else:
                    skipped_count += 1

            elif choice == "resolve":
                if _handle_resolve_thread(ctx, pr_thread):
                    processed_count += 1
                else:
                    skipped_count += 1

        ctx.textual.text("")
        ctx.textual.success_text(
            f"Review complete! Processed {processed_count}, skipped {skipped_count} "
            f"out of {len(review_threads)} thread(s)"
        )
        if pending_responses:
            ctx.textual.dim_text(f"  • {len(pending_responses)} response(s) ready to send")

        ctx.textual.end_step("success")

        return Success(
            f"Reviewed {len(review_threads)} comment thread(s)",
            metadata={
                "processed_count": processed_count,
                "skipped_count": skipped_count,
                "total_threads": len(review_threads),
                "comment_commits": comment_commits,
                "pending_responses": pending_responses,
                "general_comment_ids": list(general_comment_ids),
            }
        )

    except Exception as e:
        error_msg = f"Error in review_comments_step: {str(e)}"
        ctx.textual.error_text(error_msg)
        ctx.textual.text("")
        ctx.textual.dim_text(traceback.format_exc())
        ctx.textual.end_step("error")
        return Error(error_msg)

    finally:
        # Cleanup temporary AI response files
        for response_file in response_files:
            try:
                if os.path.exists(response_file):
                    os.remove(response_file)
            except Exception:
                pass


def push_commits_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Push commits to PR branch.

    Requires (from ctx.data):
        selected_pr_head_branch (str): Branch to push to
        comment_commits (Dict[int, str]): Map of comment_id -> commit_hash

    Outputs (saved to ctx.data):
        push_successful (bool): Whether push succeeded

    Returns:
        Success: Commits pushed
        Skip: No commits to push or user cancelled
        Error: Failed to push
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Push Commits")

    head_branch = ctx.get("selected_pr_head_branch", "")
    comment_commits = ctx.get("comment_commits", {})

    if not ctx.git:
        ctx.textual.error_text("Git client not available")
        ctx.textual.end_step("error")
        return Error("Git client not available")

    if not comment_commits:
        ctx.textual.dim_text("No commits to push")
        ctx.textual.end_step("skip")
        return Skip("No commits to push")

    # Show commits to push
    ctx.textual.bold_text(f"Push {len(comment_commits)} commit(s) to `{head_branch}`")

    # Ask confirmation
    should_push = ctx.textual.ask_confirm(
        "Do you want to push these commit(s) to the PR branch?",
        default=True
    )

    if not should_push:
        ctx.textual.dim_text("Push cancelled")
        ctx.textual.end_step("skip")
        return Skip("Push cancelled by user", metadata={"push_successful": False})

    with ctx.textual.loading(f"Pushing to {head_branch}..."):
        push_result = ctx.git.push(branch=head_branch)

    match push_result:
        case ClientSuccess():
            ctx.textual.success_text(f"✓ Pushed {len(comment_commits)} commit(s) to {head_branch}")
            ctx.textual.end_step("success")
            return Success(
                f"Pushed {len(comment_commits)} commits",
                metadata={"push_successful": True}
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to push: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to push: {err}", metadata={"push_successful": False})


def send_comment_replies_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Send comment replies (both text responses and commit hashes).

    Requires (from ctx.data):
        selected_pr_number (int): The PR number
        comment_commits (Dict[int, str]): Map of comment_id -> commit_hash
        pending_responses (Dict[int, Dict]): Map of comment_id -> {"text": ..., "source": ...}
        push_successful (bool): Whether push succeeded

    Returns:
        Success: Replies sent
        Skip: No replies to send or user cancelled
        Error: Failed to send replies
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Send Comment Replies")

    pr_number = ctx.get("selected_pr_number")
    comment_commits = ctx.get("comment_commits", {})
    pending_responses = ctx.get("pending_responses", {})
    push_successful = ctx.get("push_successful", False)
    general_comment_ids = set(ctx.get("general_comment_ids", []))

    replies_to_send = prepare_replies_for_sending(
        pending_responses,
        comment_commits,
        push_successful
    )

    if not replies_to_send:
        ctx.textual.dim_text("No replies to send")
        ctx.textual.end_step("skip")
        return Skip("No replies to send")

    # Build thread lookup for context display
    review_threads: List[UICommentThread] = ctx.get("review_threads", [])
    thread_by_id = {}
    for thread in review_threads:
        if thread.main_comment:
            thread_by_id[thread.main_comment.id] = thread

    # Let user review, edit, or skip each reply before sending
    final_replies = {}
    total = len(replies_to_send)

    for i, (comment_id, reply_text) in enumerate(replies_to_send.items(), 1):
        ctx.textual.text("")

        thread = thread_by_id.get(comment_id)
        if thread and thread.main_comment:
            mc = thread.main_comment
            filename = mc.path.split('/')[-1] if mc.path else "General"
            ctx.textual.dim_text(f"Reply {i}/{total} — {mc.author_login} on {filename}")

            # Show a short snippet of the original comment as context
            if mc.body:
                first_line = mc.body.splitlines()[0].strip()
                snippet = first_line[:120] + "…" if len(first_line) > 120 else first_line
                if snippet:
                    ctx.textual.dim_text(f"  > {snippet}")
        else:
            ctx.textual.dim_text(f"Reply {i}/{total}")

        ctx.textual.text("")
        for line in reply_text.splitlines():
            ctx.textual.text(f"  {line}")

        choice = ctx.textual.ask_choice(
            "What would you like to do?",
            options=[
                InteractionOption(id="send", value="send", label="Send"),
                InteractionOption(id="edit", value="edit", label="Edit"),
                InteractionOption(id="skip", value="skip", label="Skip"),
            ]
        )

        if choice == "send":
            final_replies[comment_id] = reply_text
        elif choice == "edit":
            edited = ctx.textual.ask_multiline("Edit reply:", default=reply_text)
            if edited and edited.strip():
                final_replies[comment_id] = edited.strip()
            else:
                ctx.textual.dim_text("Empty reply, skipping")

    if not final_replies:
        skipped = total - len(final_replies)
        ctx.textual.dim_text(f"No replies sent ({skipped}/{total} skipped)")
        ctx.textual.end_step("skip")
        return Skip("No replies sent")

    # Split replies: general comments use add_issue_comment, review comments use reply_to_comment.
    # A general comment has no thread for the reply to land in, so quote the
    # original (GitHub's "quote reply") to tie the new issue comment back to it.
    general_replies = {}
    for cid, text in final_replies.items():
        if cid not in general_comment_ids:
            continue
        thread = thread_by_id.get(cid)
        if thread and thread.main_comment and thread.main_comment.body:
            general_replies[cid] = build_quote_reply(thread.main_comment.body, text)
        else:
            general_replies[cid] = text
    review_replies = {cid: text for cid, text in final_replies.items() if cid not in general_comment_ids}

    with ctx.textual.loading(f"Sending {len(final_replies)} reply(s)..."):
        results = {}
        for comment_id, text in general_replies.items():
            result = ctx.github.add_issue_comment(pr_number, text)
            match result:
                case ClientSuccess():
                    results[comment_id] = True
                case ClientError():
                    results[comment_id] = False
        results.update(reply_to_comment_batch(ctx.github, pr_number, review_replies))

    replied_count = sum(results.values())
    failed_count = len(results) - replied_count

    if replied_count > 0:
        ctx.textual.success_text(f"✓ Sent {replied_count} reply(s)")
    if failed_count > 0:
        ctx.textual.warning_text(f"⚠ Failed to send {failed_count} reply(s)")

    ctx.textual.end_step("success")

    return Success(
        f"Sent {replied_count} replies",
        metadata={"replies_sent": replied_count, "replies_failed": failed_count}
    )


def request_review_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Re-request review from existing reviewers.

    Requires (from ctx.data):
        selected_pr_number (int): The PR number
        push_successful (bool): Whether push succeeded

    Returns:
        Success: Review re-requested
        Skip: Push didn't succeed or user cancelled
        Error: Failed to request review
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Review Requested")

    pr_number = ctx.get("selected_pr_number")
    push_successful = ctx.get("push_successful", False)

    if not push_successful:
        ctx.textual.dim_text("Skipping re-request (no commits were pushed)")
        ctx.textual.end_step("skip")
        return Skip("No commits pushed")

    should_rerequest = ctx.textual.ask_confirm(
        "Do you want to re-request review from existing reviewers?",
        default=True
    )

    if not should_rerequest:
        ctx.textual.dim_text("Re-request cancelled")
        ctx.textual.end_step("skip")
        return Skip("Re-request cancelled by user")

    with ctx.textual.loading("Re-requesting review..."):
        result = ctx.github.request_pr_review(pr_number)

    match result:
        case ClientSuccess(message=msg):
            ctx.textual.success_text(f"✓ {msg}")
            ctx.textual.end_step("success")
            return Success("Review re-requested")
        case ClientError(error_message=err):
            ctx.textual.warning_text(f"Re-request partially failed: {err}")
            ctx.textual.dim_text("Some reviewers may have been skipped (e.g., bots)")
            ctx.textual.end_step("success")
            return Success("Review re-requested (partial)")


def checkout_original_branch_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Restore the original branch after PR review.

    Requires (from ctx.data):
        original_branch (str): Branch to restore

    Returns:
        Success: Restored to original branch
        Exit: No original branch saved or checkout failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Restore Branch")

    original_branch = ctx.get("original_branch")

    if not original_branch:
        ctx.textual.dim_text("No original branch to restore")
        ctx.textual.end_step("skip")
        return Exit("No original branch to restore")

    if not ctx.git:
        ctx.textual.warning_text("Git client not available — could not restore branch")
        ctx.textual.end_step("skip")
        return Exit("Git client not available")

    with ctx.textual.loading(f"Checking out {original_branch}..."):
        result = ctx.git.checkout(original_branch)

    match result:
        case ClientSuccess():
            ctx.textual.success_text(f"✓ Back on {original_branch}")
            ctx.textual.end_step("success")
            return Success(f"Restored to {original_branch}")
        case ClientError(error_message=err):
            ctx.textual.warning_text(f"Failed to restore branch: {err}")
            ctx.textual.end_step("skip")
            return Exit(f"Failed to restore: {err}")


# Export for plugin registration
__all__ = [
    "select_pr_for_review_step",
    "fetch_pending_comments_step",
    "check_clean_state_step",
    "checkout_pr_branch_step",
    "review_comments_step",
    "push_commits_step",
    "send_comment_replies_step",
    "request_review_step",
    "checkout_original_branch_step",
]
