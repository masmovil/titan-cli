"""Activate and clean up an isolated worktree workflow context."""

from pathlib import Path

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext, WorkflowResult

from ..clients.git_client import GitClient


def activate_worktree_context(ctx: WorkflowContext) -> WorkflowResult:
    """
    Route subsequent workflow operations through a created worktree.

    Requires:
        ctx.git: The GitClient for the main working tree.

    Inputs (from ctx.data):
        worktree_path (str): Existing worktree directory.
        base_branch (str, optional): Main branch for comparisons in nested workflows.

    Outputs (saved to ctx.data):
        project_root (str): Worktree path used by commands, tests, and AI CLIs.
        worktree_context_active (bool): Whether routing to the worktree is active.

    Returns:
        Success: If the workflow context now targets the worktree.
        Error: If the Git client or worktree path is unavailable.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Activate Worktree Context")
    if not ctx.git:
        ctx.textual.end_step("error")
        return Error("Git client is not available in context")

    worktree_path = ctx.get("worktree_path")
    if not worktree_path or not Path(worktree_path).is_dir():
        ctx.textual.end_step("error")
        return Error("A valid worktree_path is required")

    original_git = ctx.git
    worktree_git = GitClient(
        repo_path=worktree_path,
        main_branch=ctx.get("base_branch") or original_git.main_branch,
        default_remote=ctx.get("remote") or original_git.default_remote,
    )

    ctx._original_worktree_git = original_git
    ctx._original_project_root = ctx.data.get("project_root")
    ctx._had_original_project_root = "project_root" in ctx.data
    ctx.git = worktree_git
    if ctx.github:
        ctx.github.git_client = worktree_git
    ctx.data["project_root"] = worktree_path

    ctx.textual.success_text(f"✓ Workflow isolated in {worktree_path}")
    ctx.textual.end_step("success")
    return Success(
        "Worktree context activated",
        metadata={
            "project_root": worktree_path,
            "worktree_context_active": True,
        },
    )


def cleanup_worktree_context(ctx: WorkflowContext) -> WorkflowResult:
    """
    Restore the main workflow context and remove the active worktree.

    Inputs (from ctx.data):
        worktree_path (str): Worktree directory to remove.
        worktree_context_active (bool): Whether the context was activated.

    Outputs (saved to ctx.data):
        worktree_context_active (bool): Always False after successful cleanup.
        worktree_removed (bool): Whether the worktree was removed.

    Returns:
        Success: If the original context is restored and the worktree is removed.
        Error: If no original context exists or worktree removal fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Cleanup Worktree Context")
    original_git = getattr(ctx, "_original_worktree_git", None)
    worktree_path = ctx.get("worktree_path")
    if not original_git or not worktree_path:
        ctx.textual.end_step("error")
        return Error("No active worktree context is available")

    ctx.git = original_git
    if ctx.github:
        ctx.github.git_client = original_git

    if getattr(ctx, "_had_original_project_root", False):
        ctx.data["project_root"] = getattr(ctx, "_original_project_root", None)
    else:
        ctx.data.pop("project_root", None)

    remove_result = original_git.remove_worktree(path=worktree_path, force=False)
    match remove_result:
        case ClientSuccess():
            pass
        case ClientError(error_message=err):
            ctx.textual.end_step("error")
            return Error(f"Failed to remove worktree: {err}")

    ctx.textual.success_text("✓ Worktree removed and original context restored")
    ctx.textual.end_step("success")
    return Success(
        "Worktree context cleaned up",
        metadata={"worktree_context_active": False, "worktree_removed": True},
    )


__all__ = ["activate_worktree_context", "cleanup_worktree_context"]
