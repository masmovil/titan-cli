"""
Steps for AI-powered PR code review.

This module contains steps for reviewing pull requests authored by others using
AI analysis combined with project-specific skill guidelines.
"""
import re
import threading
import time
from difflib import SequenceMatcher
from typing import List, Optional

from titan_cli.core.logging import get_logger
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Exit, Skip
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.external_cli.adapters import HEADLESS_ADAPTER_REGISTRY, get_headless_adapter
from titan_cli.ui.tui.widgets import ChoiceOption, OptionItem, PromptChoice

from ..managers.diff_context_manager import get_or_create_diff_manager
from ..managers.prompt_budget_manager import get_prompt_budget_manager
from ..models.review_enums import ReviewActionType, ReviewStrategyType, ThreadDecisionType
from ..models.review_models import (
    PRClassification,
    ReferencedCommitContext,
    ReviewActionProposal,
)
from ..models.review_profile_models import ReviewProfile
from ..models.view import UICommentThread, UIPullRequest
from ..operations.ai_response_parsing_operations import (
    REFORMAT_RETRY_TIMEOUT_SECONDS,
    build_json_reformat_prompt,
    extract_json_payload,
)
from ..operations.code_review_operations import (
    select_files_for_review,
    compute_diff_stat,
)
from ..operations.review_action_operations import (
    build_new_comment_actions as build_new_comment_actions_operation,
    build_review_action_payload,
    classify_github_review_rejection,
    extract_diff_hunk_for_action,
    extract_file_excerpt_for_action,
    resolve_action_anchors,
)
from ..operations.thread_resolution_operations import (
    batch_thread_review_contexts,
    build_thread_review_candidates as build_thread_review_candidates_operation,
    build_thread_review_contexts as build_thread_review_contexts_operation,
    build_thread_resolution_prompt,
    build_thread_actions as build_thread_actions_operation,
)
from ..operations.pr_selection_operations import (
    build_pr_selection_description,
    build_pr_selection_title,
)

from ..operations.manifest_operations import (
    build_change_manifest as build_change_manifest_operation,
)

from ..operations.manifest_operations import (
        build_comment_review_context,
        build_existing_comments_index as build_existing_comments_index_operation,
    )

logger = get_logger(__name__)

_PROMPT_PREVIEW_CHARS = 2000
_RESPONSE_PREVIEW_CHARS = 1500
_COMMIT_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
_CENTRAL_PATH_HINTS = ("/utils/", "/configuration/", "/interceptors/", "/base/", "Utils.kt", "Configuration.kt")
_MAX_REFERENCED_COMMITS_PER_THREAD = 3
_MAX_REFERENCED_COMMIT_FILES = 3
_MAX_REFERENCED_COMMIT_PATCH_CHARS = 4000


def _preview_edges(text: str, limit: int) -> tuple[str, str]:
    """Return start/end previews for large text blobs."""
    if len(text) <= limit:
        return text, text
    return text[:limit], text[-limit:]


def _log_ai_prompt(step_name: str, cli_name: str, prompt: str, **extra) -> None:
    """Log prompt metadata plus previews for review debugging."""
    first, last = _preview_edges(prompt, _PROMPT_PREVIEW_CHARS)
    logger.debug(
        "ai_prompt_built",
        step=step_name,
        cli=cli_name,
        prompt_chars=len(prompt),
        prompt_first_chars=first,
        prompt_last_chars=last,
        **extra,
    )
    logger.debug(
        "ai_prompt_full",
        step=step_name,
        cli=cli_name,
        prompt=prompt,
        **extra,
    )


def _log_ai_response(step_name: str, cli_name: str, stdout: str, stderr: str, exit_code: int, **extra) -> None:
    """Log response metadata plus previews for review debugging."""
    stdout_first, stdout_last = _preview_edges(stdout, _RESPONSE_PREVIEW_CHARS)
    stderr_first, stderr_last = _preview_edges(stderr, _RESPONSE_PREVIEW_CHARS)
    logger.debug(
        "ai_response_received",
        step=step_name,
        cli=cli_name,
        exit_code=exit_code,
        stdout_chars=len(stdout),
        stderr_chars=len(stderr),
        stdout_first_chars=stdout_first,
        stdout_last_chars=stdout_last,
        stderr_first_chars=stderr_first,
        stderr_last_chars=stderr_last,
        **extra,
    )
    logger.debug(
        "ai_response_full",
        step=step_name,
        cli=cli_name,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        **extra,
    )


def _extract_referenced_commit_shas(reply_bodies: list[str]) -> list[str]:
    """Collect distinct SHA-like tokens mentioned in reply bodies."""
    seen: set[str] = set()
    shas: list[str] = []

    for body in reply_bodies:
        for match in _COMMIT_SHA_RE.findall(body or ""):
            sha = match.lower()
            if sha in seen:
                continue
            seen.add(sha)
            shas.append(sha)

    return shas


def _load_referenced_commit_contexts(
    ctx: WorkflowContext,
    threads: list[UICommentThread],
    pr: Optional[UIPullRequest] = None,
) -> dict[str, list[ReferencedCommitContext]]:
    """Fetch compact remote commit context for SHA references in the PR author's replies.

    Only replies authored by the PR author are scanned for SHAs, since the AI
    is deciding whether the author's response resolved the review comment; SHAs
    mentioned by other reviewers or bots aren't claims made by the author.

    For cross-repo (fork) PRs, referenced SHAs may only exist on the fork's
    head repository, so lookups are resolved against it instead of the base repo.
    """
    if not ctx.github:
        return {}

    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    if pr and pr.is_cross_repository and pr.head_repository_owner and pr.head_repository_name:
        repo_owner = pr.head_repository_owner
        repo_name = pr.head_repository_name

    pr_author = pr.author_name if pr else None

    commit_cache: dict[str, ReferencedCommitContext | None] = {}
    contexts_by_thread: dict[str, list[ReferencedCommitContext]] = {}

    for thread in threads:
        reply_bodies = [
            reply.body for reply in thread.replies
            if pr_author is None or reply.author_login == pr_author
        ]
        referenced_shas = _extract_referenced_commit_shas(reply_bodies)
        if not referenced_shas:
            continue

        referenced_contexts: list[ReferencedCommitContext] = []
        for sha in referenced_shas[:_MAX_REFERENCED_COMMITS_PER_THREAD]:
            if sha not in commit_cache:
                result = ctx.github.get_commit_review_context(
                    sha,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    max_files=_MAX_REFERENCED_COMMIT_FILES,
                    max_patch_chars=_MAX_REFERENCED_COMMIT_PATCH_CHARS,
                )
                match result:
                    case ClientSuccess(data=commit_context):
                        commit_cache[sha] = commit_context
                    case ClientError(error_message=err):
                        logger.debug(
                            "referenced_commit_context_unavailable",
                            thread_id=thread.thread_id,
                            sha=sha,
                            error=err,
                        )
                        commit_cache[sha] = None

            commit_context = commit_cache.get(sha)
            if commit_context is not None:
                referenced_contexts.append(commit_context)

        if referenced_contexts:
            contexts_by_thread[thread.thread_id] = referenced_contexts

    return contexts_by_thread


def _show_review_plan_summary(ctx: WorkflowContext, plan) -> None:
    """Render a concise review plan summary in the UI."""
    if getattr(plan, "focus_files", None):
        ctx.textual.dim_text("focus files:")
        ctx.textual.text(" ")
        for file_plan in plan.focus_files:
            ctx.textual.dim_text(
                f"{file_plan.path} · {file_plan.priority.value} · {file_plan.read_mode.value}"
            )

    ctx.textual.text(" ")
    if getattr(plan, "review_axes", None):
        ctx.textual.dim_text("review axes:")
        ctx.textual.text(" ")
        for axis in plan.review_axes:
            ctx.textual.dim_text(str(axis))

    if getattr(plan, "extra_context_requests", None):
        ctx.textual.dim_text("extra context:")
        ctx.textual.text(" ")
        for request in plan.extra_context_requests:
            ctx.textual.dim_text(f"{request.type} -> {request.for_path}")


def _show_review_plan_validation_summary(ctx: WorkflowContext, plan) -> None:
    """Render a compact validation summary without repeating the full plan."""
    focus_count = len(getattr(plan, "focus_files", []) or [])
    axes_count = len(getattr(plan, "review_axes", []) or [])
    extra_count = len(getattr(plan, "extra_context_requests", []) or [])
    ctx.textual.dim_text(
        f"Validated plan: {focus_count} focus file(s) · {axes_count} axes · {extra_count} extra context request(s)"
    )


def _filter_invalid_inline_comments(ctx: WorkflowContext, pr_number: int, payload: dict) -> tuple[dict, list[dict]]:
    """Probe inline comments individually, keep only those GitHub accepts."""
    if not ctx.github or not payload.get("comments"):
        return payload, []

    valid_comments: list[dict] = []
    rejected_comments: list[dict] = []

    for comment in payload.get("comments", []):
        probe_payload = {
            "commit_id": payload["commit_id"],
            "comments": [comment],
        }
        probe_result = ctx.github.create_draft_review(pr_number, probe_payload)
        match probe_result:
            case ClientSuccess(data=probe_review_id):
                valid_comments.append(comment)
                delete_result = ctx.github.delete_review(pr_number, probe_review_id)
                match delete_result:
                    case ClientError(error_message=err):
                        logger.warning(
                            "probe_review_delete_failed",
                            pr_number=pr_number,
                            review_id=probe_review_id,
                            error=err,
                        )
            case ClientError(error_message=err):
                rejection_kind = classify_github_review_rejection(err)
                rejected = {**comment, "error": err}
                rejected_comments.append(rejected)
                logger.warning(
                    "inline_comment_rejected_by_github",
                    pr_number=pr_number,
                    path=comment.get("path"),
                    line=comment.get("line"),
                    github_rejection_kind=rejection_kind,
                    error=err,
                )

    filtered_payload = {
        "commit_id": payload["commit_id"],
        "comments": valid_comments,
    }
    if payload.get("body"):
        filtered_payload["body"] = payload["body"]
    return filtered_payload, rejected_comments


def _collapse_derived_findings(findings: list) -> tuple[list, int]:
    """Drop call-site findings that are derived from a stronger central finding."""
    central_findings = [finding for finding in findings if _is_central_path(finding.path)]
    if not central_findings:
        return findings, 0

    kept: list = []
    removed = 0
    for finding in findings:
        if _is_central_path(finding.path):
            kept.append(finding)
            continue

        if any(_is_derived_from_central(finding, central) for central in central_findings):
            removed += 1
            logger.debug(
                "finding_collapsed_to_root_cause",
                path=finding.path,
                title=finding.title,
            )
            continue

        kept.append(finding)
    return kept, removed


def _is_central_path(path: str) -> bool:
    return any(hint in path for hint in _CENTRAL_PATH_HINTS)


def _is_derived_from_central(finding, central) -> bool:
    if finding.path == central.path:
        return False
    if finding.category != central.category:
        return False

    finding_text = " ".join(filter(None, [finding.title, finding.why, finding.evidence, finding.suggested_comment])).lower()
    central_text = " ".join(filter(None, [central.title, central.why, central.evidence, central.suggested_comment])).lower()

    central_stem = central.path.split("/")[-1].replace(".kt", "").replace(".py", "").lower()
    shared_api = any(
        token in finding_text and token in central_text
        for token in ("launchcustomtab", "openurlordialog", "checkinternalorexternaluri", "ishostallowed", "onopenfailed", "onopensuccess")
    )
    # Only the FINDING mentioning the central file counts as a derivation signal —
    # the central finding mentions its own file stem practically by definition, so
    # checking central_text here would make this clause always true and reduce the
    # whole collapse condition to a 0.32 title similarity.
    mentions_central = central_stem in finding_text
    title_similarity = SequenceMatcher(None, finding.title.lower(), central.title.lower()).ratio()

    return (shared_api or mentions_central) and title_similarity >= 0.32


# ============================================================================
# UI HELPERS
# ============================================================================


def _show_review_action_and_get_decision(
    ctx: WorkflowContext,
    action: ReviewActionProposal,
    diff_hunk: str,
    idx: int,
    total: int,
    review_threads: Optional[List[UICommentThread]] = None,
    file_excerpt: Optional[str] = None,
) -> str:
    """
    Display a ReviewActionProposal and return the user's chosen decision.

    For resolve_thread actions, shows thread context and resolve confirmation.
    For reply_to_thread actions, shows the original thread context and proposed reply.
    For new_comment actions, shows just the proposed comment.

    ``file_excerpt`` carries real file content for findings the diff cannot anchor, so
    they are shown with their code rather than as an unsupported claim.

    Returns:
        "approve", "edit", "skip", or "exit"
    """
    ctx.textual.text("")

    # Handle resolve_thread actions differently
    if action.action_type == ReviewActionType.RESOLVE_THREAD:
        ctx.textual.bold_text(f"Thread {idx + 1} of {total}")
        ctx.textual.text("")

        # Show the original thread to be resolved
        if review_threads:
            from titan_plugin_github.widgets import CommentThread

            original_thread = next(
                (t for t in review_threads if t.thread_id == action.thread_id),
                None
            )
            if original_thread:
                ctx.textual.text("📌 Thread to resolve:")
                ctx.textual.mount(
                    CommentThread(
                        thread=original_thread,
                        options=[],  # No buttons in this display
                    )
                )
                ctx.textual.text("")

        ctx.textual.text("✓ Mark this thread as resolved")
        ctx.textual.text("")

        options = [
            ChoiceOption(value="approve", label="✓ Resolve", variant="success"),
            ChoiceOption(value="skip", label="— Skip", variant="default"),
        ]
        if idx < total - 1:
            options.append(ChoiceOption(value="exit", label="✗ Exit review", variant="error"))

        question = "What would you like to do with this thread?"
    else:
        # For reply_to_thread and new_comment actions
        ctx.textual.bold_text(f"Comment {idx + 1} of {total}")
        ctx.textual.text("")

        # For reply_to_thread actions, show the original thread context
        if action.action_type == ReviewActionType.REPLY_TO_THREAD and review_threads:
            from titan_plugin_github.widgets import CommentThread

            # Find the original thread
            original_thread = next(
                (t for t in review_threads if t.thread_id == action.thread_id),
                None
            )
            if original_thread:
                ctx.textual.text("📌 Original comment:")
                ctx.textual.mount(
                    CommentThread(
                        thread=original_thread,
                        options=[],  # No buttons in this display
                    )
                )
                ctx.textual.text("")
                ctx.textual.text("📝 Your reply:")

        # Show the action (proposed reply or new comment)
        from titan_plugin_github.widgets import CommentView
        ctx.textual.mount(
            CommentView.from_action(action, diff_hunk=diff_hunk, file_excerpt=file_excerpt)
        )
        ctx.textual.text("")

        options = [
            ChoiceOption(value="approve", label="✓ Approve", variant="success"),
            ChoiceOption(value="edit", label="✎ Edit", variant="default"),
            ChoiceOption(value="skip", label="— Skip", variant="default"),
        ]
        if idx < total - 1:
            options.append(ChoiceOption(value="exit", label="✗ Exit review", variant="error"))

        question = "What would you like to do with this comment?"

    result_container: dict = {}
    result_event = threading.Event()

    def on_choice(value):
        result_container["choice"] = value
        result_event.set()

    prompt = PromptChoice(
        question=question,
        options=options,
        on_select=on_choice,
    )
    ctx.textual.mount(prompt)
    result_event.wait()

    choice = result_container.get("choice", "skip")

    action_labels = {
        "approve": "✓ Resolved" if action.action_type == ReviewActionType.RESOLVE_THREAD else "✓ Approved",
        "edit": "✎ Edited",
        "skip": "— Skipped",
        "exit": "✗ Exit review",
    }
    action_variants = {
        "approve": "success",
        "edit": "default",
        "skip": "default",
        "exit": "warning",
    }

    def _replace_with_badge():
        from titan_cli.ui.tui.widgets.decision_badge import DecisionBadge
        try:
            prompt.remove()
        except Exception:
            pass
        try:
            target = ctx.textual._active_step_container or ctx.textual.output_widget
            target.mount(
                DecisionBadge(
                    action_labels.get(choice, choice),
                    variant=action_variants.get(choice, "default"),
                )
            )
        except Exception:
            pass

    ctx.textual.app.call_from_thread(_replace_with_badge)
    return choice


