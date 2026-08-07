"""
Merge Operations

Pure business logic for merging a branch into the current one.
These functions are UI-agnostic and easily testable.
"""

from typing import List, Optional, Tuple

from ..models.view.merge import MergeStatus, UIMergeResult


def resolve_merge_source(
    explicit_branch: Optional[str],
    main_branch: str,
    current_branch: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Decide which branch should be merged into the current one.

    Falls back to the configured main branch when no branch is given.

    Args:
        explicit_branch: Branch requested via workflow params/hook (may be empty)
        main_branch: Configured base branch of the project
        current_branch: Branch currently checked out

    Returns:
        Tuple of (source_branch, error_reason). Exactly one is not None.
    """
    source = (explicit_branch or "").strip() or (main_branch or "").strip()

    if not source:
        return None, "No source branch specified and no base branch is configured"

    if source == current_branch.strip():
        return None, f"Cannot merge '{source}' into itself"

    return source, None


def build_merge_ref(source_branch: str, remote: str) -> str:
    """
    Build the ref to merge from.

    The workflow merges the remote-tracking ref so HEAD never has to move.

    Args:
        source_branch: Branch to merge
        remote: Remote name

    Returns:
        Remote-tracking ref, or the plain branch name when no remote is given
    """
    remote = (remote or "").strip()
    if not remote:
        return source_branch
    return f"{remote}/{source_branch}"


def classify_merge_result(
    head_before: str,
    head_after: str,
    has_second_parent: bool,
    conflicted_files: List[str],
    merge_in_progress: bool,
) -> MergeStatus:
    """
    Classify the outcome of a merge from the repository state.

    Nothing here parses git's output: those messages are localized and change
    between versions, so the state of HEAD and MERGE_HEAD is the only reliable
    signal.

    Args:
        head_before: HEAD SHA before the merge ran
        head_after: HEAD SHA after the merge ran
        has_second_parent: Whether the new HEAD is a merge commit
        conflicted_files: Paths reported as unmerged
        merge_in_progress: Whether MERGE_HEAD exists

    Returns:
        The matching MergeStatus
    """
    if conflicted_files or merge_in_progress:
        return MergeStatus.CONFLICTED

    if head_after == head_before:
        return MergeStatus.UP_TO_DATE

    if has_second_parent:
        return MergeStatus.MERGED

    return MergeStatus.FAST_FORWARD


def build_conflict_resolution_prompt(
    conflicted_files: List[str],
    source_ref: str,
    target_branch: str,
) -> str:
    """
    Build the prompt handed to the interactive AI CLI to resolve conflicts.

    Args:
        conflicted_files: Paths with unresolved conflicts
        source_ref: Ref being merged in
        target_branch: Branch receiving the merge

    Returns:
        Prompt text
    """
    file_list = "\n".join(f"- {path}" for path in conflicted_files)

    return (
        f"I am merging `{source_ref}` into `{target_branch}` and git stopped "
        f"with conflicts.\n\n"
        f"Files with unresolved conflicts:\n{file_list}\n\n"
        f"Please resolve every conflict in these files:\n"
        f"1. Read each file and understand both sides of the conflict.\n"
        f"2. Produce a resolution that keeps the intent of both branches.\n"
        f"3. Remove all conflict markers (<<<<<<<, =======, >>>>>>>).\n"
        f"4. Do NOT run `git add`, `git commit` or `git merge --continue` — "
        f"the merge will be completed automatically once you exit.\n\n"
        f"When every file is resolved, exit."
    )


def format_merge_summary(result: UIMergeResult) -> List[str]:
    """
    Build the human-readable lines describing a merge result.

    Args:
        result: The merge outcome

    Returns:
        Lines ready to render in the TUI
    """
    header = f"{result.source_ref} → {result.target_branch}"

    match result.status:
        case MergeStatus.UP_TO_DATE:
            return [header, "Already up to date - nothing to merge"]
        case MergeStatus.FAST_FORWARD:
            return [header, "Fast-forwarded, no merge commit needed"]
        case MergeStatus.MERGED:
            return [header, "Merged cleanly"]
        case MergeStatus.CONFLICTED:
            count = len(result.conflicted_files)
            noun = "file" if count == 1 else "files"
            return [header, f"Stopped with conflicts in {count} {noun}"]

    return [header]


__all__ = [
    "resolve_merge_source",
    "build_merge_ref",
    "classify_merge_result",
    "build_conflict_resolution_prompt",
    "format_merge_summary",
]
