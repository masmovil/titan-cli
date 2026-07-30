"""
Operations for building and submitting review actions.

Pure business logic for Phase 5 of the new_findings_review pipeline:
converting Finding objects into ReviewActionProposal objects and building
the GitHub API payload for submission.
"""

from typing import Dict, List, Optional

from titan_cli.core.logging.config import get_logger

from ..models.review_enums import ReviewActionSource, ReviewActionType
from ..models.review_models import Finding, ReviewActionProposal
from ..managers.diff_context_manager import DiffContextManager, get_or_create_diff_manager

logger = get_logger(__name__)


def classify_github_review_rejection(error_message: str) -> str:
    """Classify GitHub inline review rejection into a stable bucket."""
    lower = error_message.lower()
    if "line could not be resolved" in lower:
        return "line_not_resolved"
    if "path could not be resolved" in lower:
        return "path_not_resolved"
    if "one pending review" in lower:
        return "pending_review_exists"
    return "unknown"


def build_new_comment_actions(findings: List[Finding]) -> List[ReviewActionProposal]:
    """
    Convert deduplicated findings into ReviewActionProposal objects.

    Args:
        findings: Validated, deduplicated Finding objects from Phase 4

    Returns:
        List of ReviewActionProposal with action_type='new_comment'
    """
    actions = []
    for finding in findings:
        actions.append(
            ReviewActionProposal(
                action_type=ReviewActionType.NEW_COMMENT,
                source=ReviewActionSource.NEW_FINDING,
                path=finding.path,
                line=finding.line,
                original_line=finding.line,
                title=finding.title,
                body=finding.suggested_comment,
                reasoning=finding.why,
                category=finding.category,
                severity=finding.severity,
                anchor_snippet=finding.snippet,
                evidence=finding.evidence,
            )
        )
    return actions


def build_review_action_payload(
    actions: List[ReviewActionProposal],
    commit_sha: str,
    diff: str = "",
    diff_manager: Optional[DiffContextManager] = None,
) -> Dict:
    """
    Build the GitHub API payload from approved ReviewActionProposal objects.

    Handles new_comment action type only. Actions with action_type='resolve_thread'
    or 'reply_to_thread' are excluded — they are handled separately via direct API
    calls in the submit step.

    For new_comment actions, tries to place the comment inline if the line
    is present in the diff. Falls back to the general review body otherwise.

    Args:
        actions: Approved ReviewActionProposal objects
        commit_sha: Head commit SHA for inline comments
        diff: Full PR unified diff (used to validate inline line positions)

    Returns:
        Dict with keys: commit_id, comments (list), body (str, optional)
    """
    manager = diff_manager or (get_or_create_diff_manager(diff) if diff else None)
    # Publishable lines come from GitHub's own diff when attached (D-008): the local
    # context diff may use extended context (-U20) whose extra context lines GitHub
    # rejects with 422 "line could not be resolved".
    valid_lines = {p: set(ls) for p, ls in manager.get_all_publishable_lines().items()} if manager else {}
    logger.debug(
        "build_review_payload_start",
        action_count=len(actions),
        files_in_diff=len(valid_lines),
        publishable_source="github_diff" if manager and manager.has_github_diff else "added_lines_fallback",
    )
    if valid_lines:
        for path, lines in valid_lines.items():  # Log TODOS los archivos
            sorted_lines = sorted(list(lines))[:10]  # First 10 lines
            logger.debug("valid_lines_for_file", path=path, line_count=len(lines), sample_lines=sorted_lines)
    else:
        logger.warning("no_valid_lines_in_diff", diff_length=len(diff) if diff else 0)

    inline_comments = []
    general_parts: List[str] = []

    for idx, action in enumerate(actions):
        if action.action_type in (
            ReviewActionType.RESOLVE_THREAD,
            ReviewActionType.REPLY_TO_THREAD,
        ):
            continue

        # new_comment — try inline first, fall back to general body
        resolved_line = action.resolved_line

        if action.path and resolved_line:
            file_valid_lines = valid_lines.get(action.path, set())
            inline_safe = resolved_line in file_valid_lines
            logger.debug("validate_comment_action",
                action_idx=idx, path=action.path, line=action.line, resolved_line=resolved_line,
                original_line=action.original_line,
                resolution_source=action.resolution_source,
                anchor_confidence=action.anchor_confidence,
                inline_reason=action.inline_reason,
                why_inline_allowed=action.why_inline_allowed,
                file_status=action.file_status,
                is_test_file=action.is_test_file,
                read_mode=action.read_mode,
                file_has_valid_lines=len(file_valid_lines),
                is_valid=inline_safe)
            if inline_safe:
                inline_comments.append({
                    "path": action.path,
                    "line": resolved_line,
                    "side": "RIGHT",
                    "body": action.body,
                })
                logger.debug("inline_comment_added", action_idx=idx, path=action.path, line=resolved_line)
                continue

        # Fallback: include in the general review body
        location = f"**{action.path}**" if action.path else "General"
        display_line = resolved_line or action.line
        if display_line:
            location += f" (line {display_line})"
        general_parts.append(f"{location}:\n{action.body}")
        logger.debug(
            "fallback_to_general_body",
            action_idx=idx,
            path=action.path,
            line=action.line,
            resolved_line=resolved_line,
            resolution_source=action.resolution_source,
        )

    payload: Dict = {"commit_id": commit_sha, "comments": inline_comments}
    if general_parts:
        payload["body"] = "\n\n---\n\n".join(general_parts)

    logger.debug("build_review_payload_complete",
        commit_sha=commit_sha,
        inline_comment_count=len(inline_comments),
        general_comment_count=len(general_parts),
        inline_comments_details=[
            {"path": c.get("path"), "line": c.get("line"), "has_body": len(c.get("body", "")) > 0}
            for c in inline_comments
        ],
        inline_candidates_details=[
            {
                "path": action.path,
                "original_line": action.original_line,
                "resolved_line": action.resolved_line,
                "resolution_source": action.resolution_source,
                "anchor_confidence": action.anchor_confidence,
                "inline_reason": action.inline_reason,
                "why_inline_allowed": action.why_inline_allowed,
                "is_inline_safe_for_github": action.is_inline_safe_for_github,
                "file_status": action.file_status,
                "is_test_file": action.is_test_file,
                "read_mode": action.read_mode,
            }
            for action in actions
            if action.action_type == ReviewActionType.NEW_COMMENT
        ],
    )

    return payload