# ============================================================================
# STEP FUNCTIONS
# ============================================================================


def select_pr_for_code_review(ctx: WorkflowContext) -> WorkflowResult:
    """
    List all open PRs and ask user to select one.

    Assigned PRs (pending your review) appear first marked with ⭐.

    Outputs (saved to ctx.data):
        review_pr_number (int): Selected PR number
        review_pr_title (str): PR title
        review_pr_head (str): Head branch
        review_pr_base (str): Base branch

    Returns:
        Success, Exit (no PRs or cancelled), or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Select PR to Review")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    with ctx.textual.loading("Fetching open PRs..."):
        all_result = ctx.github.list_all_prs()
        assigned_result = ctx.github.list_pending_review_prs()

    match all_result:
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to fetch PRs: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to fetch PRs: {err}")
        case ClientSuccess(data=all_prs_list):
            pass

    if not all_prs_list:
        ctx.textual.dim_text("No open PRs found in this repository.")
        ctx.textual.end_step("skip")
        return Exit("No open PRs found")

    # Build set of assigned PR numbers (ignore errors — best effort)
    assigned_numbers: set = set()
    match assigned_result:
        case ClientSuccess(data=assigned_prs):
            assigned_numbers = {pr.number for pr in assigned_prs}
        case ClientError():
            pass

    # Sort: assigned first, then the rest (preserving original order within each group)
    sorted_prs = [pr for pr in all_prs_list if pr.number in assigned_numbers] + \
                 [pr for pr in all_prs_list if pr.number not in assigned_numbers]

    options = [
        OptionItem(
            value=pr.number,
            title=build_pr_selection_title(
                pr,
                highlight_assigned=pr.number in assigned_numbers,
                include_review_badge=True,
            ),
            description=build_pr_selection_description(
                pr,
                include_author=True,
                include_checks=True,
            ),
        )
        for pr in sorted_prs
    ]

    assigned_count = len(assigned_numbers)
    question = f"Select a PR to review ({len(all_prs_list)} total{f', {assigned_count} assigned to you ⭐' if assigned_count else ''}):"

    try:
        selected = ctx.textual.ask_option(question, options)
    except Exception as e:
        ctx.textual.error_text(str(e))
        ctx.textual.end_step("error")
        return Error(str(e))

    if not selected:
        ctx.textual.warning_text("No PR selected")
        ctx.textual.end_step("skip")
        return Exit("User cancelled PR selection")

    selected_pr = next((pr for pr in sorted_prs if pr.number == selected), None)
    if not selected_pr:
        ctx.textual.error_text(f"PR #{selected} not found in list")
        ctx.textual.end_step("error")
        return Error(f"PR #{selected} not found in list")

    ctx.textual.success_text(f"Selected PR #{selected_pr.number}: {selected_pr.title}")
    ctx.textual.end_step("success")

    return Success(
        f"Selected PR #{selected_pr.number}",
        metadata={
            "review_pr_number": selected_pr.number,
            "review_pr_title": selected_pr.title,
            "review_pr_head": selected_pr.head_ref,
            "review_pr_base": selected_pr.base_ref,
        },
    )


def fetch_pr_review_bundle(ctx: WorkflowContext) -> WorkflowResult:
    """
    Fetch all data needed for a full PR review cycle.

    Builds a complete review bundle: PR metadata, diff, file stats,
    inline review threads (separate from general comments), and commit SHA.

    Requires (from ctx.data):
        review_pr_number (int): PR number

    Outputs (saved to ctx.data):
        review_pr (UIPullRequest): Pull request details
        review_diff (str): Full unified diff
        review_changed_files (List[str]): Changed file paths (may be subset for large PRs)
        review_changed_files_with_stats (List[UIFileChange]): All files with add/del stats
        review_commit_sha (str): Head commit SHA
        review_threads (List[UICommentThread]): Inline review threads (unresolved)
        review_general_comments (List[UICommentThread]): General PR-level comments
        pr_template (str | None): PR template content if available

    Returns:
        Success, Skip (empty diff), or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Fetch PR Review Bundle")

    pr_number = ctx.get("review_pr_number")
    if not pr_number:
        ctx.textual.error_text("No PR number in context (run select_pr_for_code_review first)")
        ctx.textual.end_step("error")
        return Error("No PR number in context (run select_pr_for_code_review first)")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    # Fetch PR details, files with stats, and commit SHA
    with ctx.textual.loading(f"Fetching PR #{pr_number} data..."):
        pr_result = ctx.github.get_pull_request(pr_number)
        files_result = ctx.github.get_pr_files_with_stats(pr_number)
        sha_result = ctx.github.get_pr_commit_sha(pr_number)

    # Validate PR
    match pr_result:
        case ClientSuccess(data=pr):
            pass
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to fetch PR: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to fetch PR: {err}")

    # Validate files
    match files_result:
        case ClientSuccess(data=all_files_with_stats):
            changed_file_paths = [f.path for f in all_files_with_stats]
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to fetch changed files: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to fetch files: {err}")

    # Fetch diff. For fork PRs, gh pr diff is the source of truth because the
    # head branch usually does not exist under the local origin remote.
    with ctx.textual.loading(f"Fetching PR #{pr_number} diff..."):
        diff_result, diff_is_github_source = _get_review_diff(ctx, pr_number, pr, all_files_with_stats)

    # Validate diff — fallback to per-file patches if PR is too large
    match diff_result:
        case ClientSuccess(data=diff):
            if not diff or not diff.strip():
                if all_files_with_stats:
                    ctx.textual.warning_text(
                        "Diff came back empty despite changed files in the PR."
                    )
                    ctx.textual.end_step("error")
                    return Error("Could not resolve PR diff despite changed files")
                ctx.textual.dim_text("PR diff is empty — nothing to review.")
                ctx.textual.end_step("success")
                return Exit("Empty PR diff")
        case ClientError(error_message=err) if "too_large" in err or "too large" in err.lower():
            ctx.textual.warning_text("PR diff is too large. Selecting files that matter...")

            # AI selects which files to review from the already-fetched stats
            if ctx.ai:
                with ctx.textual.loading(f"AI selecting from {len(all_files_with_stats)} files..."):
                    selected_paths = select_files_for_review(all_files_with_stats, ctx.ai)
            else:
                from ..operations.code_review_operations import MAX_FILES_FOR_REVIEW
                selected_paths = [f.path for f in all_files_with_stats[:MAX_FILES_FOR_REVIEW]]

            ctx.textual.dim_text(f"Reviewing {len(selected_paths)} of {len(all_files_with_stats)} files")
            changed_file_paths = selected_paths

            with ctx.textual.loading("Fetching patches for selected files..."):
                patches_result = ctx.github.get_pr_file_patches(pr_number, selected_paths)

            match patches_result:
                case ClientSuccess(data=patches_diff) if patches_diff:
                    diff = patches_diff
                    # Files-API patches ARE GitHub's diff hunks — valid as the
                    # publishable-lines source.
                    diff_is_github_source = True
                case ClientError(error_message=err):
                    ctx.textual.error_text(f"Failed to fetch file patches: {err}")
                    ctx.textual.end_step("error")
                    return Error(f"Could not fetch file patches: {err}")
                case _:
                    ctx.textual.end_step("error")
                    return Error("Could not fetch file patches for large PR")
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to fetch diff: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to fetch diff: {err}")

    # Validate commit SHA
    match sha_result:
        case ClientSuccess(data=commit_sha):
            pass
        case ClientError(error_message=err):
            ctx.textual.warning_text(f"Could not get commit SHA: {err}")
            commit_sha = ""

    # Display file changes summary
    formatted_files, formatted_summary = compute_diff_stat(diff)
    diff_manager = get_or_create_diff_manager(diff, ctx.data)

    # Attach GitHub's own diff as the publishable-lines source (D-008). The review diff
    # may be a local `git diff -U20` whose extra context lines GitHub rejects for inline
    # comments; publish validation must use GitHub's hunks. When unavailable, the manager
    # falls back to added-lines-only, which GitHub always accepts.
    github_diff = diff if diff_is_github_source else None
    if github_diff is None:
        github_diff_result = ctx.github.get_pr_diff(pr_number)
        match github_diff_result:
            case ClientSuccess(data=gh_diff) if gh_diff and gh_diff.strip():
                github_diff = gh_diff
            case _:
                logger.warning(
                    "github_diff_unavailable_for_publish_validation",
                    pr_number=pr_number,
                    fallback="added_lines_only",
                )
    if github_diff:
        diff_manager.attach_github_diff(github_diff)

    ctx.textual.show_diff_stat(formatted_files, formatted_summary, title="Files affected:")

    # Fetch inline review threads and general comments separately
    review_threads = []
    general_comments = []
    review_current_user = None
    with ctx.textual.loading("Fetching existing review comments..."):
        threads_result = ctx.github.get_pr_review_threads(pr_number, include_resolved=True)
        match threads_result:
            case ClientSuccess(data=threads):
                review_threads = threads
            case ClientError(error_message=err):
                # Threads drive dedup against existing comments — reviewing without
                # them risks re-proposing duplicates, so the degradation must be visible.
                ctx.textual.warning_text(f"Could not fetch review threads: {err}")

        general_result = ctx.github.get_pr_general_comments(pr_number)
        match general_result:
            case ClientSuccess(data=general):
                general_comments = general
            case ClientError(error_message=err):
                ctx.textual.warning_text(f"Could not fetch general comments: {err}")

        current_user_result = ctx.github.get_current_user()
        match current_user_result:
            case ClientSuccess(data=current_user):
                review_current_user = current_user
            case ClientError(error_message=err):
                ctx.textual.warning_text(f"Could not get current user: {err}")

    ctx.textual.dim_text(
        f"{len(changed_file_paths)} files · {formatted_summary} · "
        f"{len(review_threads)} review thread(s) · {len(general_comments)} general comment(s)"
    )

    ctx.textual.end_step("success")

    pr_template = ctx.github.get_pr_template()

    return Success(
        f"Fetched PR #{pr_number} review bundle",
        metadata={
            "review_pr": pr,
            "review_diff": diff,
            "review_diff_manager": diff_manager,
            "review_changed_files": changed_file_paths,
            "review_changed_files_with_stats": all_files_with_stats,
            "review_commit_sha": commit_sha,
            "review_threads": review_threads,
            "review_general_comments": general_comments,
            "review_current_user": review_current_user,
            "pr_template": pr_template,
        },
    )


def _get_review_diff(
    ctx: WorkflowContext,
    pr_number: int,
    pr: UIPullRequest,
    all_files_with_stats: list,
):
    """
    Resolve the most trustworthy diff source for a PR review.

    Returns:
        Tuple of (diff ClientResult, is_github_source). ``is_github_source`` is True when
        the diff came from GitHub itself (``gh pr diff``) — that diff can then double as
        the publishable-lines source without a second fetch.
    """
    if pr.is_cross_repository:
        logger.info(
            "review_diff_using_github",
            pr_number=pr_number,
            reason="cross_repository_pr",
            head_repository_owner=pr.head_repository_owner,
        )
        return ctx.github.get_pr_diff(pr_number), True

    if not ctx.git:
        logger.debug("Git plugin not available; using gh pr diff")
        return ctx.github.get_pr_diff(pr_number), True

    fetch_result = ctx.git.fetch(all=True)
    match fetch_result:
        case ClientError(error_message=err):
            logger.warning(f"Git fetch failed: {err}, will try diff anyway")
        case _:
            pass

    git_diff_result = ctx.git.get_branch_diff(
        pr.base_ref,
        pr.head_ref,
        context_lines=20,
        use_remote=True,
    )

    match git_diff_result:
        case ClientSuccess(data=diff) if diff and diff.strip():
            return git_diff_result, False
        case ClientSuccess(data=_):
            if all_files_with_stats:
                logger.warning(
                    "git_diff_empty_with_changed_files",
                    pr_number=pr_number,
                    base_ref=pr.base_ref,
                    head_ref=pr.head_ref,
                    files_changed=len(all_files_with_stats),
                )
                return ctx.github.get_pr_diff(pr_number), True
            return git_diff_result, False
        case ClientError(error_message=err):
            logger.warning(
                "git_diff_failed_falling_back_to_github",
                pr_number=pr_number,
                base_ref=pr.base_ref,
                head_ref=pr.head_ref,
                error=err,
            )
            return ctx.github.get_pr_diff(pr_number), True


def _resolve_headless_adapter(cli_preference: str):
    """Return the first available headless adapter, or None."""
    if cli_preference == "auto":
        for cli_name in HEADLESS_ADAPTER_REGISTRY:
            candidate = get_headless_adapter(cli_name)
            if candidate.is_available():
                return candidate
        return None

    try:
        candidate = get_headless_adapter(cli_preference)
    except ValueError:
        return None

    return candidate if candidate.is_available() else None


# ============================================================================
# PHASE 2: CHEAP CONTEXT STEPS (pre-AI, deterministic)
# ============================================================================


def build_change_manifest(ctx: WorkflowContext) -> WorkflowResult:
    """
    Build a structured manifest of the PR changes (no AI involved).

    Converts UIFileChange objects into a typed ChangeManifest that serves
    as cheap context for both AI-directed workflows.

    Requires (from ctx.data):
        review_pr (UIPullRequest): Pull request details
        review_changed_files_with_stats (List[UIFileChange]): Files with add/del stats

    Outputs (saved to ctx.data):
        change_manifest (ChangeManifest): Structured PR context

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Change Manifest")

    pr = ctx.get("review_pr")
    files = ctx.get("review_changed_files_with_stats", [])

    if not pr:
        ctx.textual.error_text("No PR data in context (run fetch_pr_review_bundle first)")
        ctx.textual.end_step("error")
        return Error("No PR data in context (run fetch_pr_review_bundle first)")

    try:
        manifest = build_change_manifest_operation(pr, files)
    except Exception as e:
        ctx.textual.error_text(f"Failed to build change manifest: {e}")
        ctx.textual.end_step("error")
        return Error(f"Failed to build change manifest: {e}")

    test_count = sum(1 for f in manifest.files if f.is_test)
    docs_count = sum(1 for f in manifest.files if f.is_docs)
    config_count = sum(1 for f in manifest.files if f.is_config)
    generated_count = sum(1 for f in manifest.files if f.is_generated)
    lockfile_count = sum(1 for f in manifest.files if f.is_lockfile)
    rename_only_count = sum(1 for f in manifest.files if f.is_rename_only)
    ctx.textual.success_text(
        f"✓ {len(manifest.files)} files analysed"
        + (f" ({test_count} test files)" if test_count else "")
        + f" · +{manifest.total_additions} -{manifest.total_deletions}"
    )
    logger.debug(
        "change_manifest_census",
        tests=test_count,
        docs=docs_count,
        config=config_count,
        generated=generated_count,
        lockfiles=lockfile_count,
        rename_only=rename_only_count,
    )
    ctx.textual.end_step("success")
    return Success("Change manifest built", metadata={"change_manifest": manifest})


def build_existing_comments_index(ctx: WorkflowContext) -> WorkflowResult:
    """
    Build a compact index of existing PR comments for deduplication.

    Flattens inline review threads and general PR comments into a lightweight
    list of ExistingCommentIndexEntry objects. The index is used later to
    avoid AI findings that duplicate comments already posted.

    Requires (from ctx.data):
        review_threads (List[UICommentThread]): Inline review threads
        review_general_comments (List[UICommentThread]): General PR-level comments

    Outputs (saved to ctx.data):
        existing_comments_index (List[ExistingCommentIndexEntry])

    Returns:
        Success
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Existing Comments Index")

    threads = ctx.get("review_threads", [])
    general = ctx.get("review_general_comments", [])
    changed_files = ctx.get("review_changed_files_with_stats", [])

    try:
        index = build_existing_comments_index_operation(threads, general)
        is_smallish_pr = len(changed_files) <= 8
        comment_context = build_comment_review_context(
            threads,
            general,
            max_entries=4 if is_smallish_pr else 8,
            max_chars=900 if is_smallish_pr else 1800,
            include_resolved=False,
            bug_risk_only=True,
        )
    except Exception as e:
        ctx.textual.error_text(f"Failed to build comments index: {e}")
        ctx.textual.end_step("error")
        return Error(f"Failed to build comments index: {e}")

    resolved_count = sum(1 for e in index if e.is_resolved)
    adjudicated_count = sum(1 for e in index if e.is_adjudicated)
    msg = f"✓ {len(index)} existing comment(s) indexed"
    if resolved_count:
        msg += f" ({resolved_count} resolved)"
    ctx.textual.success_text(msg)
    logger.debug(
        "existing_comments_index_built",
        existing_comments_total=len(index),
        comments_for_prompt_count=len(comment_context),
        dedupe_comment_count=len(index),
        resolved_comments_count=resolved_count,
        unresolved_comments_count=len(index) - resolved_count,
        adjudicated_threads_count=adjudicated_count,
        filtered_out_comment_entries=max(0, len(index) - len(comment_context)),
    )
    ctx.textual.end_step("success")
    return Success(
        "Comments index built",
        metadata={
            "existing_comments_index": index,
            "comment_review_context": comment_context,
        },
    )


