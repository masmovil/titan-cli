"""
Worktree Steps

Steps for creating and cleaning up git worktrees.
Available for use in any workflow that needs isolated branch checkouts.
"""
import os
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip
from ..operations import setup_worktree, cleanup_worktree

def create_worktree_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Create a worktree for PR review.

    Requires (from ctx.data):
        selected_pr_number (int): The PR number
        selected_pr_head_branch (str): Branch to checkout in worktree

    Outputs (saved to ctx.data):
        worktree_path (str): Absolute path to worktree
        worktree_created (bool): Whether worktree was created

    Returns:
        Success: Worktree created
        Error: Failed to create worktree
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Create PR Worktree")

    pr_number = ctx.get("selected_pr_number") or ctx.get("review_pr_number")
    head_branch = ctx.get("selected_pr_head_branch") or ctx.get("review_pr_head") or ""

    if not pr_number:
        ctx.textual.end_step("error")
        return Error("Missing required data")

    if not ctx.git:
        ctx.textual.error_text("Git client not available")
        ctx.textual.end_step("error")
        return Error("Git client not available")

    with ctx.textual.loading(f"Creating worktree for PR #{pr_number}..."):
        remote = getattr(ctx.git, 'default_remote', 'origin')
        worktree_path, worktree_created = setup_worktree(
            ctx.git,
            pr_number,
            head_branch,
            remote=remote
        )

    if worktree_created:
        worktree_name = os.path.basename(worktree_path)
        ctx.textual.success_text(f"✓ Worktree created: {worktree_name}")
        ctx.textual.end_step("success")
        return Success(
            "Worktree created",
            metadata={"worktree_path": worktree_path, "worktree_created": True}
        )
    else:
        ctx.textual.error_text("Failed to create worktree")
        ctx.textual.end_step("error")
        return Error("Failed to create worktree")


def cleanup_worktree_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Cleanup a worktree created for PR review.

    Requires (from ctx.data):
        worktree_created (bool): Whether worktree was created
        worktree_path (str): Absolute path to worktree

    Returns:
        Success: Worktree cleaned up
        Skip: Nothing to clean up, no git client, or removal failed

    Never returns Exit: that would stop the whole workflow, and this step may run
    before others (nothing was created is a normal case when worktree setup was
    allowed to fail). Skip keeps the workflow going.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Cleanup PR Worktree")

    worktree_created = ctx.get("worktree_created", False)
    worktree_path = ctx.get("worktree_path")

    if not worktree_created or not worktree_path:
        ctx.textual.dim_text("No worktree to cleanup")
        ctx.textual.end_step("skip")
        return Skip("No worktree to cleanup")

    if not ctx.git:
        ctx.textual.warning_text("Git client not available - cannot cleanup")
        ctx.textual.end_step("skip")
        return Skip("Git client not available")

    with ctx.textual.loading("Cleaning up worktree..."):
        success = cleanup_worktree(ctx.git, worktree_path)

    if success:
        ctx.textual.success_text("✓ Worktree cleaned up")
        ctx.textual.end_step("success")
        return Success("Worktree cleaned up")
    else:
        ctx.textual.warning_text("Failed to cleanup worktree")
        ctx.textual.end_step("skip")
        return Skip("Cleanup failed")


__all__ = [
    "create_worktree_step",
    "cleanup_worktree_step",
]
