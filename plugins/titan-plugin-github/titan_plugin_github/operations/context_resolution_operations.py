"""Operations for resolving bounded review context from a focused review plan."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from titan_cli.core.logging import get_logger

from ..managers.diff_context_manager import DiffContextManager, get_or_create_diff_manager
from ..managers.prompt_budget_manager import get_prompt_budget_manager
from ..models.review_enums import ContextRequestType, FileReadMode, PRSizeClass
from ..models.review_models import (
    ChangeManifest,
    CommentContextEntry,
    ContextRequest,
    ExcludedFileEntry,
    FileContextEntry,
    FileReviewPlan,
    FocusContextBatch,
    ReviewChecklistItem,
    ReviewContextPackage,
    ReviewPlan,
    ReviewStrategy,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class FileReadAccess:
    """
    Whether files read from a directory can be trusted to be the PR's head revision.

    Attributes:
        allowed: True when reading files from ``root`` yields the code the diff
                 describes. False means only diff hunks may be used.
        source: Where the trusted content comes from — "worktree", "checkout",
                or "none" when reads are not allowed.
        reason: Short explanation, shown in the UI and logged.
    """
    allowed: bool
    source: str
    reason: str


def resolve_file_read_access(
    worktree_path: Optional[str],
    head_sha: Optional[str] = None,
    checkout_sha: Optional[str] = None,
    checkout_dirty: Optional[bool] = None,
) -> FileReadAccess:
    """
    Decide whether file content on disk may be used as this PR's code.

    A dedicated worktree is checked out at the PR head, so it is always trusted. Without
    one, the only directory available is the user's own checkout, which sits on whatever
    branch they happen to be on. Reading a file from there and pairing it with the PR's
    diff silently mixes two revisions: line numbers stop matching the hunks, and the AI
    reviews code that is not in the PR at all. So the checkout is trusted only when it is
    provably at the head commit with nothing modified on top.

    Args:
        worktree_path: Path to a worktree created for this PR, if any
        head_sha: The PR head commit SHA the diff was computed against
        checkout_sha: HEAD of the user's checkout
        checkout_dirty: Whether the user's checkout has uncommitted changes

    Returns:
        FileReadAccess with the verdict and a reason for display
    """
    if worktree_path:
        return FileReadAccess(True, "worktree", f"worktree at PR head: {worktree_path}")

    if not head_sha or not checkout_sha:
        return FileReadAccess(
            False, "none", "no worktree and the checkout revision could not be verified"
        )

    if checkout_sha != head_sha:
        return FileReadAccess(
            False,
            "none",
            f"checkout is at {checkout_sha[:8]}, PR head is {head_sha[:8]}",
        )

    if checkout_dirty or checkout_dirty is None:
        return FileReadAccess(
            False,
            "none",
            "checkout is at the PR head but has uncommitted changes"
            if checkout_dirty
            else "checkout is at the PR head but its dirty state could not be verified",
        )

    return FileReadAccess(True, "checkout", f"checkout verified at PR head {head_sha[:8]}")


def extract_hunks_only(
    diff: str,
    path: str,
    diff_manager: Optional[DiffContextManager] = None,
) -> list[str]:
    manager = diff_manager or DiffContextManager.from_diff(diff)
    return manager.get_hunk_texts(path)


def extract_expanded_hunks(
    diff: str,
    path: str,
    cwd: Optional[str] = None,
    diff_manager: Optional[DiffContextManager] = None,
) -> list[str]:
    file_content = read_file_content(path, cwd)
    if not file_content:
        return extract_hunks_only(diff, path, diff_manager=diff_manager)

    manager = diff_manager or DiffContextManager.from_diff(diff)
    return manager.build_expanded_hunks(path, file_content, extra_lines=10)


def read_file_content(path: str, cwd: Optional[str] = None) -> Optional[str]:
    try:
        base = Path(cwd) if cwd else Path.cwd()
        file_path = base / path
        if file_path.exists() and file_path.is_file():
            return file_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as e:
        logger.debug("Could not read %s: %s", path, e)
    return None


def _find_related_tests(path: str, cwd: Optional[str] = None) -> Optional[str]:
    p = Path(path)
    stem = p.stem
    candidates = [
        p.parent / "tests" / f"test_{stem}{p.suffix}",
        p.parent / f"test_{stem}{p.suffix}",
        p.parent / f"{stem}_test{p.suffix}",
        Path("tests") / f"test_{stem}{p.suffix}",
        Path("tests") / p.parent / f"test_{stem}{p.suffix}",
    ]

    for candidate in candidates:
        content = read_file_content(str(candidate), cwd)
        if content:
            return content
    return None


def _find_related_context(path: str, cwd: Optional[str] = None) -> Optional[str]:
    p = Path(path)
    candidates = [
        p.parent / "__init__.py",
        p.parent / "protocols.py",
        p.parent / "interfaces.py",
        p.parent / f"base_{p.stem}{p.suffix}",
        p.parent / f"{p.stem}_base{p.suffix}",
    ]

    for candidate in candidates:
        if candidate == p:
            continue
        content = read_file_content(str(candidate), cwd)
        if content:
            return content[:3000]
    return None


def resolve_context_requests(
    requests: list[ContextRequest],
    cwd: Optional[str] = None,
    allow_file_reads: bool = True,
) -> dict[str, str]:
    """
    Resolve extra context requests by reading sibling files.

    Returns nothing when ``allow_file_reads`` is False: these files are read whole from
    disk, so an unverified revision would put unrelated code in the prompt.
    """
    if not allow_file_reads:
        return {}

    result: dict[str, str] = {}
    for req in requests:
        key = f"{req.type}:{req.for_path}"
        if req.type == ContextRequestType.RELATED_TESTS:
            content = _find_related_tests(req.for_path, cwd)
        else:
            content = _find_related_context(req.for_path, cwd)
        if content:
            result[key] = content
    return result


def build_review_context_package(
    plan: ReviewPlan,
    diff: str,
    manifest: ChangeManifest,
    checklist: list[ReviewChecklistItem],
    comment_context: list[CommentContextEntry],
    strategy: ReviewStrategy,
    cwd: Optional[str] = None,
    diff_manager: Optional[DiffContextManager] = None,
    allow_file_reads: bool = True,
) -> ReviewContextPackage:
    """
    Build the batched review context package for the AI prompt.

    When ``allow_file_reads`` is False, no file is read from ``cwd``: every file falls
    back to its diff hunks. Callers set this when the content on disk cannot be proven to
    be the PR's head revision — see ``resolve_file_read_access``.
    """
    manager = diff_manager or get_or_create_diff_manager(diff)
    applicable_ids = set(plan.review_axes)
    checklist_applicable = [item for item in checklist if item.id in applicable_ids] or checklist[:2]

    if len(plan.extra_context_requests) > 1:
        logger.info(
            "extra_context_requests_trimmed: planned=%d resolved=%d dropped=%d",
            len(plan.extra_context_requests),
            1,
            len(plan.extra_context_requests) - 1,
        )

    related_files = resolve_context_requests(
        plan.extra_context_requests[:1], cwd, allow_file_reads=allow_file_reads
    )
    comment_context = comment_context[: strategy.max_comment_entries]
    content_budget = get_prompt_budget_manager().content_budget(strategy)

    batches: list[FocusContextBatch] = []
    current_files: dict[str, FileContextEntry] = {}
    current_chars = _estimate_related_chars(related_files) + _estimate_comment_chars(comment_context)
    batch_index = 1
    carry_excluded: list[ExcludedFileEntry] = []

    for file_plan in plan.focus_files:
        entry = _resolve_file_context(
            file_plan, diff, strategy, cwd, manager, allow_file_reads=allow_file_reads
        )
        entry_chars = entry.approximate_chars or get_prompt_budget_manager().estimate_entry_chars(entry)
        # A worktree_reference file forces the CLI to read it from disk itself, which is
        # expensive regardless of how cheap its prompt text looks — cap how many of them
        # can stack up in a single batch, on top of the regular char-budget check.
        exceeds_worktree_reference_limit = entry.worktree_reference and _batch_has_worktree_reference(current_files)

        exceeds_char_budget = current_chars + entry_chars > content_budget
        if current_files and strategy.batching_enabled and (exceeds_char_budget or exceeds_worktree_reference_limit):
            batches.append(
                FocusContextBatch(
                    batch_id=f"batch_{batch_index}",
                    files_context=current_files,
                    comment_context=comment_context,
                    checklist_applicable=checklist_applicable,
                    related_files=related_files,
                    excluded_files=carry_excluded,
                    pr_manifest=manifest.pr,
                    approximate_chars=current_chars,
                    prompt_budget_target_chars=strategy.max_prompt_chars,
                )
            )
            batch_index += 1
            current_files = {}
            current_chars = _estimate_related_chars(related_files) + _estimate_comment_chars(comment_context)
            carry_excluded = []

        if not strategy.batching_enabled and current_files and current_chars + entry_chars > content_budget:
            carry_excluded.append(
                ExcludedFileEntry(
                    path=file_plan.path,
                    reason="budget_trimmed",
                    detail="did not fit in direct context budget",
                )
            )
            continue

        current_files[file_plan.path] = entry
        current_chars += entry_chars

    if current_files:
        batches.append(
            FocusContextBatch(
                batch_id=f"batch_{batch_index}",
                files_context=current_files,
                comment_context=comment_context,
                checklist_applicable=checklist_applicable,
                related_files=related_files,
                excluded_files=carry_excluded,
                pr_manifest=manifest.pr,
                approximate_chars=current_chars,
                prompt_budget_target_chars=strategy.max_prompt_chars,
            )
        )

    return ReviewContextPackage(batches=batches)


def _resolve_file_context(
    file_plan: FileReviewPlan,
    diff: str,
    strategy: ReviewStrategy,
    cwd: Optional[str] = None,
    diff_manager: Optional[DiffContextManager] = None,
    allow_file_reads: bool = True,
) -> FileContextEntry:
    manager = diff_manager or DiffContextManager.from_diff(diff)
    desired_mode = file_plan.read_mode
    # The model anchors comments inside the hunks it can see; a header it never saw
    # is a region it cannot anchor to, so those comments end up on unpublishable
    # lines and degrade to the general body. 30 covers any realistic file (a header
    # is ~40 chars, so worst case ~1.2k chars) while still bounding pathological diffs.
    hunk_headers = [hunk.header for hunk in manager.get_hunks(file_plan.path)[:30]]
    file_limits = _file_limits(strategy, file_plan.path)
    resolved_entry: FileContextEntry | None = None

    if not allow_file_reads and desired_mode in (FileReadMode.FULL_FILE, FileReadMode.EXPANDED_HUNKS):
        # Content on disk is not provably this PR's revision; hunks come from the diff
        # itself and are always correct.
        logger.debug(
            "file_read_not_allowed: path=%s requested_mode=%s → hunks_only",
            file_plan.path,
            desired_mode,
        )
        desired_mode = FileReadMode.HUNKS_ONLY

    if desired_mode == FileReadMode.FULL_FILE:
        content = read_file_content(file_plan.path, cwd)
        if content and len(content) <= file_limits["max_file_chars"] and len(content.splitlines()) <= file_limits["max_file_lines"]:
            resolved_entry = FileContextEntry(
                path=file_plan.path,
                read_mode=FileReadMode.FULL_FILE,
                full_content=content,
                changed_hunk_headers=hunk_headers,
                approximate_chars=len(content),
            )
            return _log_file_context(resolved_entry, file_plan.path)
        desired_mode = FileReadMode.EXPANDED_HUNKS

    if desired_mode == FileReadMode.EXPANDED_HUNKS:
        file_content = read_file_content(file_plan.path, cwd)
        expanded = (
            manager.build_expanded_hunks(
                file_plan.path,
                file_content,
                extra_lines=file_limits["extra_lines"],
            )
            if file_content
            else manager.get_hunk_texts(file_plan.path)
        )
        expanded_chars = sum(len(hunk) for hunk in expanded)
        if expanded and expanded_chars <= file_limits["max_file_chars"]:
            resolved_entry = FileContextEntry(
                path=file_plan.path,
                read_mode=FileReadMode.EXPANDED_HUNKS,
                expanded_hunks=expanded,
                changed_hunk_headers=hunk_headers,
                approximate_chars=expanded_chars,
            )
            return _log_file_context(resolved_entry, file_plan.path)
        desired_mode = FileReadMode.HUNKS_ONLY

    if desired_mode == FileReadMode.HUNKS_ONLY:
        hunks = manager.get_hunk_texts(file_plan.path)
        hunks_chars = sum(len(hunk) for hunk in hunks)
        if hunks and (hunks_chars <= file_limits["max_file_chars"] or not allow_file_reads):
            # Over-budget hunks are still preferable to the worktree_reference fallback
            # when reads are not allowed: that mode has the CLI open the file itself, which
            # is the same wrong-revision read, just delegated. The batching loop keeps the
            # prompt bounded via approximate_chars.
            resolved_entry = FileContextEntry(
                path=file_plan.path,
                read_mode=FileReadMode.HUNKS_ONLY,
                hunks=hunks,
                changed_hunk_headers=hunk_headers,
                approximate_chars=hunks_chars,
            )
            return _log_file_context(resolved_entry, file_plan.path)

    if not allow_file_reads:
        # No hunks and no trustworthy file to read: headers only, so the AI still knows
        # the file changed but is never handed content from another revision.
        resolved_entry = FileContextEntry(
            path=file_plan.path,
            read_mode=FileReadMode.HUNKS_ONLY,
            changed_hunk_headers=hunk_headers,
            review_hint=(
                "File content unavailable: no PR worktree and the local checkout is not "
                "at this PR's head commit. Review from the diff only."
            ),
        )
        return _log_file_context(resolved_entry, file_plan.path)

    resolved_entry = FileContextEntry(
        path=file_plan.path,
        read_mode=FileReadMode.WORKTREE_REFERENCE,
        worktree_reference=True,
        review_hint=_build_worktree_hint(file_plan),
        changed_hunk_headers=hunk_headers,
        approximate_chars=get_prompt_budget_manager().WORKTREE_REFERENCE_ESTIMATED_CHARS,
    )
    return _log_file_context(resolved_entry, file_plan.path)


def _file_limits(strategy: ReviewStrategy, path: str) -> dict[str, int]:
    is_large = strategy.size_class in {PRSizeClass.LARGE, PRSizeClass.HUGE}
    is_central = _looks_like_central_file(path)
    is_test = _is_test_file(path)
    return {
        "max_file_chars": 9000 if is_test and is_large else 12000 if is_central and is_large else 7000 if is_large else 14000,
        "max_file_lines": 140 if is_test and is_large else 220 if is_central and is_large else 120 if is_large else 260,
        "extra_lines": 4 if is_test and is_large else 8 if is_central else 4 if is_large else 8,
    }


def _looks_like_central_file(path: str) -> bool:
    path_lower = path.lower()
    return any(
        token in path_lower
        for token in (
            "viewmodel",
            "manager",
            "service",
            "utils",
            "mapper",
            "serializer",
            "adapter",
            "converter",
            "parser",
            "model",
        )
    )


def _is_test_file(path: str) -> bool:
    path_lower = path.lower()
    return any(token in path_lower for token in ("/test/", "/tests/", "test.kt", "test.py", "spec."))


def _build_worktree_hint(file_plan: FileReviewPlan) -> str:
    reasons = "; ".join(file_plan.reasons[:2]) if file_plan.reasons else "central changed file"
    return (
        "Read this file from the worktree. Prioritize the changed regions first and validate: "
        f"{reasons}. Check especially for semantic mismatches, missing guarantees, state inconsistencies, "
        "and behavior changes that remain executable but no longer mean the same thing. You may check a few "
        "directly related files (an imported type, a caller, a test) if genuinely needed to resolve a "
        "specific doubt, but do not perform a broad, open-ended exploration of the codebase."
    )


def _estimate_related_chars(related_files: dict[str, str]) -> int:
    return sum(len(label) + len(content[:2000]) for label, content in related_files.items())


def _estimate_comment_chars(comment_context: list[CommentContextEntry]) -> int:
    return sum(len(entry.title) + len(entry.summary) for entry in comment_context)


def _batch_has_worktree_reference(files_context: dict[str, FileContextEntry]) -> bool:
    return any(entry.worktree_reference for entry in files_context.values())


def _log_file_context(entry: FileContextEntry, path: str) -> FileContextEntry:
    logger.debug(
        "file_context_resolved",
        path=path,
        read_mode=entry.read_mode,
        chars=entry.approximate_chars,
        changed_hunks=len(entry.changed_hunk_headers),
        worktree_reference=entry.worktree_reference,
        trimmed=entry.read_mode == FileReadMode.WORKTREE_REFERENCE,
    )
    return entry