def classify_pr(ctx: WorkflowContext) -> WorkflowResult:
    """
    Classify PR size and composition before planning.

    Requires:
        ctx.textual: Textual UI context.

    Inputs (from ctx.data):
        change_manifest (ChangeManifest): Structured PR change summary.
        existing_comments_index (List[ExistingCommentIndexEntry], optional): Existing comments used to estimate review activity.
        review_threads (List[UICommentThread], optional): Current review threads.

    Outputs (saved to ctx.data):
        pr_classification (PRClassification): Deterministic PR classification.
        review_profile (ReviewProfile): Resolved review profile used during classification.

    Returns:
        Success: When PR classification is computed successfully.
        Error: When required context is missing or the step cannot run.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Classify PR")

    manifest = ctx.get("change_manifest")
    comments_index = ctx.get("existing_comments_index", [])
    review_threads = ctx.get("review_threads", [])
    review_profile = _get_review_profile(ctx)

    if not manifest:
        ctx.textual.error_text("No change manifest in context")
        ctx.textual.end_step("error")
        return Error("No change manifest in context")

    from ..operations.review_strategy_operations import classify_pr as classify_pr_operation

    classification = classify_pr_operation(
        manifest,
        comment_entries=len(comments_index),
        comment_threads=len(review_threads),
        review_profile=review_profile,
    )
    
    logger.debug(
        "pr_classified",
        size_class=classification.size_class,
        files_changed=classification.files_changed,
        total_lines_changed=classification.total_lines_changed,
        comment_entries=classification.comment_entries,
    )
    _render_pr_classification(ctx, classification)
    ctx.textual.end_step("success")
    return Success(
        "PR classified",
        metadata={
            "pr_classification": classification,
            "review_profile": review_profile,
        },
    )

def score_review_candidates(ctx: WorkflowContext) -> WorkflowResult:
    """
    Rank changed files and precompute excluded files.

    Requires:
        ctx.textual: Textual UI context.

    Inputs (from ctx.data):
        change_manifest (ChangeManifest): Structured PR change summary.

    Outputs (saved to ctx.data):
        review_profile (ReviewProfile): Resolved review profile used during scoring.
        review_candidates (List[ScoredReviewCandidate]): Ranked review candidates.
        excluded_review_files (List[ExcludedFileEntry]): Files excluded from deep review.

    Returns:
        Success: When review candidates are scored successfully.
        Exit: When no reviewable candidates remain after exclusions.
        Error: When required context is missing or the step cannot run.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Score Review Candidates")

    manifest = ctx.get("change_manifest")
    review_profile = _get_review_profile(ctx)
    if not manifest:
        ctx.textual.error_text("No change manifest in context")
        ctx.textual.end_step("error")
        return Error("No change manifest in context")

    from ..operations.review_strategy_operations import (
        score_review_candidates as score_review_candidates_operation,
    )

    candidates, excluded = score_review_candidates_operation(manifest, review_profile=review_profile)

    logger.debug(
        "review_candidates_scored",
        candidates=len(candidates),
        excluded=len(excluded),
        top_candidates=[candidate.path for candidate in candidates[:5]],
    )
    if not candidates:
        ctx.textual.dim_text("No reviewable candidates remain after exclusions.")
        ctx.textual.end_step("skip")
        return Exit(
            "No reviewable candidates after exclusions",
            metadata={
                "review_profile": review_profile,
                "review_candidates": candidates,
                "excluded_review_files": excluded,
            },
        )
    ctx.textual.success_text(f"✓ {len(candidates)} candidate file(s), {len(excluded)} excluded")
    for candidate in candidates[:5]:
        ctx.textual.dim_text(
            f"{candidate.path} · {candidate.priority.value} · score {candidate.score}"
        )
    ctx.textual.end_step("success")
    return Success(
        "Review candidates scored",
        metadata={
            "review_profile": review_profile,
            "review_candidates": candidates,
            "excluded_review_files": excluded,
        },
    )


def build_review_checklist(ctx: WorkflowContext) -> WorkflowResult:
    """
    Assemble the review checklist for this PR.

    Delegates checklist resolution to ChecklistManager so project-specific
    checklist loading can evolve without changing workflow orchestration.

    Outputs (saved to ctx.data):
        review_checklist (List[ReviewChecklistItem])

    Returns:
        Success
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Review Checklist")

    if not ctx.github_managers:
        ctx.textual.error_text("GitHub managers are not available in workflow context.")
        ctx.textual.end_step("error")
        return Error("GitHub managers are not available in workflow context.")

    checklist = ctx.github_managers.checklist.get_effective_checklist()
    applicable_preview_ids = _build_review_checklist_preview(ctx, checklist)
    review_profile = _get_review_profile(ctx)
    ctx.data["review_checklist"] = checklist
    ctx.data["review_checklist_applicable_preview"] = applicable_preview_ids
    ctx.data["review_profile"] = review_profile

    manifest = ctx.get("change_manifest")
    candidates = ctx.get("review_candidates", [])
    profile_path = None
    checklist_path = None
    if ctx.github_managers:
        profile_path = ctx.github_managers.review_profile._profile_path()
        checklist_path = ctx.github_managers.checklist._checklist_path()
    logger.debug(
        "review_config_applied_to_pr",
        project_root=str(ctx.data.get("project_root")) if ctx.data.get("project_root") else None,
        profile_source=("project" if profile_path and profile_path.exists() else "default"),
        profile_path=str(profile_path) if profile_path else None,
        checklist_source=("project" if checklist_path and checklist_path.exists() else "default"),
        checklist_path=str(checklist_path) if checklist_path else None,
        manifest_files=len(manifest.files) if manifest else 0,
        candidate_files=len(candidates),
        offered_checklist_ids=[str(item.id) for item in checklist],
        applicable_checklist_preview=sorted(applicable_preview_ids),
        top_candidate_paths=[candidate.path for candidate in candidates[:5]],
    )

    _render_review_checklist(ctx, checklist, applicable_preview_ids)
    ctx.textual.end_step("success")
    return Success(
        "Review checklist built",
        metadata={
            "review_checklist": checklist,
            "review_checklist_applicable_preview": applicable_preview_ids,
        },
    )


def select_review_strategy(ctx: WorkflowContext) -> WorkflowResult:
    """
    Choose review strategy based on deterministic PR classification.

    Requires:
        ctx.textual: Textual UI context.

    Inputs (from ctx.data):
        pr_classification (PRClassification): Deterministic PR classification.

    Outputs (saved to ctx.data):
        review_strategy (ReviewStrategy): Execution strategy for planning and findings.

    Returns:
        Success: When a review strategy is selected successfully.
        Error: When required context is missing or the step cannot run.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Select Review Strategy")

    classification = ctx.get("pr_classification")
    if not classification:
        ctx.textual.error_text("No pr_classification in context")
        ctx.textual.end_step("error")
        return Error("No pr_classification in context")

    from ..operations.review_strategy_operations import (
        select_review_strategy as select_review_strategy_operation,
    )

    strategy = select_review_strategy_operation(classification)

    logger.debug(
        "review_strategy_selected",
        strategy=strategy.strategy,
        size_class=strategy.size_class,
        max_focus_files=strategy.max_focus_files,
        max_prompt_chars=strategy.max_prompt_chars,
        max_comment_entries=strategy.max_comment_entries,
    )
    # Speak outcome, not mechanics: strategy enum names and prompt budgets in chars
    # mean nothing to the reviewer — what matters is how the review will proceed and
    # how many files it will focus on. Mechanics stay in the debug log above.
    strategy_labels = {
        "direct_findings": "direct review in one pass",
        "light_plan": "lightweight plan, then focused review",
        "batched_findings": "planned review in batches",
    }
    approach = strategy_labels.get(strategy.strategy.value, strategy.strategy.value)
    ctx.textual.success_text(
        f"✓ Review approach: {approach} · up to {strategy.max_focus_files} focus file(s)"
    )
    if strategy.reason:
        ctx.textual.dim_text(strategy.reason)
    ctx.textual.end_step("success")
    return Success("Review strategy selected", metadata={"review_strategy": strategy})


# ============================================================================
# PHASE 3: DIRECTED AI ANALYSIS (first AI call)
# ============================================================================


def ai_review_plan(ctx: WorkflowContext) -> WorkflowResult:
    """
    First AI call: decide which files to read and which checklist items apply.

    Sends a structured prompt to the selected headless CLI (Claude, Gemini, Codex).
    The prompt includes the change manifest, existing comments index, and review
    checklist. It also instructs the AI to use any project-specific skills or
    guidelines available in its context (each CLI knows where its own skills live).

    On parse failure, falls back to a local conservative heuristic plan.

    Requires (from ctx.data):
        change_manifest (ChangeManifest)
        existing_comments_index (List[ExistingCommentIndexEntry])
        review_checklist (List[ReviewChecklistItem])
        cli_preference (str): "claude" | "gemini" | "codex" | "auto"

    Outputs (saved to ctx.data):
        review_plan (ReviewPlan)

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("AI Review Plan")

    manifest = ctx.get("change_manifest")
    comments_context = ctx.get("comment_review_context", [])
    checklist = ctx.get("review_checklist", [])
    candidates = ctx.get("review_candidates", [])
    excluded_files = ctx.get("excluded_review_files", [])
    strategy = ctx.get("review_strategy")
    review_profile = _get_review_profile(ctx)
    cli_preference = ctx.data.get("cli_preference", "auto")
    project_root = ctx.data.get("project_root")

    if not manifest or not strategy:
        ctx.textual.error_text("Missing change_manifest or review_strategy in context")
        ctx.textual.end_step("error")
        return Error("Missing change_manifest or review_strategy in context")

    from ..operations.plan_prompt_operations import (
        build_review_plan_prompt,
        build_default_review_plan,
    )
    from ..models.review_models import ReviewPlan
    from pydantic import ValidationError

    if strategy.strategy == ReviewStrategyType.DIRECT_FINDINGS:
        fallback = build_default_review_plan(
            candidates,
            excluded_files,
            checklist,
            strategy,
            review_profile=review_profile,
        )
        ctx.data["review_plan"] = fallback
        ctx.textual.success_text(
            f"✓ Deterministic plan: {len(fallback.focus_files)} focus file(s) · "
            f"{len(fallback.excluded_files)} excluded"
        )
        _show_review_plan_summary(ctx, fallback)
        ctx.textual.end_step("success")
        return Success("Deterministic review plan built", metadata={"review_plan": fallback})

    adapter = _resolve_headless_adapter(cli_preference)

    if not adapter:
        ctx.textual.warning_text("No headless CLI available — using default review plan")
        fallback = build_default_review_plan(
            candidates,
            excluded_files,
            checklist,
            strategy,
            review_profile=review_profile,
        )
        ctx.data["review_plan"] = fallback
        ctx.textual.dim_text(f"Default plan: {len(fallback.focus_files)} focus files")
        _show_review_plan_summary(ctx, fallback)
        ctx.textual.end_step("success")
        return Success("Default review plan used (no CLI available)", metadata={"review_plan": fallback})

    prompt = build_review_plan_prompt(
        manifest,
        comments_context,
        checklist,
        candidates,
        strategy,
        excluded_files,
        review_profile,
    )

    cli_display = adapter.cli_name.value.capitalize()
    _log_ai_prompt(
        step_name="ai_review_plan",
        cli_name=adapter.cli_name.value,
        prompt=prompt,
        manifest_files=len(manifest.files),
        comment_entries=len(comments_context),
        checklist_items=len(checklist),
        candidate_files=len(candidates),
        strategy=str(strategy.strategy),
    )
    with ctx.textual.loading(f"Asking {cli_display} to plan the review…"):
        response = adapter.execute(prompt, cwd=project_root, timeout=240)
    _log_ai_response(
        step_name="ai_review_plan",
        cli_name=adapter.cli_name.value,
        stdout=response.stdout,
        stderr=response.stderr,
        exit_code=response.exit_code,
        manifest_files=len(manifest.files),
        comment_entries=len(comments_context),
        checklist_items=len(checklist),
        candidate_files=len(candidates),
        strategy=str(strategy.strategy),
    )

    if not response.succeeded:
        # Raw stderr means nothing to the reviewer; the actionable fact is that the
        # AI plan failed and a deterministic plan takes over. Details go to the log
        # (already captured in full by _log_ai_response above).
        ctx.textual.warning_text(
            "The AI couldn't produce a review plan — falling back to the automatic plan "
            "(top-scored files)."
        )
        fallback = build_default_review_plan(
            candidates,
            excluded_files,
            checklist,
            strategy,
            review_profile=review_profile,
        )
        ctx.data["review_plan"] = fallback
        _show_review_plan_summary(ctx, fallback)
        ctx.textual.end_step("success")
        return Success("Default review plan used (CLI error)", metadata={"review_plan": fallback})

    # Parse JSON response
    parse_error: Optional[str] = None
    match extract_json_payload(response.stdout, kind="object"):
        case ClientSuccess(data=payload):
            try:
                plan = ReviewPlan.model_validate(payload)
            except ValidationError as e:
                parse_error = str(e)
        case ClientError(error_message=err):
            parse_error = err

    if parse_error is not None:
        # Same as the CLI-failure path: no raw pydantic/JSON error dumps on screen.
        logger.debug("review_plan_parse_failed", parse_error=parse_error)
        ctx.textual.warning_text(
            "The AI's review plan couldn't be read — falling back to the automatic plan "
            "(top-scored files)."
        )
        fallback = build_default_review_plan(
            candidates,
            excluded_files,
            checklist,
            strategy,
            review_profile=review_profile,
        )
        ctx.data["review_plan"] = fallback
        _show_review_plan_summary(ctx, fallback)
        ctx.textual.end_step("success")
        return Success("Default review plan used (parse error)", metadata={"review_plan": fallback})

    ctx.data["review_plan"] = plan
    ctx.textual.success_text(
        f"✓ Plan: {len(plan.focus_files)} focus file(s) · "
        f"{len(plan.review_axes)} axes · "
        f"{len(plan.extra_context_requests)} extra context request(s)"
    )
    ctx.textual.text(" ")
    _show_review_plan_summary(ctx, plan)
    ctx.textual.end_step("success")
    return Success("Review plan built", metadata={"review_plan": plan})


def validate_review_plan(ctx: WorkflowContext) -> WorkflowResult:
    """
    Validate the AI-generated ReviewPlan against local semantic rules.

    Checks that all file paths exist in the manifest, read modes are valid,
    extra context requests don't exceed the limit, and full_file mode is only
    used for small or new files.

    Requires (from ctx.data):
        review_plan (ReviewPlan)
        change_manifest (ChangeManifest)

    Outputs (saved to ctx.data):
        validated_review_plan (ReviewPlan): Same plan if valid

    Returns:
        Success or Error (halts workflow on validation failure)
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Validate Review Plan")

    plan = ctx.get("review_plan")
    manifest = ctx.get("change_manifest")
    checklist = ctx.get("review_checklist", [])
    review_profile = _get_review_profile(ctx)

    if not plan or not manifest:
        ctx.textual.error_text("Missing review_plan or change_manifest in context")
        ctx.textual.end_step("error")
        return Error("Missing review_plan or change_manifest in context")

    from ..models.validators import ReviewPlanValidator
    from ..operations.plan_prompt_operations import build_default_review_plan

    offered_ids = frozenset(item.id for item in checklist)
    validator = ReviewPlanValidator(manifest, offered_ids)
    is_valid, errors = validator.validate_semantically(plan)

    if not is_valid:
        # Log errors but don't halt — auto-correct by falling back to default plan
        for err in errors:
            ctx.textual.warning_text(f"  ⚠ {err}")

        candidates = ctx.get("review_candidates", [])
        excluded_files = ctx.get("excluded_review_files", [])
        strategy = ctx.get("review_strategy")
        corrected = build_default_review_plan(
            candidates,
            excluded_files,
            checklist,
            strategy,
            review_profile=review_profile,
        )
        ctx.data["validated_review_plan"] = corrected
        ctx.textual.warning_text("Plan corrected: using conservative fallback")
        _show_review_plan_summary(ctx, corrected)
        ctx.textual.end_step("success")
        return Success("Review plan corrected (validation issues)", metadata={"validated_review_plan": corrected})

    ctx.data["validated_review_plan"] = plan
    ctx.textual.success_text("✓ Plan validated")
    _show_review_plan_validation_summary(ctx, plan)
    ctx.textual.end_step("success")
    return Success("Review plan validated", metadata={"validated_review_plan": plan})


