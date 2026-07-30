"""
Worktree Operations

Pure business logic for git worktree operations.
These functions wrap git worktree commands without UI dependencies.
"""

import os
import shutil
from typing import Tuple
from titan_cli.core.result import ClientSuccess, ClientError


def setup_worktree(
    git_client,
    pr_number: int,
    branch: str = "",
    base_path: str = ".titan/worktrees",
    remote: str = "origin"
) -> Tuple[str, bool]:
    """
    Create a git worktree for PR review.

    Args:
        git_client: Git client instance
        pr_number: PR number (used in worktree name)
        branch: Branch to checkout in worktree
        base_path: Base directory for worktrees
        remote: Remote name (default: "origin")

    Returns:
        Tuple of (absolute_path, created_successfully)
    """
    try:
        worktree_name = f"titan-review-{pr_number}"
        worktree_path = f"{base_path}/{worktree_name}"
        original_cwd = os.getcwd()
        full_worktree_path = os.path.join(original_cwd, worktree_path)

        clear_stale_worktree(git_client, worktree_path, full_worktree_path)

        # Fetch the PR ref into a stable local ref. This works for both same-repo
        # and fork-based PRs where origin/<head_branch> does not exist locally.
        review_ref = f"refs/titan/review/pr-{pr_number}"
        pr_refspec = f"pull/{pr_number}/head:{review_ref}"
        fetch_result = git_client.fetch_refspec(remote, pr_refspec)
        match fetch_result:
            case ClientSuccess():
                pass
            case ClientError():
                return ("", False)

        result = git_client.create_worktree(
            path=worktree_path,
            branch=review_ref,
            create_branch=False,
            detached=True
        )

        match result:
            case ClientSuccess():
                return (full_worktree_path, True)
            case ClientError():
                return ("", False)

    except Exception:
        return ("", False)


def clear_stale_worktree(
    git_client,
    worktree_path: str,
    full_worktree_path: str = "",
) -> None:
    """
    Make ``worktree_path`` reusable, whatever state a previous run left it in.

    Three residues can block ``git worktree add`` on the same path, and they need
    different remedies, so all three are attempted in order:

    1. A live registered worktree — ``git worktree remove --force`` handles it.
    2. Stale metadata under ``.git/worktrees`` after the directory was deleted by
       hand or a removal was interrupted — ``remove`` rejects it ("not a working
       tree") and only ``git worktree prune`` clears it.
    3. A leftover directory with no registration — neither git command touches it
       and ``add`` refuses a non-empty path, so it is deleted directly.

    Best-effort by design: every step is optional cleanup, so failures are ignored
    and the caller proceeds to creation, which reports the real error if any residue
    survived.

    Args:
        git_client: Git client instance
        worktree_path: Worktree path as git knows it (usually repo-relative)
        full_worktree_path: Absolute path on disk; when empty, the directory
                            removal step is skipped
    """
    try:
        git_client.remove_worktree(worktree_path, force=True)
    except Exception:
        pass

    try:
        git_client.prune_worktrees()
    except Exception:
        pass

    if full_worktree_path and os.path.isdir(full_worktree_path):
        try:
            shutil.rmtree(full_worktree_path)
        except OSError:
            pass


def cleanup_worktree(
    git_client,
    worktree_path: str
) -> bool:
    """
    Remove a git worktree.

    Args:
        git_client: Git client instance
        worktree_path: Path to worktree (relative or absolute)

    Returns:
        True if successful, False otherwise
    """
    result = git_client.remove_worktree(worktree_path, force=True)
    match result:
        case ClientSuccess():
            return True
        case ClientError():
            return False


def commit_in_worktree(
    git_client,
    worktree_path: str,
    message: str,
    add_all: bool = True,
    no_verify: bool = False
) -> str:
    """
    Create a commit in a worktree.

    Args:
        git_client: Git client instance
        worktree_path: Path to worktree
        message: Commit message
        add_all: Stage all changes before committing
        no_verify: Skip pre-commit hooks

    Returns:
        Commit hash (40-char SHA)

    Raises:
        Exception: If commit fails
    """
    result = git_client.commit_in_worktree(worktree_path, message, add_all, no_verify)
    match result:
        case ClientSuccess(data=commit_hash):
            return commit_hash
        case ClientError(error_message=err):
            raise Exception(f"Failed to commit in worktree: {err}")