def extract_diff_hunk_for_action(
    action: ReviewActionProposal,
    diff: str,
    diff_manager: Optional[DiffContextManager] = None,
) -> Optional[str]:
    """
    Extract the diff hunk around an action's file/line for display in the UI.

    Args:
        action: The action whose code context to extract
        diff: Full PR unified diff

    Returns:
        Hunk string starting with @@, or None if not found
    """
    if not diff or not action.path or not action.line:
        return None

    manager = diff_manager or get_or_create_diff_manager(diff)
    resolved_line = action.resolved_line
    if resolved_line is None:
        return None

    hunk = manager.get_hunk_for_line(action.path, resolved_line, allow_fallback=False)
    return hunk.content if hunk else None


def resolve_action_anchors(
    actions: List[ReviewActionProposal],
    diff: str,
    diff_manager: Optional[DiffContextManager] = None,
) -> List[ReviewActionProposal]:
    """Return actions enriched with resolved inline anchors for UI and submission."""
    if not diff:
        return actions

    manager = diff_manager or get_or_create_diff_manager(diff)
    resolved_actions: List[ReviewActionProposal] = []
    for action in actions:
        if not action.path:
            resolved_actions.append(action)
            continue

        resolved_line = manager.resolve_line_anchor(
            action.path,
            line=action.line,
            snippet=action.anchor_snippet,
            evidence=action.evidence,
        )
        resolution_source = None
        anchor_confidence = "none"
        inline_reason = None
        why_inline_allowed = None
        if resolved_line is not None:
            if action.anchor_snippet and resolved_line in manager.find_lines_by_snippet(action.path, action.anchor_snippet):
                resolution_source = "snippet"
                anchor_confidence = "high"
                inline_reason = "snippet_match"
            elif action.evidence and resolved_line in manager.find_lines_by_snippet(action.path, action.evidence):
                resolution_source = "evidence"
                anchor_confidence = "medium"
                inline_reason = "evidence_match"
            elif action.line == resolved_line:
                resolution_source = "validated_line"
                anchor_confidence = "medium"
                inline_reason = "validated_line"
            else:
                resolution_source = "resolved"
                anchor_confidence = "low"
                inline_reason = "context_match"

            is_inline_safe_for_github = resolved_line in manager.get_publishable_lines(action.path)
            if is_inline_safe_for_github:
                why_inline_allowed = (
                    f"resolved via {resolution_source} to line {resolved_line} present in GitHub-publishable lines"
                )
            else:
                why_inline_allowed = (
                    f"resolved via {resolution_source} but line {resolved_line} not in GitHub-publishable lines"
                )
        else:
            is_inline_safe_for_github = False
            why_inline_allowed = "no resolved line could be inferred from snippet/evidence/AI line"

        resolved_actions.append(
            action.model_copy(
                update={
                    "original_line": action.original_line or action.line,
                    "resolved_line": resolved_line,
                    "resolution_source": resolution_source,
                    "anchor_confidence": anchor_confidence,
                    "inline_reason": inline_reason,
                    "why_inline_allowed": why_inline_allowed,
                    "is_inline_safe_for_github": is_inline_safe_for_github,
                }
            )
        )
    return resolved_actions