def _get_review_profile(ctx: WorkflowContext) -> ReviewProfile:
    """Resolve review profile from workflow managers with cached fallback."""
    review_profile = ctx.get("review_profile")
    if review_profile:
        return review_profile
    if ctx.github_managers:
        return ctx.github_managers.review_profile.get_effective_profile()
    from ..review_profiles import DEFAULT_REVIEW_PROFILE

    return DEFAULT_REVIEW_PROFILE.model_copy(deep=True)


def _render_pr_classification(ctx: WorkflowContext, classification: PRClassification) -> None:
    """Render the classification as one human-readable summary.

    On screen: the size class, the two numbers that explain it, and the signals that
    change how the review will behave. Scoring internals (complexity score, roles,
    repeated call sites, machine-composed rationale) go to the debug log — they help
    diagnose a misclassification, not decide anything during a review.
    """
    ctx.textual.success_text(f"✓ PR classified as {classification.size_class.value.upper()}")
    ctx.textual.dim_text(
        f"{classification.files_changed} file(s) · "
        f"{classification.total_lines_changed} changed line(s)"
    )
    signals = []
    if classification.high_signal_files:
        signals.append(f"{classification.high_signal_files} critical file(s) touched")
    if classification.is_repetitive_migration:
        signals.append("repetitive change pattern (many similar call sites)")
    if classification.active_review:
        signals.append(f"review already in progress ({classification.comment_threads} thread(s))")
    if signals:
        ctx.textual.dim_text("Signals: " + " · ".join(signals))
    logger.debug(
        "pr_classification_detail",
        size_class=classification.size_class.value,
        complexity_score=classification.complexity_score,
        roles=classification.roles,
        repeated_callsite_files=classification.repeated_callsite_files,
        comment_threads=classification.comment_threads,
        comment_entries=classification.comment_entries,
        rationale=classification.rationale,
    )


def _build_review_checklist_preview(ctx: WorkflowContext, checklist: list) -> set[str]:
    """Build a deterministic preview of checklist categories that look relevant."""
    candidates = ctx.get("review_candidates", [])
    review_profile = _get_review_profile(ctx)

    from ..operations.review_profile_operations import select_review_axes

    applicable = select_review_axes(checklist, candidates, review_profile)
    return {str(item_id) for item_id in applicable}


def _render_review_checklist(
    ctx: WorkflowContext,
    checklist: list,
    applicable_preview_ids: set[str],
) -> None:
    """Render the resolved checklist with applicable categories emphasized."""
    applicable_count = sum(1 for item in checklist if str(item.id) in applicable_preview_ids)
    ctx.textual.success_text(
        f"✓ {applicable_count} of {len(checklist)} checklist categories look relevant for this PR"
    )
    ctx.textual.text(" ")
    for item in checklist:
        # Show the human-readable name, not the snake_case category id.
        label = item.name or str(item.id)
        if str(item.id) in applicable_preview_ids:
            ctx.textual.bold_text(label)
        else:
            ctx.textual.dim_text(label)


def _show_review_context_batches(ctx: WorkflowContext, batches: list) -> None:
    """Render batch composition for resolved review context."""
    for batch in batches:
        file_paths = list(getattr(batch, "files_context", {}).keys())
        related_count = len(getattr(batch, "related_files", {}) or {})
        degraded = getattr(batch, "degraded_context", False)

        ctx.textual.text(" ")
        # Keep the raw batch_id as the label: the findings step references the same
        # ids ("Reviewing batch_1…", "✓ batch_1 complete"), so the user can correlate.
        ctx.textual.bold_text(f"{batch.batch_id} · {len(file_paths)} file(s)")
        if related_count:
            ctx.textual.dim_text(f"  +{related_count} related file(s) included for context")
        if degraded:
            ctx.textual.dim_text("  context reduced to fit the AI prompt size limit")
        for path in file_paths:
            ctx.textual.dim_text(f"  {path}")


def _render_findings_batch_started(ctx: WorkflowContext, batch) -> None:
    """Render the start of a findings batch review."""
    file_paths = list(getattr(batch, "files_context", {}).keys())
    ctx.textual.text(" ")
    ctx.textual.bold_text(f"Reviewing {batch.batch_id} ({len(file_paths)} file(s))")
    for path in file_paths:
        ctx.textual.dim_text(f"  {path}")


def _retry_findings_batch_reformat(
    adapter, previous_stdout: str, cwd: Optional[str], batch_id: str, structured: bool, effort: Optional[str] = None
):
    """Ask the same CLI to reformat its own previous output as a JSON array, without
    rerunning the full analysis, using a short timeout distinct from the main one."""
    from ..operations.findings_operations import FINDINGS_DISALLOWED_TOOLS, findings_json_schema, parse_findings_response

    reformat_prompt = build_json_reformat_prompt(previous_stdout, kind="array")
    schema = findings_json_schema() if structured else None
    disallowed_tools = list(FINDINGS_DISALLOWED_TOOLS) if adapter.supports_tool_restriction else None
    _log_ai_prompt("ai_review_findings_reformat_retry", adapter.cli_name.value, reformat_prompt, batch_id=batch_id)
    response = adapter.execute(
        reformat_prompt,
        cwd=cwd,
        timeout=REFORMAT_RETRY_TIMEOUT_SECONDS,
        json_schema=schema,
        disallowed_tools=disallowed_tools,
        effort=effort if adapter.supports_effort_control else None,
    )
    _log_ai_response(
        step_name="ai_review_findings_reformat_retry",
        cli_name=adapter.cli_name.value,
        stdout=response.stdout,
        stderr=response.stderr,
        exit_code=response.exit_code,
        batch_id=batch_id,
    )
    if not response.succeeded:
        return ClientError(
            error_message=f"Reformat retry CLI call failed (exit {response.exit_code})",
            error_code="REFORMAT_RETRY_FAILED",
            log_level="warning",
        )
    return parse_findings_response(response.stdout, structured=structured)


def _render_findings_batch_split(ctx: WorkflowContext, batch_id: str, produced_batches: list[str]) -> None:
    """Render a batch split caused by prompt budget constraints."""
    ctx.textual.dim_text(
        f"{batch_id} was too large for one AI call — split into {', '.join(produced_batches)}"
    )


def _render_findings_batch_degraded(ctx: WorkflowContext, batch_id: str) -> None:
    """Render an in-place context reduction (no new batches) caused by prompt budget constraints."""
    ctx.textual.dim_text(f"{batch_id} was too large — file context reduced to fit the AI call")


def _retry_timed_out_worktree_batch(ctx: WorkflowContext, batch, run, strategy) -> Optional[tuple]:
    """Retry a timed-out worktree_reference batch once in bounded hunks_only mode.

    Runs on the step thread (UI access is fine). Returns (fallback_batch, outcome)
    when the retry was executed, or None when no bounded fallback was possible
    (no hunks, or the fallback prompt itself exceeds the budget) — the caller then
    keeps the original failed outcome.
    """
    from ..operations.findings_operations import (
        build_findings_prompt_parts,
        build_timeout_fallback_batch,
    )

    fallback = build_timeout_fallback_batch(
        batch, ctx.get("review_diff", ""), diff_manager=ctx.get("review_diff_manager")
    )
    if not fallback:
        return None
    prompt = build_findings_prompt_parts(fallback)["prompt"]
    if strategy and len(prompt) > strategy.max_prompt_chars:
        return None

    ctx.textual.dim_text(
        f"{batch.batch_id} timed out exploring the worktree — retrying with inline diff hunks only"
    )
    logger.info(
        "findings_batch_timeout_fallback",
        batch_id=batch.batch_id,
        fallback_batch_id=fallback.batch_id,
        prompt_actual_chars=len(prompt),
    )
    with ctx.textual.loading(f"Retrying {batch.batch_id} with inline hunks…"):
        outcome = run((fallback, prompt, None))
    return fallback, outcome


def _render_findings_batch_result(
    ctx: WorkflowContext,
    batch_id: str,
    *,
    status: str,
    findings_count: int = 0,
    detail: str = "",
) -> None:
    """Render the outcome of a findings batch review."""
    if status == "success":
        ctx.textual.success_text(f"✓ {batch_id} complete · {findings_count} raw finding(s)")
        return

    message = f"{batch_id} {status}"
    if detail:
        message += f" · {detail}"
    ctx.textual.warning_text(message)


def _attach_content_provider(diff_manager, root: Optional[str]) -> None:
    """
    Give the diff manager a way to read whole files from ``root``.

    Only call this with a root already verified to hold the PR's head revision — the
    provider is trusted to return the code the diff describes.
    """
    if diff_manager is None or not root:
        return

    from ..operations.context_resolution_operations import read_file_content

    diff_manager.attach_content_provider(lambda path: read_file_content(path, root))


def _resolve_file_read_access(ctx: WorkflowContext, worktree_path: Optional[str]):
    """
    Decide whether files on disk may be used as this PR's code.

    Worktree creation is allowed to fail in the workflow, and the fallback root is the
    user's own checkout — which is usually on a different branch. Query its HEAD and
    dirty state so the decision is made on facts rather than assumed.
    """
    from ..operations.context_resolution_operations import resolve_file_read_access

    if worktree_path:
        return resolve_file_read_access(worktree_path)

    head_sha = ctx.data.get("review_commit_sha")
    checkout_sha = None
    checkout_dirty = None

    if ctx.git:
        match ctx.git.get_current_commit():
            case ClientSuccess(data=sha):
                checkout_sha = (sha or "").strip()
            case ClientError(error_message=err):
                logger.debug("checkout_sha_unavailable", error=err)

        match ctx.git.has_uncommitted_changes():
            case ClientSuccess(data=dirty):
                checkout_dirty = dirty
            case ClientError(error_message=err):
                logger.debug("checkout_dirty_state_unavailable", error=err)

    access = resolve_file_read_access(
        worktree_path=None,
        head_sha=head_sha,
        checkout_sha=checkout_sha,
        checkout_dirty=checkout_dirty,
    )
    logger.debug(
        "file_read_access_resolved",
        allowed=access.allowed,
        source=access.source,
        reason=access.reason,
    )
    return access


def resolve_review_context(ctx: WorkflowContext) -> WorkflowResult:
    """
    Fetch the exact code context according to the validated review plan.

    For each file in the plan, extracts code using the chosen read_mode:
    - hunks_only: diff hunks as-is (already has 20 lines of context)
    - expanded_hunks: hunks + extra surrounding lines from the actual file
    - full_file: reads the complete file from disk

    Also resolves any extra context requests (related_tests, related_context).

    Requires (from ctx.data):
        validated_review_plan (ReviewPlan)
        change_manifest (ChangeManifest)
        review_diff (str)
        existing_comments_index (List[ExistingCommentIndexEntry])
        review_checklist (List[ReviewChecklistItem])

    Outputs (saved to ctx.data):
        review_context_package (ReviewContextPackage)

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Resolve Review Context")

    plan = ctx.get("validated_review_plan")
    manifest = ctx.get("change_manifest")
    diff = ctx.get("review_diff", "")
    comment_context = ctx.get("comment_review_context", [])
    checklist = ctx.get("review_checklist", [])
    strategy = ctx.get("review_strategy")
    worktree_path = ctx.data.get("worktree_path")
    project_root = worktree_path or ctx.data.get("project_root")

    if not plan or not manifest or not strategy:
        ctx.textual.error_text("Missing validated_review_plan, change_manifest or review_strategy in context")
        ctx.textual.end_step("error")
        return Error("Missing validated_review_plan, change_manifest or review_strategy in context")

    if not diff:
        ctx.textual.error_text("No diff in context (run fetch_pr_review_bundle first)")
        ctx.textual.end_step("error")
        return Error("No diff in context (run fetch_pr_review_bundle first)")

    from ..operations.context_resolution_operations import build_review_context_package
    diff_manager = ctx.get("review_diff_manager")

    read_access = _resolve_file_read_access(ctx, worktree_path)
    if read_access.allowed:
        ctx.textual.dim_text(f"Reading files from {read_access.source} ({read_access.reason})")
        # Same verified root powers the comment-rendering path, so a finding about
        # pre-existing code can show that code instead of nothing.
        _attach_content_provider(diff_manager, project_root)
    else:
        ctx.textual.warning_text(
            f"Reviewing from the diff only — {read_access.reason}. "
            "Full-file and expanded-hunk context are disabled to avoid mixing revisions."
        )

    try:
        with ctx.textual.loading("Extracting code context…"):
            package = build_review_context_package(
                plan=plan,
                diff=diff,
                manifest=manifest,
                checklist=checklist,
                comment_context=comment_context,
                strategy=strategy,
                cwd=project_root,
                diff_manager=diff_manager,
                allow_file_reads=read_access.allowed,
            )
    except Exception as e:
        ctx.textual.error_text(f"Failed to resolve review context: {e}")
        ctx.textual.end_step("error")
        return Error(f"Failed to resolve review context: {e}")

    ctx.data["review_context_package"] = package
    ctx.data["review_context_batches"] = package.batches
    ctx.data["review_file_reads_allowed"] = read_access.allowed

    batch_count = len(package.batches)
    files_count = sum(len(batch.files_context) for batch in package.batches)
    related_count = sum(len(batch.related_files) for batch in package.batches)

    ctx.textual.success_text(
        f"✓ Context: {files_count} focus file(s) in {batch_count} batch(es)"
        + (f" · {related_count} related file(s)" if related_count else "")
    )
    # Coverage honesty: name the files that will NOT be reviewed instead of hiding
    # them behind a count — silent coverage loss is indistinguishable from a full
    # review otherwise.
    trimmed_paths = sorted(
        {entry.path for batch in package.batches for entry in batch.excluded_files}
    )
    if trimmed_paths:
        ctx.textual.warning_text(
            f"⚠ {len(trimmed_paths)} file(s) will NOT be reviewed (context budget exceeded): "
            + ", ".join(trimmed_paths)
        )
    logger.debug(
        "review_context_summary",
        comments_in_context=sum(len(batch.comment_context) for batch in package.batches),
        trimmed_paths=trimmed_paths,
    )
    _show_review_context_batches(ctx, package.batches)
    ctx.textual.end_step("success")
    return Success(
        "Review context resolved",
        metadata={
            "review_context_package": package,
            "review_context_batches": package.batches,
            "review_file_reads_allowed": read_access.allowed,
        },
    )


# ============================================================================
# PHASE 4: TARGETED REVIEW (Second AI Call)
# ============================================================================


def _execute_findings_batch(
    adapter,
    batch,
    prompt: str,
    *,
    project_root: Optional[str],
    findings_schema: Optional[dict],
    disallowed_tools: Optional[list],
    effort: Optional[str],
    use_structured_output: bool,
    strategy_name: Optional[str],
) -> dict:
    """Run one findings batch end-to-end: CLI call, parse, reformat retry.

    Runs inside a worker thread when batches execute concurrently, so it must not
    touch `ctx`/the UI — it returns an outcome dict the step thread renders:
    {"status": "success" | "failed", "raw": list | None, "detail": str}.
    """
    from ..operations.findings_operations import parse_findings_response

    adapter_started_at = time.monotonic()
    response = adapter.execute(
        prompt,
        cwd=project_root,
        timeout=300,
        json_schema=findings_schema,
        disallowed_tools=disallowed_tools,
        effort=effort,
    )
    adapter_duration_seconds = time.monotonic() - adapter_started_at
    worktree_reference_count = sum(
        1 for entry in batch.files_context.values() if entry.worktree_reference
    )
    logger.info(
        "findings_batch_adapter_call",
        batch_id=batch.batch_id,
        cli=adapter.cli_name.value,
        files_context=len(batch.files_context),
        worktree_reference_count=worktree_reference_count,
        prompt_actual_chars=len(prompt),
        duration_seconds=round(adapter_duration_seconds, 3),
        exit_code=response.exit_code,
        timed_out=response.exit_code == 124,
        structured_output=use_structured_output,
        effort=effort,
    )
    _log_ai_response(
        step_name="ai_review_findings",
        cli_name=adapter.cli_name.value,
        stdout=response.stdout,
        stderr=response.stderr,
        exit_code=response.exit_code,
        batch_id=batch.batch_id,
        files_context=len(batch.files_context),
        related_files=len(batch.related_files),
        checklist_items=len(batch.checklist_applicable),
        comment_entries=len(batch.comment_context),
        strategy=strategy_name,
    )

    if not response.succeeded:
        logger.debug("findings_batch_failed", batch_id=batch.batch_id, exit_code=response.exit_code)
        return {
            "status": "failed",
            "raw": None,
            "detail": f"CLI exit {response.exit_code}",
            "timed_out": response.exit_code == 124,
        }

    match parse_findings_response(response.stdout, structured=use_structured_output):
        case ClientSuccess(data=raw) if isinstance(raw, list):
            return {"status": "success", "raw": raw, "detail": ""}
        case ClientSuccess(data=raw):
            # A structured success whose payload isn't a findings list (e.g. a dict)
            # must not vanish silently — treat it like any other parse failure.
            parse_error = f"non-list findings payload ({type(raw).__name__})"
        case ClientError(error_message=err):
            parse_error = err

    logger.debug("findings_batch_parse_failed", batch_id=batch.batch_id, error=parse_error)
    match _retry_findings_batch_reformat(
        adapter, response.stdout, project_root, batch.batch_id, use_structured_output, effort
    ):
        case ClientSuccess(data=raw) if isinstance(raw, list):
            logger.debug(
                "findings_batch_reformat_recovered",
                batch_id=batch.batch_id,
                findings_count=len(raw),
            )
            return {"status": "success", "raw": raw, "detail": ""}
        case _:
            logger.debug("findings_batch_reformat_failed", batch_id=batch.batch_id)
            return {"status": "failed", "raw": None, "detail": "parse error"}


def ai_review_findings(ctx: WorkflowContext) -> WorkflowResult:
    """
    Second AI call: find actionable problems in the exact code context.

    Sends the ReviewContextPackage (exact file content + applicable checklist +
    existing comments) to the selected headless CLI. The AI reviews only the
    code it was specifically directed to read in the planning phase.

    On parse failure or CLI error a batch is retried (reformat) and then marked
    failed. If every batch fails, the step returns Error — an empty result caused
    by total AI failure must not look like a clean review — while still publishing
    empty raw_findings so downstream steps run via the workflow's on_error: continue.

    When ReviewProfile.findings_synthesis_enabled is on and the PR touches more than
    one focus file, one extra best-effort cross-file synthesis batch (all hunks
    together, hunks_only) runs after the per-file batches; its findings are deduped
    against theirs before aggregation.

    Requires (from ctx.data):
        review_context_package (ReviewContextPackage)
        cli_preference (str): "claude" | "gemini" | "codex" | "auto"

    Outputs (saved to ctx.data):
        raw_findings (list | str): Raw AI output before normalization

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("AI Review Findings")

    batches = ctx.get("review_context_batches")
    strategy = ctx.get("review_strategy")
    cli_preference = ctx.data.get("cli_preference", "auto")
    project_root = ctx.data.get("worktree_path") or ctx.data.get("project_root")

    if not batches:
        ctx.textual.error_text("No review_context_batches in context (run resolve_review_context first)")
        ctx.textual.end_step("error")
        return Error("No review_context_batches in context (run resolve_review_context first)")

    from ..operations.findings_operations import (
        FINDINGS_DISALLOWED_TOOLS,
        FINDINGS_WORKTREE_REFERENCE_EFFORT,
        build_default_findings,
        build_findings_prompt_parts,
        findings_json_schema,
        summarize_findings_prompt_parts,
    )

    adapter = _resolve_headless_adapter(cli_preference)

    if not adapter:
        ctx.textual.warning_text("No headless CLI available — skipping AI findings")
        ctx.data["raw_findings"] = build_default_findings()
        # Keep the outputs consistent with every other exit of this step: downstream
        # reads ai_findings_failed, and it must be explicitly False here (nothing
        # failed — nothing ran).
        ctx.data["ai_findings_failed"] = False
        ctx.textual.end_step("success")
        return Success(
            "No findings (no CLI available)",
            metadata={"raw_findings": [], "ai_findings_failed": False},
        )

    # Structured output forces the CLI to return findings via a schema-validated tool
    # call instead of relying on the model to follow a "respond only with JSON" prompt
    # instruction, which models frequently ignore in favor of a prose summary.
    use_structured_output = adapter.supports_structured_output
    findings_schema = findings_json_schema() if use_structured_output else None
    # Removes Bash (and other unneeded tools) from the CLI's own session so it can't explore
    # far beyond the batch's worktree_reference files (D-011/O-003) — Read/Grep/Glob stay
    # available for the legitimate cross-file lookups the worktree_reference hint permits.
    disallowed_tools = list(FINDINGS_DISALLOWED_TOOLS) if adapter.supports_tool_restriction else None
    cli_display = adapter.cli_name.value.capitalize()
    aggregated_raw = []
    findings_failed = False
    batches_attempted = 0
    batches_succeeded = 0
    # Paths whose batch actually produced output — a failed/skipped batch's files were
    # NOT reviewed, and downstream passes (synthesis) must not claim they were.
    reviewed_paths: set[str] = set()
    batch_queue = list(batches)
    ctx.textual.dim_text(f"Reviewing {len(batch_queue)} batch(es) with {cli_display}")

    # Phase 1 — budget fitting stays sequential and deterministic: splits/degradations
    # requeue, so the set of ready-to-execute batches isn't known until this loop
    # reaches a fixpoint. No AI calls happen here.
    ready: list[tuple] = []  # (batch, prompt, effort)
    while batch_queue:
        batch = batch_queue.pop(0)
        prompt_parts = build_findings_prompt_parts(batch)
        prompt = prompt_parts["prompt"]
        fitted_batches, changed = get_prompt_budget_manager().fit_batch_to_budget(
            batch, prompt_parts, strategy.max_prompt_chars
        )
        if changed:
            logger.debug(
                "findings_batch_rebalanced",
                original_batch_id=batch.batch_id,
                produced_batches=[candidate.batch_id for candidate in fitted_batches],
                prompt_actual_chars=len(prompt),
                prompt_budget_target_chars=strategy.max_prompt_chars,
            )
            is_actual_split = len(fitted_batches) > 1 or fitted_batches[0].batch_id != batch.batch_id
            if is_actual_split:
                _render_findings_batch_split(
                    ctx,
                    batch.batch_id,
                    [candidate.batch_id for candidate in fitted_batches],
                )
            else:
                _render_findings_batch_degraded(ctx, batch.batch_id)
            batch_queue = fitted_batches + batch_queue
            continue

        batch = fitted_batches[0]
        batches_attempted += 1
        prompt_parts = build_findings_prompt_parts(batch)
        prompt = prompt_parts["prompt"]
        prompt_breakdown = summarize_findings_prompt_parts(prompt_parts)
        _log_ai_prompt(
            step_name="ai_review_findings",
            cli_name=adapter.cli_name.value,
            prompt=prompt,
            batch_id=batch.batch_id,
            files_context=len(batch.files_context),
            related_files=len(batch.related_files),
            checklist_items=len(batch.checklist_applicable),
            comment_entries=len(batch.comment_context),
            strategy=str(strategy.strategy) if strategy else None,
            prompt_budget_target_chars=strategy.max_prompt_chars,
            prompt_actual_chars=len(prompt),
            prompt_still_too_large=batch.prompt_still_too_large,
            degraded_context=batch.degraded_context,
            **prompt_breakdown,
        )
        if len(prompt) > strategy.max_prompt_chars:
            findings_failed = True
            logger.error(
                "findings_batch_over_budget",
                batch_id=batch.batch_id,
                prompt_budget_target_chars=strategy.max_prompt_chars,
                prompt_actual_chars=len(prompt),
            )
            skipped_paths = ", ".join(sorted(batch.files_context)) or "unknown files"
            ctx.textual.warning_text(
                f"⚠ {batch.batch_id} skipped — too large even after reduction. "
                f"NOT reviewed: {skipped_paths}"
            )
            continue
        worktree_reference_count = sum(
            1 for entry in batch.files_context.values() if entry.worktree_reference
        )
        # A worktree_reference batch is the one shape shown to reliably drive O-003's
        # duration/timeout problem (D-011) — capping effort only here, not on every batch,
        # leaves batches that already complete quickly untouched.
        effort = (
            FINDINGS_WORKTREE_REFERENCE_EFFORT
            if worktree_reference_count and adapter.supports_effort_control
            else None
        )
        _render_findings_batch_started(ctx, batch)
        ready.append((batch, prompt, effort))

    # Phase 2 — execute ready batches through a small worker pool. Adapter calls are
    # independent subprocesses, so the only sequential cost was the loop itself
    # (real baseline: 307s wall for 6 batches, PR #3596). Workers never touch the UI;
    # results render here, on the step thread, as each batch completes.
    def _run(entry: tuple) -> dict:
        entry_batch, entry_prompt, entry_effort = entry
        try:
            return _execute_findings_batch(
                adapter,
                entry_batch,
                entry_prompt,
                project_root=project_root,
                findings_schema=findings_schema,
                disallowed_tools=disallowed_tools,
                effort=entry_effort,
                use_structured_output=use_structured_output,
                strategy_name=str(strategy.strategy) if strategy else None,
            )
        except Exception as exc:
            logger.error("findings_batch_crashed", batch_id=entry_batch.batch_id, error=str(exc))
            return {"status": "failed", "raw": None, "detail": f"adapter error: {exc}"}

    if ready:
        pool_size = min(
            max(1, _get_review_profile(ctx).findings_batch_concurrency), len(ready)
        )
        with ctx.textual.loading(
            f"Asking {cli_display} to review {len(ready)} batch(es)"
            + (f" ({pool_size} in parallel)…" if pool_size > 1 else "…")
        ):
            if pool_size == 1:
                completed = ((entry[0], _run(entry)) for entry in ready)
                outcomes = list(completed)
            else:
                from concurrent.futures import ThreadPoolExecutor, as_completed

                with ThreadPoolExecutor(max_workers=pool_size) as executor:
                    future_to_batch = {executor.submit(_run, entry): entry[0] for entry in ready}
                    outcomes = [
                        (future_to_batch[future], future.result())
                        for future in as_completed(future_to_batch)
                    ]

        for batch, outcome in outcomes:
            if (
                outcome["status"] == "failed"
                and outcome.get("timed_out")
                and any(entry.worktree_reference for entry in batch.files_context.values())
            ):
                # A timed-out worktree_reference batch means the CLI spent the whole
                # budget exploring a (usually huge) file and reviewed NOTHING. One
                # bounded retry with inline hunks trades depth for guaranteed
                # coverage of the batch's files.
                retried = _retry_timed_out_worktree_batch(ctx, batch, _run, strategy)
                if retried:
                    batch, outcome = retried
            if outcome["status"] == "success":
                batches_succeeded += 1
                reviewed_paths.update(batch.files_context)
                aggregated_raw.extend(outcome["raw"])
                _render_findings_batch_result(
                    ctx,
                    batch.batch_id,
                    status="success",
                    findings_count=len(outcome["raw"]),
                )
            else:
                findings_failed = True
                _render_findings_batch_result(
                    ctx,
                    batch.batch_id,
                    status="failed",
                    detail=outcome["detail"],
                )

    if batches_attempted and not batches_succeeded:
        # Every batch failed or was skipped: an "empty" review here means the AI never
        # ran, not that the code is clean. Publish empty findings so downstream steps
        # (and the worktree cleanup) still run via on_error: continue, but fail the step
        # visibly instead of masquerading as a clean review.
        ctx.data["raw_findings"] = build_default_findings()
        ctx.data["ai_findings_failed"] = True
        logger.error("findings_all_batches_failed", batches_attempted=batches_attempted)
        ctx.textual.error_text(
            f"AI findings failed: 0 of {batches_attempted} batch(es) produced output. "
            "No code was reviewed — do not treat this as a clean review."
        )
        ctx.textual.end_step("error")
        return Error(f"AI findings failed: 0/{batches_attempted} batches produced output")

    if not aggregated_raw and strategy and strategy.suspicious_empty_findings:
        # Empty review on a PR the strategy flagged as suspicious-if-empty: instead of
        # only noting that borderline files went unreviewed, run ONE rescue batch over
        # up to 2 of them (hunks_only, budget-respecting). Rescue findings are the
        # signal that the main candidate selection was too aggressive.
        from ..operations.findings_operations import build_empty_findings_rescue_batch

        candidates = ctx.get("review_candidates", [])
        # "Already reviewed" means a batch actually PRODUCED output for the path — a
        # failed/skipped batch's files are as unreviewed as any borderline candidate.
        borderline_paths = [
            candidate.path for candidate in candidates if candidate.path not in reviewed_paths
        ]
        rescue_batch = (
            build_empty_findings_rescue_batch(
                borderline_paths,
                ctx.get("review_diff", ""),
                ctx.get("review_checklist", []),
                batches[0].pr_manifest if batches else None,
                diff_manager=ctx.get("review_diff_manager"),
            )
            if borderline_paths
            else None
        )
        if rescue_batch:
            rescue_prompt = build_findings_prompt_parts(rescue_batch)["prompt"]
            if len(rescue_prompt) > strategy.max_prompt_chars:
                logger.debug(
                    "rescue_batch_over_budget",
                    prompt_actual_chars=len(rescue_prompt),
                    prompt_budget_target_chars=strategy.max_prompt_chars,
                )
                ctx.textual.dim_text(
                    "No findings from main batches; borderline files remain unreviewed (rescue over budget)."
                )
            else:
                ctx.textual.dim_text(
                    f"No findings from main batches — reviewing {len(rescue_batch.files_context)} "
                    "borderline file(s) as a rescue batch."
                )
                _log_ai_prompt(
                    step_name="ai_review_findings",
                    cli_name=adapter.cli_name.value,
                    prompt=rescue_prompt,
                    batch_id=rescue_batch.batch_id,
                    files_context=len(rescue_batch.files_context),
                    prompt_budget_target_chars=strategy.max_prompt_chars,
                    prompt_actual_chars=len(rescue_prompt),
                )
                _render_findings_batch_started(ctx, rescue_batch)
                with ctx.textual.loading(f"Asking {cli_display} to review the rescue batch…"):
                    rescue_outcome = _run((rescue_batch, rescue_prompt, None))
                if rescue_outcome["status"] == "success":
                    reviewed_paths.update(rescue_batch.files_context)
                    aggregated_raw.extend(rescue_outcome["raw"])
                    _render_findings_batch_result(
                        ctx,
                        rescue_batch.batch_id,
                        status="success",
                        findings_count=len(rescue_outcome["raw"]),
                    )
                    if rescue_outcome["raw"]:
                        # The rescue pass finding real issues means files the scorer
                        # considered borderline held findings — candidate selection was
                        # too aggressive for this PR shape.
                        logger.info(
                            "rescue_batch_found_findings",
                            findings_count=len(rescue_outcome["raw"]),
                            rescued_paths=sorted(rescue_batch.files_context),
                        )
                else:
                    # The rescue pass is best-effort: its failure must not mark an
                    # otherwise-clean review as failed.
                    _render_findings_batch_result(
                        ctx,
                        rescue_batch.batch_id,
                        status="failed",
                        detail=rescue_outcome["detail"],
                    )
        elif borderline_paths:
            ctx.textual.dim_text(
                "No findings from main batches; borderline files remain unreviewed (no diff hunks)."
            )

    # Cross-file synthesis (off by default): per-file batches are structurally blind to
    # interactions between the PR's own changes, so re-combine every reviewed path's
    # hunks into one extra batch that looks ONLY for cross-file inconsistencies. Runs
    # after the rescue block so the rescue's empty-findings gate is unaffected, and
    # best-effort like it: failure never marks the review as failed, and it stays
    # outside the attempted/succeeded counters.
    if _get_review_profile(ctx).findings_synthesis_enabled and strategy:
        from ..operations.findings_operations import (
            FINDINGS_SYNTHESIS_EFFORT,
            SYNTHESIS_INSTRUCTIONS,
            build_cross_file_synthesis_batch,
            dedupe_synthesis_findings,
        )

        # Only paths whose batch actually SUCCEEDED: the synthesis instructions tell
        # the model "single-file issues in these files were already reviewed" — that
        # claim must not cover files whose batch failed or was skipped over budget
        # (their single-file issues would be silently suppressed with no one having
        # looked at them).
        focus_paths = sorted(reviewed_paths)
        synthesis_batch = (
            build_cross_file_synthesis_batch(
                focus_paths,
                ctx.get("review_diff", ""),
                batches[0].pr_manifest if batches else None,
                diff_manager=ctx.get("review_diff_manager"),
            )
            if len(focus_paths) > 1
            else None
        )
        if synthesis_batch:
            synthesis_prompt = build_findings_prompt_parts(
                synthesis_batch, instructions_override=SYNTHESIS_INSTRUCTIONS
            )["prompt"]
            if len(synthesis_prompt) > strategy.max_prompt_chars:
                # No split/degrade machinery for this batch: the whole point is seeing
                # every hunk together, so a partial synthesis is not worth the spend.
                logger.debug(
                    "synthesis_batch_over_budget",
                    prompt_actual_chars=len(synthesis_prompt),
                    prompt_budget_target_chars=strategy.max_prompt_chars,
                )
                ctx.textual.dim_text("Cross-file synthesis skipped (combined hunks over budget).")
            else:
                _log_ai_prompt(
                    step_name="ai_review_findings",
                    cli_name=adapter.cli_name.value,
                    prompt=synthesis_prompt,
                    batch_id=synthesis_batch.batch_id,
                    files_context=len(synthesis_batch.files_context),
                    prompt_budget_target_chars=strategy.max_prompt_chars,
                    prompt_actual_chars=len(synthesis_prompt),
                )
                _render_findings_batch_started(ctx, synthesis_batch)
                synthesis_effort = (
                    FINDINGS_SYNTHESIS_EFFORT if adapter.supports_effort_control else None
                )
                with ctx.textual.loading(
                    f"Asking {cli_display} to run the cross-file synthesis batch…"
                ):
                    synthesis_outcome = _run((synthesis_batch, synthesis_prompt, synthesis_effort))
                if synthesis_outcome["status"] == "success":
                    unique_findings = dedupe_synthesis_findings(
                        synthesis_outcome["raw"], aggregated_raw
                    )
                    aggregated_raw.extend(unique_findings)
                    logger.info(
                        "synthesis_batch_result",
                        findings_count_raw=len(synthesis_outcome["raw"]),
                        findings_count_unique=len(unique_findings),
                        focus_files=len(synthesis_batch.files_context),
                    )
                    _render_findings_batch_result(
                        ctx,
                        synthesis_batch.batch_id,
                        status="success",
                        findings_count=len(unique_findings),
                    )
                else:
                    logger.debug("synthesis_batch_failed", detail=synthesis_outcome["detail"])
                    _render_findings_batch_result(
                        ctx,
                        synthesis_batch.batch_id,
                        status="failed",
                        detail=synthesis_outcome["detail"],
                    )

    ctx.data["raw_findings"] = aggregated_raw or build_default_findings()
    ctx.data["ai_findings_failed"] = findings_failed
    ctx.textual.success_text(f"✓ AI returned {len(ctx.data['raw_findings'])} raw finding(s)")
    if findings_failed:
        ctx.textual.warning_text("Some findings batches failed or were skipped due to budget limits.")
    ctx.textual.end_step("success")
    return Success(
        "AI findings retrieved",
        metadata={
            "ai_findings_failed": findings_failed,
        },
    )


def normalize_findings(ctx: WorkflowContext) -> WorkflowResult:
    """
    Parse and validate raw AI output into Finding models.

    Accepts raw_findings as either a JSON string or a list of dicts.
    Each item is validated as a Finding model. Invalid items are skipped
    with a warning rather than failing the entire step.

    Requires (from ctx.data):
        raw_findings (list | str): Raw AI output from ai_review_findings

    Outputs (saved to ctx.data):
        normalized_findings (List[Finding]): Validated Finding objects

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Normalize Findings")

    raw = ctx.get("raw_findings")

    if raw is None:
        ctx.textual.error_text("No raw_findings in context (run ai_review_findings first)")
        ctx.textual.end_step("error")
        return Error("No raw_findings in context (run ai_review_findings first)")

    from ..models.review_models import Finding
    from pydantic import ValidationError
    import json

    # Parse JSON string if needed
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            ctx.textual.error_text(f"Failed to parse raw_findings JSON: {e}")
            ctx.textual.end_step("error")
            return Error(f"Failed to parse raw_findings JSON: {e}")

    if not isinstance(raw, list):
        ctx.textual.error_text(f"raw_findings must be a list, got {type(raw).__name__}")
        ctx.textual.end_step("error")
        return Error(f"raw_findings must be a list, got {type(raw).__name__}")

    findings: list[Finding] = []
    skipped = 0

    for i, item in enumerate(raw):
        try:
            findings.append(Finding.model_validate(item))
        except ValidationError as e:
            skipped += 1
            ctx.textual.dim_text(f"⚠ Finding {i + 1} invalid, skipping: {e.error_count()} error(s)")
            logger.debug("Finding %d validation error: %s", i + 1, e)

    ctx.data["normalized_findings"] = findings

    summary = f"✓ {len(findings)} finding(s) normalized"
    if skipped:
        summary += f" ({skipped} skipped)"
    ctx.textual.success_text(summary)
    ctx.textual.end_step("success")
    return Success("Findings normalized")


def dedupe_findings(ctx: WorkflowContext) -> WorkflowResult:
    """
    Remove findings that duplicate existing PR comments.

    Uses the is_duplicate() validator to compare each finding against the
    existing_comments_index. A finding is a duplicate if it targets the same
    file, the same area (within 5 lines), and the same topic (same category
    or similar title).

    Requires (from ctx.data):
        normalized_findings (List[Finding])
        existing_comments_index (List[ExistingCommentIndexEntry])

    Outputs (saved to ctx.data):
        deduped_findings (List[Finding]): Findings after duplicate removal

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Deduplicate Findings")

    findings = ctx.get("normalized_findings")
    existing_index = ctx.get("existing_comments_index", [])

    if findings is None:
        ctx.textual.error_text("No normalized_findings in context (run normalize_findings first)")
        ctx.textual.end_step("error")
        return Error("No normalized_findings in context (run normalize_findings first)")

    from ..models.validators import is_duplicate

    deduped: list = []
    removed = 0
    removed_existing = 0
    seen_keys: set[tuple[str, int | None, str]] = set()

    for finding in findings:
        is_dup = any(is_duplicate(finding, ex) for ex in existing_index)
        key = (finding.path, finding.line, finding.title.lower())
        if is_dup or key in seen_keys:
            removed += 1
            if is_dup:
                removed_existing += 1
            logger.debug("Deduplicated finding: %s @ %s:%s", finding.title, finding.path, finding.line)
        else:
            deduped.append(finding)
            seen_keys.add(key)

    deduped, collapsed = _collapse_derived_findings(deduped)
    removed += collapsed

    ctx.data["deduped_findings"] = deduped

    summary = f"✓ {len(deduped)} finding(s) ready"
    if removed:
        # Say WHY findings were dropped: "already commented on the PR" explains why a
        # re-run reports different things than the first pass — "duplicates removed"
        # does not.
        if removed_existing:
            summary += f" ({removed_existing} skipped: already commented on this PR"
            if removed > removed_existing:
                summary += f"; {removed - removed_existing} internal duplicate(s)"
            summary += ")"
        else:
            summary += f" ({removed} internal duplicate(s) removed)"
    ctx.textual.success_text(summary)
    logger.debug(
        "findings_deduplicated",
        deduped_findings_count=len(deduped),
        findings_removed_due_to_existing_threads=removed_existing,
        findings_removed_due_to_adjudicated_threads=sum(
            1 for finding in findings for ex in existing_index if ex.is_adjudicated and is_duplicate(finding, ex)
        ),
    )
    ctx.textual.end_step("success")
    return Success("Findings deduplicated", metadata={"deduped_findings_count": len(deduped)})


def verify_findings(ctx: WorkflowContext) -> WorkflowResult:
    """
    Adversarial verification pass: try to REFUTE each finding before the human gate.

    One batched AI call (effort low, structured output, same adapter infra as
    ai_review_findings) receives all non-nit findings plus the focused hunks they
    refer to, and judges each as confirmed/refuted/uncertain. Findings refuted with
    evidence are dropped (and shown, with the refutation reasoning); everything else
    passes through. Fail-open: any CLI/parse/budget problem keeps all findings.

    Generalizes the retired `_looks_like_contradicted_api_claim` heuristic.
    Gated by ReviewProfile.findings_verification_enabled (default True).

    Requires (from ctx.data):
        deduped_findings (List[Finding])
        review_context_batches (List[FocusContextBatch])
        review_strategy (ReviewStrategy)
        cli_preference (str)

    Outputs (saved to ctx.data):
        deduped_findings (List[Finding]): verified set, refuted findings removed
        refuted_findings (List[Finding]): findings dropped by this pass

    Returns:
        Success or Skip
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Verify Findings")

    findings = ctx.get("deduped_findings")
    if findings is None:
        ctx.textual.error_text("No deduped_findings in context (run dedupe_findings first)")
        ctx.textual.end_step("error")
        return Error("No deduped_findings in context (run dedupe_findings first)")

    if not findings:
        ctx.textual.dim_text("No findings to verify.")
        ctx.textual.end_step("skip")
        return Skip("No findings to verify")

    profile = _get_review_profile(ctx)
    if not profile.findings_verification_enabled:
        ctx.textual.dim_text("Findings verification disabled by review profile.")
        ctx.textual.end_step("skip")
        return Skip("Verification disabled by review profile")

    from ..operations.findings_operations import FINDINGS_DISALLOWED_TOOLS
    from ..operations.verification_operations import (
        VERIFICATION_EFFORT,
        VERIFICATION_TIMEOUT_SECONDS,
        apply_verification_verdicts,
        build_verification_code_map,
        build_verification_prompt_parts,
        parse_verification_response,
        select_findings_for_verification,
        summarize_verification_prompt_parts,
        verification_json_schema,
    )

    to_verify, exempt = select_findings_for_verification(findings)
    if not to_verify:
        ctx.textual.dim_text("Only nit-severity findings — skipping verification.")
        ctx.textual.end_step("skip")
        return Skip("No findings eligible for verification")

    adapter = _resolve_headless_adapter(ctx.data.get("cli_preference", "auto"))
    if not adapter:
        ctx.textual.dim_text("No headless CLI available — findings pass unverified.")
        ctx.textual.end_step("skip")
        return Skip("No CLI available for verification")

    strategy = ctx.get("review_strategy")
    batches = ctx.get("review_context_batches", [])
    project_root = ctx.data.get("worktree_path") or ctx.data.get("project_root")

    code_map = build_verification_code_map(to_verify, batches)
    prompt_parts = build_verification_prompt_parts(to_verify, code_map)
    prompt = prompt_parts["prompt"]

    max_prompt_chars = strategy.max_prompt_chars if strategy else None
    if max_prompt_chars and len(prompt) > max_prompt_chars:
        # Fail-open on budget too: verification is an optional quality filter, never
        # worth degrading or splitting like the findings pass.
        logger.warning(
            "verification_prompt_over_budget",
            prompt_actual_chars=len(prompt),
            prompt_budget_target_chars=max_prompt_chars,
        )
        ctx.textual.dim_text(
            f"Verification prompt too large ({len(prompt)} chars) — findings pass unverified."
        )
        ctx.textual.end_step("skip")
        return Skip("Verification prompt over budget")

    use_structured_output = adapter.supports_structured_output
    disallowed_tools = list(FINDINGS_DISALLOWED_TOOLS) if adapter.supports_tool_restriction else None
    effort = VERIFICATION_EFFORT if adapter.supports_effort_control else None
    cli_display = adapter.cli_name.value.capitalize()

    _log_ai_prompt(
        step_name="verify_findings",
        cli_name=adapter.cli_name.value,
        prompt=prompt,
        findings_to_verify=len(to_verify),
        findings_exempt=len(exempt),
        prompt_actual_chars=len(prompt),
        effort=effort,
        **summarize_verification_prompt_parts(prompt_parts),
    )
    adapter_started_at = time.monotonic()
    with ctx.textual.loading(f"Asking {cli_display} to verify {len(to_verify)} finding(s)…"):
        response = adapter.execute(
            prompt,
            cwd=project_root,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
            json_schema=verification_json_schema() if use_structured_output else None,
            disallowed_tools=disallowed_tools,
            effort=effort,
        )
    adapter_duration_seconds = time.monotonic() - adapter_started_at
    _log_ai_response(
        step_name="verify_findings",
        cli_name=adapter.cli_name.value,
        stdout=response.stdout,
        stderr=response.stderr,
        exit_code=response.exit_code,
        duration_seconds=round(adapter_duration_seconds, 3),
        findings_to_verify=len(to_verify),
    )

    if not response.succeeded:
        logger.warning("verification_call_failed", exit_code=response.exit_code)
        ctx.textual.warning_text(
            f"Verification call failed (exit {response.exit_code}) — findings pass unverified."
        )
        ctx.textual.end_step("skip")
        return Skip("Verification call failed")

    match parse_verification_response(response.stdout, structured=use_structured_output):
        case ClientSuccess(data=raw_verdicts) if isinstance(raw_verdicts, list):
            pass
        case _:
            logger.warning("verification_parse_failed")
            ctx.textual.warning_text("Could not parse verification response — findings pass unverified.")
            ctx.textual.end_step("skip")
            return Skip("Verification response unparseable")

    # Truthy contents only — the prompt builder treats an empty block as "no code
    # available", so the refutation guard must agree with it.
    outcome = apply_verification_verdicts(
        findings,
        to_verify,
        raw_verdicts,
        paths_with_code={path for path, content in code_map.items() if content},
    )
    ctx.data["deduped_findings"] = outcome.kept
    ctx.data["refuted_findings"] = outcome.refuted

    logger.info(
        "findings_verification_applied",
        findings_in=len(findings),
        verified=len(to_verify),
        exempt_nits=len(exempt),
        refuted=len(outcome.refuted),
        kept=len(outcome.kept),
        duration_seconds=round(adapter_duration_seconds, 3),
    )
    for finding, reason in zip(outcome.refuted, outcome.refuted_reasons):
        ctx.textual.dim_text(
            f"✗ Refuted: {finding.title} @ {finding.path}:{finding.line} — {reason[:200]}"
        )
    summary = f"✓ {len(outcome.kept)} finding(s) verified"
    if outcome.refuted:
        summary += f" ({len(outcome.refuted)} refuted and dropped)"
    ctx.textual.success_text(summary)
    ctx.textual.end_step("success")
    return Success(
        "Findings verified",
        metadata={
            "deduped_findings": outcome.kept,
            "refuted_findings": outcome.refuted,
        },
    )


# ============================================================================
# PHASE 5: UI + SUBMIT
# ============================================================================


def build_new_comment_actions(ctx: WorkflowContext) -> WorkflowResult:
    """
    Convert deduplicated findings into ReviewActionProposal objects.

    Requires (from ctx.data):
        deduped_findings (List[Finding])

    Outputs (saved to ctx.data):
        review_action_proposals (List[ReviewActionProposal])

    Returns:
        Success or Skip (no findings)
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Comment Actions")

    findings = ctx.get("deduped_findings", [])
    manifest = ctx.get("change_manifest")
    batches = ctx.get("review_context_batches", [])

    if not findings:
        ctx.textual.dim_text("No findings to convert into actions.")
        ctx.textual.end_step("skip")
        return Skip("No findings to submit")

    actions = build_new_comment_actions_operation(findings)
    manifest_files = {file.path: file for file in getattr(manifest, "files", [])}
    read_modes = {
        path: entry.read_mode.value if entry.read_mode else None
        for batch in batches or []
        for path, entry in batch.files_context.items()
    }
    enriched_actions = []
    for action in actions:
        file_entry = manifest_files.get(action.path)
        enriched_actions.append(
            action.model_copy(
                update={
                    "file_status": str(file_entry.status) if file_entry else None,
                    "is_test_file": bool(file_entry.is_test) if file_entry else False,
                    "read_mode": read_modes.get(action.path),
                }
            )
        )
    actions = enriched_actions
    ctx.data["review_action_proposals"] = actions

    ctx.textual.success_text(f"✓ {len(actions)} action(s) ready for review")
    ctx.textual.end_step("success")
    return Success("Actions built")


def _release_review_worktree(ctx: WorkflowContext) -> None:
    """Remove the review worktree as soon as nothing will read from it again.

    The workflow's final cleanup step only runs when the workflow reaches it —
    abandoning the review at an interactive gate (exit button, quitting the app at
    the submit prompt) used to leave the worktree on disk. Failure here is fine:
    the final cleanup step remains as backstop.
    """
    if not ctx.get("worktree_created") or not ctx.get("worktree_path") or not ctx.git:
        return
    from ..operations import cleanup_worktree as cleanup_worktree_operation

    if cleanup_worktree_operation(ctx.git, ctx.data["worktree_path"]):
        ctx.textual.dim_text("Review worktree removed (no longer needed).")
        ctx.data["worktree_created"] = False
        ctx.data["worktree_path"] = None
    else:
        logger.warning("early_worktree_release_failed", worktree_path=ctx.data.get("worktree_path"))


def validate_review_actions(ctx: WorkflowContext) -> WorkflowResult:
    """
    Present each ReviewActionProposal to the user for approval, editing, or skipping.

    Requires (from ctx.data):
        review_action_proposals (List[ReviewActionProposal])

    Optional (from ctx.data):
        review_diff (str): Full PR diff for extracting diff context per comment

    Outputs (saved to ctx.data):
        approved_action_proposals (List[ReviewActionProposal])

    Returns:
        Success, Skip (none approved), or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Validate & Approve Actions")

    actions: List[ReviewActionProposal] = ctx.get("review_action_proposals", [])

    if not actions:
        ctx.textual.dim_text("No actions to validate.")
        _release_review_worktree(ctx)
        ctx.textual.end_step("skip")
        return Skip("No actions to validate")

    diff = ctx.get("review_diff", "")
    review_threads: List[UICommentThread] = ctx.get("review_threads", [])
    diff_manager = ctx.get("review_diff_manager")

    # Sort by severity: blocking → important → nit
    severity_order = {"blocking": 0, "important": 1, "nit": 2}
    resolved_actions = resolve_action_anchors(actions, diff, diff_manager=diff_manager)

    sorted_actions = sorted(
        resolved_actions,
        key=lambda a: severity_order.get(a.severity.value if a.severity else "", 99),
    )

    # Precompute every action's code context NOW: anchors are resolved and the diff
    # hunks / file excerpts below are the last reads from the worktree. Releasing it
    # before the interactive loop means abandoning the review mid-gate (exit button,
    # quitting the app at the submit prompt) can no longer leave a stale worktree —
    # the final cleanup_worktree step becomes a no-op backstop.
    prepared: List[tuple] = []
    for action in sorted_actions:
        diff_hunk = extract_diff_hunk_for_action(action, diff, diff_manager=diff_manager)
        # Unanchored findings have no diff hunk by definition — read the real file so the
        # user judges the finding against its code instead of a bare assertion.
        file_excerpt = extract_file_excerpt_for_action(action, diff_manager=diff_manager)
        prepared.append((action, diff_hunk, file_excerpt))
    _release_review_worktree(ctx)

    approved: List[ReviewActionProposal] = []
    skipped = 0
    exit_requested = False

    for idx, (action, diff_hunk, file_excerpt) in enumerate(prepared):
        if exit_requested:
            break

        current = action

        while True:
            choice = _show_review_action_and_get_decision(
                ctx, current, diff_hunk or "", idx, len(sorted_actions),
                review_threads=review_threads,
                file_excerpt=file_excerpt,
            )

            if choice == "exit":
                exit_requested = True
                ctx.textual.warning_text(
                    f"Exiting validation. Approved {len(approved)}, skipped {skipped}."
                )
                break

            elif choice == "approve":
                approved.append(current)
                break

            elif choice == "edit":
                ctx.textual.text("")
                new_body = ctx.textual.ask_multiline(
                    "Edit the review comment:",
                    default=current.body,
                )
                if new_body and new_body.strip():
                    approved.append(current.model_copy(update={"body": new_body.strip()}))
                else:
                    ctx.textual.warning_text("Empty body, comment skipped")
                    skipped += 1
                break

            else:  # skip
                skipped += 1
                break

    if not approved:
        ctx.textual.dim_text("No actions approved.")
        ctx.textual.end_step("skip")
        return Skip("No approved review actions")

    ctx.textual.success_text(f"✓ {len(approved)} action(s) approved, {skipped} skipped")
    ctx.textual.end_step("success")
    return Success(
        f"{len(approved)} action(s) approved",
        metadata={"approved_action_proposals": approved},
    )


def _detect_submit_time_sha_drift(ctx: WorkflowContext, pr_number: int, reviewed_sha: str):
    """
    Re-read the PR's head SHA and compare it with the one the review was prepared against.

    The bundle's SHA is captured minutes earlier, before the user inspects findings. A push
    in that window invalidates every resolved line, so this is checked at submit time
    rather than trusted from the bundle.
    """
    from ..operations.review_action_operations import detect_head_sha_drift

    current_sha = ""
    match ctx.github.get_pr_commit_sha(pr_number):
        case ClientSuccess(data=sha):
            current_sha = (sha or "").strip()
        case ClientError(error_message=err):
            # Unverifiable is not the same as drifted: the publish gate still validates
            # every line against the diff, so proceed rather than block the submission.
            logger.debug("submit_sha_recheck_failed", pr_number=pr_number, error=err)

    drift = detect_head_sha_drift(reviewed_sha, current_sha)
    logger.debug(
        "submit_sha_drift_check",
        pr_number=pr_number,
        reviewed_sha=drift.reviewed_sha,
        current_sha=drift.current_sha,
        drifted=drift.drifted,
    )
    return drift


def submit_review_actions(ctx: WorkflowContext) -> WorkflowResult:
    """
    Submit approved ReviewActionProposal objects to GitHub.

    Handles resolve_thread actions directly, then submits new_comment and
    reply_to_thread actions as a GitHub draft review.

    Requires (from ctx.data):
        approved_action_proposals (List[ReviewActionProposal])
        review_pr_number (int)

    Optional (from ctx.data):
        review_commit_sha (str): Head commit SHA (fetched if missing)
        review_diff (str): Full PR diff for inline comment validation

    Returns:
        Success, Skip (no approved actions), or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Submit Review")

    approved: List[ReviewActionProposal] = ctx.get("approved_action_proposals", [])
    pr_number = ctx.get("review_pr_number")
    commit_sha = ctx.get("review_commit_sha", "")
    diff = ctx.get("review_diff", "")
    diff_manager = ctx.get("review_diff_manager")

    if not pr_number:
        ctx.textual.error_text("No PR number in context")
        ctx.textual.end_step("error")
        return Error("No PR number in context")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    if not approved:
        ctx.textual.dim_text("No approved actions — you can still submit a review decision.")

    # Handle thread actions first (direct API, outside the review draft)
    resolve_actions = [a for a in approved if a.action_type == ReviewActionType.RESOLVE_THREAD]
    reply_actions = [a for a in approved if a.action_type == ReviewActionType.REPLY_TO_THREAD]
    comment_actions = [a for a in approved if a.action_type == ReviewActionType.NEW_COMMENT]

    for action in resolve_actions:
        if not action.thread_id:
            continue
        with ctx.textual.loading("Resolving thread..."):
            result = ctx.github.resolve_review_thread(action.thread_id)
        match result:
            case ClientSuccess():
                ctx.textual.success_text("✓ Thread resolved")
            case ClientError(error_message=err):
                ctx.textual.warning_text(f"Could not resolve thread: {err}")

    for action in reply_actions:
        if not action.comment_id or not pr_number:
            continue
        with ctx.textual.loading("Posting reply to comment..."):
            result = ctx.github.reply_to_comment(pr_number, action.comment_id, action.body)
        match result:
            case ClientSuccess():
                ctx.textual.success_text("✓ Reply posted")
            case ClientError(error_message=err):
                ctx.textual.warning_text(f"Could not post reply: {err}")

    # Get commit SHA if not available (needed for inline comments)
    if not commit_sha and comment_actions:
        with ctx.textual.loading("Fetching latest commit SHA..."):
            sha_result = ctx.github.get_pr_commit_sha(pr_number)
        match sha_result:
            case ClientSuccess(data=sha):
                commit_sha = sha
            case ClientError(error_message=err):
                ctx.textual.error_text("No commit SHA available — cannot submit inline comments")
                ctx.textual.end_step("error")
                return Error(f"Missing commit SHA for inline review: {err}")

    # The anchors were resolved against commit_sha's diff. If the PR has been pushed to
    # since, every inline line describes code that moved — degrade them to the review body
    # rather than publish comments on the wrong lines.
    force_general_body = False
    if comment_actions:
        drift = _detect_submit_time_sha_drift(ctx, pr_number, commit_sha)
        if drift.drifted:
            ctx.textual.warning_text(f"⚠ PR head changed: {drift.message}")
            ctx.textual.dim_text(
                f"reviewed: {drift.reviewed_sha[:8]} · current: {drift.current_sha[:8]}"
            )
            ctx.textual.text(
                f"The {len(comment_actions)} comment(s) will go in the review body instead "
                "of inline, since their line numbers no longer match the PR's diff."
            )
            if not ctx.textual.ask_confirm("Publish the review anyway?", default=True):
                ctx.textual.warning_text("Review cancelled")
                ctx.textual.end_step("skip")
                return Skip("User cancelled after head SHA drift")
            force_general_body = True

    # Show AI's opinion and prepare action options
    ctx.textual.text("")
    if comment_actions:
        ctx.textual.text(f"📋 Found {len(comment_actions)} issue(s) to address")
        ctx.textual.text(f"Ready to submit {len(comment_actions)} comment(s) on PR #{pr_number}")
        ctx.textual.text("")

        # With findings - offer Comment or Request Changes
        event_options = [
            OptionItem(value="COMMENT", title="💬 Comment", description="Post comments without approval decision"),
            OptionItem(value="REQUEST_CHANGES", title="🔴 Request Changes", description="Block merge until changes are made"),
        ]
    else:
        ctx.textual.success_text("✅ No issues found - PR looks good and can be approved")
        ctx.textual.text("")

        # No findings - offer all options
        event_options = [
            OptionItem(value="APPROVE", title="✅ Approve", description="Approve the PR"),
            OptionItem(value="COMMENT", title="💬 Comment", description="Post a general comment"),
            OptionItem(value="REQUEST_CHANGES", title="🔴 Request Changes", description="Block merge until changes are made"),
        ]

    try:
        event = ctx.textual.ask_option("Select review type:", event_options)
    except Exception as e:
        ctx.textual.error_text(str(e))
        ctx.textual.end_step("error")
        return Error(str(e))

    if not event:
        ctx.textual.warning_text("Review cancelled")
        ctx.textual.end_step("skip")
        return Skip("User cancelled review submission")

    # Optional general body
    add_body = ctx.textual.ask_confirm("Add a general review comment (optional)?", default=False)
    review_body = ""
    if add_body:
        review_body = ctx.textual.ask_multiline("General review comment:", default="")

    # Build payload from comment actions
    payload = build_review_action_payload(
        comment_actions,
        commit_sha,
        diff,
        diff_manager=diff_manager,
        force_general_body=force_general_body,
    )

    if review_body and review_body.strip():
        existing_body = payload.get("body", "")
        payload["body"] = (existing_body + "\n\n" + review_body.strip()).strip()

    has_inline_comments = bool(payload.get("comments"))
    has_body = bool(payload.get("body"))
    is_empty_payload = not has_inline_comments and not has_body
    # Human label for the GitHub review event ('COMMENT'/'APPROVE'/'REQUEST_CHANGES').
    event_labels = {
        "COMMENT": "Comment",
        "APPROVE": "Approve",
        "REQUEST_CHANGES": "Request Changes",
    }
    event_label = event_labels.get(event, event)

    if is_empty_payload:
        ctx.textual.dim_text("Submitting review without comments...")
        with ctx.textual.loading("Submitting review..."):
            submit_result = ctx.github.submit_review(pr_number, None, event, "")
        match submit_result:
            case ClientSuccess():
                ctx.textual.success_text(f"✓ Review submitted ({event_label}) on PR #{pr_number}")
                ctx.textual.end_step("success")
                return Success(f"Review submitted on PR #{pr_number}")
            case ClientError(error_message=err, error_code="PENDING_REVIEW_EXISTS"):
                ctx.textual.warning_text(err)
                ctx.textual.end_step("error")
                return Error(err)
            case ClientError(error_message=err):
                ctx.textual.error_text(f"Failed to submit review: {err}")
                ctx.textual.end_step("error")
                return Error(f"Failed to submit review: {err}")

    with ctx.textual.loading("Creating review..."):
        draft_result = ctx.github.create_draft_review(pr_number, payload)

    match draft_result:
        case ClientSuccess(data=review_id):
            ctx.textual.success_text(f"✓ Review #{review_id} created")
        case ClientError(error_message=err):
            logger.error(
                "draft_review_creation_failed",
                pr_number=pr_number,
                error=err,
                inline_comment_count=len(payload.get("comments", [])),
            )
            if payload.get("comments"):
                ctx.textual.warning_text(
                    "GitHub rejected the review — checking which comments it will accept…"
                )
                filtered_payload, rejected_comments = _filter_invalid_inline_comments(ctx, pr_number, payload)
                if rejected_comments:
                    rejection_breakdown: dict[str, int] = {}
                    for comment in rejected_comments:
                        kind = classify_github_review_rejection(comment.get("error", ""))
                        rejection_breakdown[kind] = rejection_breakdown.get(kind, 0) + 1
                    ctx.textual.warning_text(
                        f"⚠ {len(rejected_comments)} comment(s) can't be placed inline and will be "
                        "left out:"
                    )
                    for comment in rejected_comments:
                        ctx.textual.dim_text(
                            f"  {comment.get('path')}:{comment.get('line')}"
                        )
                    logger.debug(
                        "inline_comments_filtered_after_422",
                        pr_number=pr_number,
                        inline_candidates_total=len(payload.get("comments", [])),
                        inline_candidates_validated=len(filtered_payload.get("comments", [])),
                        inline_candidates_rejected=len(rejected_comments),
                        inline_submit_success_rate=(
                            len(filtered_payload.get("comments", [])) / len(payload.get("comments", []))
                            if payload.get("comments")
                            else 0.0
                        ),
                        rejected_count=len(rejected_comments),
                        valid_count=len(filtered_payload.get("comments", [])),
                        rejection_breakdown=rejection_breakdown,
                    )
                    if filtered_payload.get("comments") or filtered_payload.get("body"):
                        payload = filtered_payload
                        with ctx.textual.loading("Retrying review creation with valid comments only..."):
                            retry_result = ctx.github.create_draft_review(pr_number, payload)
                        match retry_result:
                            case ClientSuccess(data=review_id):
                                ctx.textual.success_text(
                                    f"✓ Review #{review_id} created without the rejected comment(s)"
                                )
                            case ClientError(error_message=retry_err):
                                ctx.textual.error_text(f"Failed to create review: {retry_err}")
                                ctx.textual.end_step("error")
                                return Error(f"Failed to create draft review: {retry_err}")
                    else:
                        ctx.textual.error_text(f"Failed to create review: {err}")
                        ctx.textual.end_step("error")
                        return Error(f"Failed to create draft review: {err}")
                else:
                    ctx.textual.error_text(f"Failed to create review: {err}")
                    ctx.textual.end_step("error")
                    return Error(f"Failed to create draft review: {err}")
            else:
                ctx.textual.error_text(f"Failed to create review: {err}")
                ctx.textual.end_step("error")
                return Error(f"Failed to create draft review: {err}")

    with ctx.textual.loading("Submitting review..."):
        submit_result = ctx.github.submit_review(
            pr_number, review_id, event, payload.get("body", "")
        )

    match submit_result:
        case ClientSuccess():
            ctx.textual.success_text(
                f"✓ Review submitted ({event_label}) on PR #{pr_number}"
                + (f" with {len(comment_actions)} comment(s)" if comment_actions else "")
            )
            ctx.textual.end_step("success")
            return Success(f"Review submitted on PR #{pr_number}")
        case ClientError(error_message=err, error_code="PENDING_REVIEW_EXISTS"):
            ctx.textual.warning_text(err)
            ctx.textual.end_step("error")
            return Error(err)
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to submit review: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to submit review: {err}")


# ============================================================================
# PHASE 6: THREAD RESOLUTION PIPELINE
# ============================================================================


def build_thread_review_candidates(ctx: WorkflowContext) -> WorkflowResult:
    """
    Select open inline threads worth AI analysis.

    Filters out:
    - General comments (no GraphQL resolve API)
    - Already-resolved threads
    - Threads where the PR author has not replied (reviewer is waiting for response)

    Only includes threads where the last comment is from the PR author,
    indicating they have responded to the review.

    Requires (from ctx.data):
        review_threads (List[UICommentThread]): Unresolved inline review threads
        review_pr (UIPullRequest): PR object with author info
        review_current_user (str): GitHub login running Titan

    Outputs (saved to ctx.data):
        thread_review_candidates (List[ThreadReviewCandidate])

    Returns:
        Success, Skip (no candidates), or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Thread Review Candidates")

    threads = ctx.get("review_threads", [])
    pr = ctx.get("review_pr")
    review_current_user = ctx.get("review_current_user")

    if not pr:
        ctx.textual.dim_text("No PR info available")
        ctx.textual.end_step("skip")
        return Skip("No PR data in context")

    if not review_current_user:
        ctx.textual.error_text("Current GitHub user not available")
        ctx.textual.end_step("error")
        return Error("Current GitHub user not available")

    candidates = build_thread_review_candidates_operation(
        threads,
        pr.author_name,
        review_current_user,
    )

    if not candidates:
        if not threads:
            ctx.textual.dim_text("No open inline threads on this PR")
        else:
            ctx.textual.dim_text(
                f"No open threads created by @{review_current_user} with author replies yet"
            )
        ctx.textual.end_step("skip")
        return Skip("No threads to review")

    ctx.data["thread_review_candidates"] = candidates
    ctx.textual.success_text(
        f"✓ {len(candidates)} thread(s) created by @{review_current_user} with author replies selected"
    )
    ctx.textual.end_step("success")
    return Success("Thread candidates built", metadata={"thread_review_candidates_count": len(candidates)})


def build_thread_review_contexts(ctx: WorkflowContext) -> WorkflowResult:
    """
    Enrich thread candidates with diff hunk context and full reply history.

    For each candidate, extracts the diff hunk near the commented line,
    collects all replies from the full UICommentThread object, and attaches
    remote context for commit SHAs referenced in those replies.

    Requires (from ctx.data):
        thread_review_candidates (List[ThreadReviewCandidate])
        review_threads (List[UICommentThread]): For extracting reply history
        review_diff (str): Full PR unified diff

    Requires:
        ctx.github: Optional GitHub client used to inspect referenced commits.

    Outputs (saved to ctx.data):
        thread_review_contexts (List[ThreadReviewContext])

    Returns:
        Success, Skip (no candidates), or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Thread Review Contexts")

    candidates = ctx.get("thread_review_candidates")
    threads = ctx.get("review_threads", [])
    diff = ctx.get("review_diff", "")

    if not candidates:
        ctx.textual.dim_text("No thread candidates available")
        ctx.textual.end_step("skip")
        return Skip("No thread_review_candidates in context")

    contexts = build_thread_review_contexts_operation(candidates, threads, diff)
    candidate_ids = {candidate.thread_id for candidate in candidates}
    candidate_threads = [thread for thread in threads if thread.thread_id in candidate_ids]
    review_pr = ctx.get("review_pr")
    commit_contexts_by_thread = _load_referenced_commit_contexts(ctx, candidate_threads, review_pr)
    if commit_contexts_by_thread:
        contexts = [
            context.model_copy(
                update={
                    "referenced_commits": commit_contexts_by_thread.get(
                        context.thread_id,
                        [],
                    )
                }
            )
            for context in contexts
        ]

    ctx.data["thread_review_contexts"] = contexts
    referenced_commit_count = sum(len(context.referenced_commits) for context in contexts)
    summary = f"✓ {len(contexts)} thread context(s) built"
    if referenced_commit_count:
        summary += f" ({referenced_commit_count} referenced commit context(s))"
    ctx.textual.success_text(summary)
    ctx.textual.end_step("success")
    return Success("Thread contexts built", metadata={"thread_review_contexts_count": len(contexts)})


def ai_thread_resolution(ctx: WorkflowContext) -> WorkflowResult:
    """
    AI call: decide what to do with each open thread.

    Splits thread contexts into prompt-budget-bound batches (see
    batch_thread_review_contexts) and sends each batch — original comment +
    replies + current code + referenced commits, all untouched — to the
    selected headless CLI. The AI decides per thread: resolved / insist /
    reply / skip. Batches run sequentially and their decisions are aggregated;
    a batch that fails (CLI error or parse error) is skipped without aborting
    the remaining batches.

    On total failure (no batch produced usable output), falls back to empty
    decisions (no actions).

    Requires (from ctx.data):
        thread_review_contexts (List[ThreadReviewContext])
        cli_preference (str): "claude" | "gemini" | "codex" | "auto"

    Outputs (saved to ctx.data):
        raw_thread_decisions (list): Raw AI output aggregated across batches, before normalization

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("AI Thread Resolution")

    contexts = ctx.get("thread_review_contexts")
    cli_preference = ctx.data.get("cli_preference", "auto")
    project_root = ctx.data.get("project_root")

    if not contexts:
        ctx.textual.dim_text("No thread contexts available")
        ctx.textual.end_step("skip")
        return Skip("No thread_review_contexts in context")

    adapter = _resolve_headless_adapter(cli_preference)

    if not adapter:
        ctx.textual.warning_text("No headless CLI available — skipping AI thread resolution")
        ctx.data["raw_thread_decisions"] = []
        ctx.textual.end_step("success")
        return Success("No decisions (no CLI available)", metadata={"raw_thread_decisions": []})

    # Split into batches so one call never has to carry every open thread at
    # once — each thread's full conversation/hunk/commit context stays intact,
    # only the number of threads sharing a single AI call is bounded.
    batches = batch_thread_review_contexts(contexts)
    cli_display = adapter.cli_name.value.capitalize()
    ctx.textual.dim_text(
        f"Reviewing {len(contexts)} thread(s) in {len(batches)} batch(es) with {cli_display}"
    )

    aggregated_raw: list = []
    any_batch_failed = False

    for batch_index, batch in enumerate(batches, start=1):
        batch_label = f"batch {batch_index}/{len(batches)}"
        prompt = build_thread_resolution_prompt(batch)

        _log_ai_prompt(
            step_name="ai_thread_resolution",
            cli_name=adapter.cli_name.value,
            prompt=prompt,
            batch_index=batch_index,
            batch_count=len(batches),
            thread_count=len(batch),
        )

        adapter_started_at = time.monotonic()
        with ctx.textual.loading(
            f"Asking {cli_display} to analyse {batch_label} ({len(batch)} thread(s))…"
        ):
            response = adapter.execute(prompt, cwd=project_root, timeout=300)
        adapter_duration_seconds = time.monotonic() - adapter_started_at
        logger.info(
            "thread_resolution_adapter_call",
            cli=adapter.cli_name.value,
            batch_index=batch_index,
            batch_count=len(batches),
            thread_count=len(batch),
            prompt_actual_chars=len(prompt),
            duration_seconds=round(adapter_duration_seconds, 3),
            exit_code=response.exit_code,
            timed_out=response.exit_code == 124,
        )
        _log_ai_response(
            step_name="ai_thread_resolution",
            cli_name=adapter.cli_name.value,
            stdout=response.stdout,
            stderr=response.stderr,
            exit_code=response.exit_code,
            batch_index=batch_index,
            batch_count=len(batches),
        )

        if not response.succeeded:
            any_batch_failed = True
            ctx.textual.warning_text(f"{batch_label}: CLI call failed (exit {response.exit_code}) — skipped")
            if response.stderr:
                ctx.textual.dim_text(response.stderr[:200])
            continue

        match extract_json_payload(response.stdout, kind="array"):
            case ClientError(error_message=err):
                any_batch_failed = True
                ctx.textual.warning_text(f"{batch_label}: decisions parsing failed ({err}) — skipped")
                continue
            case ClientSuccess(data=raw):
                aggregated_raw.extend(raw)

    ctx.data["raw_thread_decisions"] = aggregated_raw

    if not aggregated_raw:
        status = "No decisions (all batches failed)" if any_batch_failed else "No decisions"
        ctx.textual.warning_text(status)
        ctx.textual.end_step("success")
        return Success(status, metadata={"raw_thread_decisions": []})

    summary = f"✓ AI returned {len(aggregated_raw)} thread decision(s)"
    if any_batch_failed:
        summary += " (some batches failed — partial results)"
    ctx.textual.success_text(summary)
    ctx.textual.end_step("success")
    return Success(
        "AI thread decisions retrieved",
        metadata={"raw_thread_decisions_count": len(aggregated_raw)},
    )


def normalize_thread_decisions(ctx: WorkflowContext) -> WorkflowResult:
    """
    Parse and validate raw AI output into ThreadDecision models.

    Accepts raw_thread_decisions as a list of dicts or a JSON string.
    Each item is validated as a ThreadDecision model. Invalid items are
    skipped with a warning rather than failing the entire step.

    Requires (from ctx.data):
        raw_thread_decisions (list | str): Raw AI output from ai_thread_resolution

    Outputs (saved to ctx.data):
        thread_decisions (List[ThreadDecision]): Validated ThreadDecision objects

    Returns:
        Success or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Normalize Thread Decisions")

    raw = ctx.get("raw_thread_decisions")

    if raw is None:
        ctx.textual.dim_text("No thread decisions to normalize")
        ctx.textual.end_step("skip")
        return Skip("No raw_thread_decisions in context")

    from ..models.review_models import ThreadDecision
    from pydantic import ValidationError
    import json

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            ctx.textual.error_text(f"Failed to parse raw_thread_decisions JSON: {e}")
            ctx.textual.end_step("error")
            return Error(f"Failed to parse raw_thread_decisions JSON: {e}")

    if not isinstance(raw, list):
        ctx.textual.error_text(f"raw_thread_decisions must be a list, got {type(raw).__name__}")
        ctx.textual.end_step("error")
        return Error(f"raw_thread_decisions must be a list, got {type(raw).__name__}")

    decisions: list[ThreadDecision] = []
    skipped = 0
    auto_resolved = 0

    for i, item in enumerate(raw):
        try:
            decision = ThreadDecision.model_validate(item)

            # Validate: if decision is "reply" or "insist" but suggested_reply is empty,
            # convert to "resolved" (avoid posting empty comments)
            if decision.decision in (ThreadDecisionType.REPLY, ThreadDecisionType.INSIST):
                reply_body = (decision.suggested_reply or "").strip()
                reasoning = (decision.reasoning or "").strip()

                if not reply_body:
                    # Try to use reasoning as fallback, otherwise convert to skip
                    if reasoning and len(reasoning) > 10:
                        # Use reasoning as the reply body
                        ctx.textual.dim_text(f"⚠ Decision {i + 1}: using reasoning as reply")
                        decision = decision.model_copy(update={"suggested_reply": reasoning})
                    else:
                        # Both empty - convert to skip
                        ctx.textual.dim_text(f"⚠ Decision {i + 1}: empty reply → skip")
                        decision = decision.model_copy(
                            update={
                                "decision": ThreadDecisionType.SKIP,
                                "suggested_reply": None,
                            }
                        )
                        auto_resolved += 1

            # Ensure suggested_reply is None for "resolved" and "skip"
            if decision.decision in (ThreadDecisionType.RESOLVED, ThreadDecisionType.SKIP):
                if decision.suggested_reply:
                    decision = decision.model_copy(update={"suggested_reply": None})

            decisions.append(decision)
        except ValidationError as e:
            skipped += 1
            ctx.textual.dim_text(f"⚠ Decision {i + 1} invalid, skipping: {e.error_count()} error(s)")
            logger.debug("ThreadDecision %d validation error: %s", i + 1, e)

    ctx.data["thread_decisions"] = decisions

    summary = f"✓ {len(decisions)} decision(s) normalized"
    if auto_resolved:
        summary += f" ({auto_resolved} empty replies → resolved)"
    if skipped:
        summary += f" ({skipped} skipped)"
    ctx.textual.success_text(summary)
    ctx.textual.end_step("success")
    return Success("Thread decisions normalized", metadata={
        "thread_decisions_count": len(decisions),
        "auto_resolved_empty_replies": auto_resolved
    })


def build_thread_actions(ctx: WorkflowContext) -> WorkflowResult:
    """
    Transform ThreadDecision objects into ReviewActionProposal objects.

    Maps AI decisions to concrete GitHub actions:
    - resolved → resolve_thread (mark thread as resolved via GraphQL)
    - insist / reply → reply_to_thread (post a follow-up comment via REST API)
    - skip → (no action created)

    Saves results under the same key as new_findings workflow so that
    validate_review_actions and submit_review_actions can be reused directly.

    Requires (from ctx.data):
        thread_decisions (List[ThreadDecision])
        thread_review_contexts (List[ThreadReviewContext])

    Outputs (saved to ctx.data):
        review_action_proposals (List[ReviewActionProposal])

    Returns:
        Success, Skip (no actionable decisions), or Error
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    ctx.textual.begin_step("Build Thread Actions")

    decisions = ctx.get("thread_decisions")
    contexts = ctx.get("thread_review_contexts", [])

    if decisions is None:
        ctx.textual.dim_text("No thread decisions available")
        ctx.textual.end_step("skip")
        return Skip("No thread_decisions in context")

    actions = build_thread_actions_operation(decisions, contexts)

    if not actions:
        ctx.textual.dim_text("No actionable thread decisions")
        ctx.textual.end_step("skip")
        return Skip("No actionable thread decisions")

    ctx.data["review_action_proposals"] = actions

    resolve_count = sum(1 for a in actions if a.action_type == ReviewActionType.RESOLVE_THREAD)
    reply_count = sum(1 for a in actions if a.action_type == ReviewActionType.REPLY_TO_THREAD)
    summary_parts = []
    if resolve_count:
        summary_parts.append(f"{resolve_count} resolve")
    if reply_count:
        summary_parts.append(f"{reply_count} reply")
    ctx.textual.success_text(f"✓ {len(actions)} action(s) built: {', '.join(summary_parts)}")
    ctx.textual.end_step("success")
    return Success("Thread actions built", metadata={"thread_actions_count": len(actions)})
