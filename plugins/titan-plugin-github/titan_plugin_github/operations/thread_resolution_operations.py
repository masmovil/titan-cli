"""
Operations for the thread resolution pipeline (Phase 6).

Pure functions — no UI, no side effects. Takes open review threads and produces
ReviewActionProposal objects (resolve_thread / reply_to_thread) for the shared
validate → submit pipeline.
"""

import json
from typing import Optional

from ..models.review_enums import (
    ReviewActionSource,
    ReviewActionType,
    ThreadDecisionType,
    ThreadSeverity,
)
from ..models.review_models import (
    ReviewActionProposal,
    ThreadDecision,
    ThreadReviewCandidate,
    ThreadReviewContext,
)
from ..managers.diff_context_manager import DiffContextManager
from ..models.view import UICommentThread


def build_thread_review_candidates(
    threads: list[UICommentThread],
    pr_author: str,
    reviewer_login: str,
) -> list[ThreadReviewCandidate]:
    """
    Filter threads worth AI analysis from the full list of open PR threads.

    Includes only inline (non-general) unresolved threads where the last
    comment is from the PR author (meaning they have replied to the review).
    General comments (thread_id starts with 'general_') cannot be resolved
    via GraphQL and are excluded.

    Args:
        threads: All unresolved inline review threads from fetch_pr_review_bundle
        pr_author: GitHub login of the PR author
        reviewer_login: GitHub login of the reviewer running Titan

    Returns:
        ThreadReviewCandidate list ready for context enrichment
    """
    candidates = []
    for thread in threads:
        if thread.is_general_comment:
            continue
        if thread.is_resolved:
            continue
        if thread.main_comment.author_login != reviewer_login:
            continue

        # Skip if no replies — reviewer is waiting for author response
        if not thread.replies:
            continue

        # Skip if last reply is not from PR author — reviewer is waiting for response
        last_reply = thread.replies[-1]
        if last_reply.author_login != pr_author:
            continue

        main = thread.main_comment
        replies = thread.replies

        last_reply_author = replies[-1].author_login if replies else None
        last_reply_body = replies[-1].body if replies else None

        candidates.append(
            ThreadReviewCandidate(
                thread_id=thread.thread_id,
                path=main.path,
                line=main.line,
                main_comment_body=main.body,
                main_comment_author=main.author_login,
                replies_count=len(replies),
                last_reply_author=last_reply_author,
                last_reply_body=last_reply_body,
                is_outdated=thread.is_outdated,
            )
        )

    return candidates


def build_thread_review_contexts(
    candidates: list[ThreadReviewCandidate],
    threads: list[UICommentThread],
    diff: str,
) -> list[ThreadReviewContext]:
    """
    Enrich each candidate with diff hunk context and full reply history.

    Args:
        candidates: Selected threads from build_thread_review_candidates
        threads: Original UICommentThread list (for extracting all replies)
        diff: Full PR unified diff

    Returns:
        ThreadReviewContext list ready for AI prompt building
    """
    thread_map = {t.thread_id: t for t in threads}
    contexts = []

    for candidate in candidates:
        thread = thread_map.get(candidate.thread_id)
        all_replies: list[dict] = []
        if thread:
            for reply in thread.replies:
                all_replies.append({"author": reply.author_login, "body": reply.body})

        hunk = None
        if candidate.path and candidate.line:
            hunk = _extract_hunk_near_line(diff, candidate.path, candidate.line)

        contexts.append(
            ThreadReviewContext(
                thread_id=candidate.thread_id,
                comment_id=thread.main_comment.id if thread else 0,
                path=candidate.path,
                line=candidate.line,
                main_comment_body=candidate.main_comment_body,
                main_comment_author=candidate.main_comment_author,
                all_replies=all_replies,
                current_code_hunk=hunk,
                is_outdated=candidate.is_outdated,
            )
        )

    return contexts


def _extract_hunk_near_line(diff: str, path: str, line: int, context: int = 5) -> Optional[str]:
    """
    Extract lines from the diff near `line` for the given file path.

    Args:
        diff: Full PR unified diff
        path: File path as it appears in the diff header
        line: Target line number
        context: Number of lines before/after to include (reserved for future use)

    Returns:
        Extracted diff hunk string, or None if the file/line is not in the diff
    """
    hunk = DiffContextManager.from_diff(diff).get_hunk_for_line(path, line)
    return hunk.content if hunk else None


def build_thread_resolution_prompt(contexts: list[ThreadReviewContext]) -> str:
    """
    Build the prompt for the thread resolution AI call.

    Presents each open thread with its full conversation and current code hunk.
    Asks the AI to decide whether the author's response resolves the issue,
    needs a follow-up reply, or can be skipped.

    Args:
        contexts: Enriched thread contexts from build_thread_review_contexts

    Returns:
        Formatted prompt string ready to send to a headless CLI adapter
    """
    threads_text = _threads_to_text(contexts)
    schema = _thread_decision_schema()

    return f"""You are reviewing open PR comment threads to decide how to proceed with each one.

For each thread, you have:
- The original reviewer comment
- All replies from the PR author and other reviewers
- The current state of the code near the commented line (if available)

## Open Threads

{threads_text}

## Your Task

For each thread, decide one of the following actions:

- **resolved**: The author's changes or replies have fully addressed the issue. The thread can be marked as resolved. Use this when:
  - The code hunk shows the problem has been fixed
  - The author acknowledged and applied the fix
  - The concern is no longer relevant due to code changes
  - The original issue is gone

- **insist**: The issue still exists in the code. The author's reply did not address it. Post a follow-up comment explaining why the problem persists.

- **reply**: The concern is partially addressed or needs clarification/acknowledgment. The author's approach seems right but needs:
  - Minor tweaks or explanations
  - Acknowledgment that the fix was applied
  - Clarification on edge cases

- **skip**: The thread is not actionable now (out of scope, already agreed to fix later, administrative discussion, etc.)

## Critical Rules:

1. **NEVER use "reply" or "insist" with empty or whitespace-only body**. If you have nothing substantive to say, use "resolved" or "skip".
2. Base decisions on **actual code shown**, not assumptions.
3. If code hunk shows the fix applied → **resolved** (suggested_reply: null)
4. If author replied but problem still visible in code → **insist** (with detailed explanation of why it's still broken)
5. If you need confirmation or minor fixes → **reply** (with specific, actionable request)
6. `suggested_reply` is MANDATORY when decision is "insist" or "reply":
   - Must be non-empty (at least 10 characters of actual content, not whitespace)
   - Must be a complete, ready-to-post GitHub comment
   - Can reference the author's changes or code
7. `suggested_reply` must be null when decision is "resolved" or "skip"
8. If you cannot think of a substantive reply, change decision to "resolved"

Respond ONLY with a valid JSON array matching this exact schema for each element:
{schema}

Return ONLY the JSON array. No explanation, no markdown fences."""


DEFAULT_THREAD_BATCH_MAX_PROMPT_CHARS = 20_000
DEFAULT_THREAD_BATCH_MAX_THREADS = 8


def batch_thread_review_contexts(
    contexts: list[ThreadReviewContext],
    max_prompt_chars: int = DEFAULT_THREAD_BATCH_MAX_PROMPT_CHARS,
    max_threads_per_batch: int = DEFAULT_THREAD_BATCH_MAX_THREADS,
) -> list[list[ThreadReviewContext]]:
    """
    Split thread contexts into batches that keep each AI call within a prompt budget.

    Each thread keeps its full conversation, code hunk, and referenced commit
    context untouched — batching only controls how many threads share one AI
    call, so no per-thread content is trimmed. A thread that alone exceeds the
    budget is still sent by itself rather than being degraded.

    Args:
        contexts: Enriched thread contexts from build_thread_review_contexts
        max_prompt_chars: Target prompt size per batch (soft budget)
        max_threads_per_batch: Upper bound on threads per batch regardless of size

    Returns:
        List of thread-context batches, each safe to pass to build_thread_resolution_prompt
    """
    if not contexts:
        return []

    queue = [
        contexts[i : i + max_threads_per_batch]
        for i in range(0, len(contexts), max_threads_per_batch)
    ]
    batches: list[list[ThreadReviewContext]] = []

    while queue:
        batch = queue.pop(0)
        if len(batch) == 1:
            batches.append(batch)
            continue

        if len(build_thread_resolution_prompt(batch)) <= max_prompt_chars:
            batches.append(batch)
            continue

        midpoint = max(1, len(batch) // 2)
        queue.insert(0, batch[midpoint:])
        queue.insert(0, batch[:midpoint])

    return batches


def _threads_to_text(contexts: list[ThreadReviewContext]) -> str:
    if not contexts:
        return "(no threads to review)"

    parts: list[str] = []
    for i, ctx in enumerate(contexts, 1):
        location = f"`{ctx.path}` line {ctx.line}" if ctx.path else "general"
        if ctx.is_outdated:
            location += " *(outdated — code may have moved)*"

        parts.append(f"### Thread {i} [thread_id: {ctx.thread_id}]")
        parts.append(f"**Location**: {location}")
        parts.append(f"**Original comment** by @{ctx.main_comment_author}:")
        parts.append(f"> {ctx.main_comment_body}")

        if ctx.all_replies:
            parts.append(f"\n**Replies** ({len(ctx.all_replies)}):")
            for reply in ctx.all_replies:
                parts.append(f"- @{reply['author']}: {reply['body']}")
        else:
            parts.append("\n*(no replies yet)*")

        if ctx.current_code_hunk:
            parts.append("\n**Current code near this line:**")
            parts.append("```diff")
            parts.append(ctx.current_code_hunk)
            parts.append("```")
        else:
            parts.append("\n*(code context not available — file may be deleted or line not in diff)*")

        if ctx.referenced_commits:
            parts.append("\n**Referenced commits from replies:**")
            for commit in ctx.referenced_commits:
                parts.append(f"- Commit `{commit.abbreviated_sha}`")
                if commit.message:
                    parts.append("  Message:")
                    parts.append("  ```")
                    for line in commit.message.splitlines():
                        parts.append(f"  {line}")
                    parts.append("  ```")
                if commit.changed_files:
                    parts.append("  Files: " + ", ".join(commit.changed_files))
                if commit.patch_excerpt:
                    parts.append("  Patch excerpt:")
                    parts.append("```diff")
                    parts.extend(commit.patch_excerpt.splitlines())
                    parts.append("```")

        parts.append("")

    return "\n".join(parts)


def _thread_decision_schema() -> str:
    return json.dumps(
        [
            {
                "thread_id": "<thread_id exactly as shown in the Thread header>",
                "decision": "<resolved|insist|reply|skip>",
                "reasoning": "<why this decision was made>",
                "suggested_reply": "<complete reply text, or null>",
                "category": "<issue category, e.g. error_handling, or null>",
                "severity": "<important|nit|none>",
            }
        ],
        indent=2,
    )


def build_thread_actions(
    decisions: list[ThreadDecision],
    contexts: list[ThreadReviewContext],
) -> list[ReviewActionProposal]:
    """
    Transform ThreadDecision objects into ReviewActionProposal objects.

    Maps decisions to action types:
    - resolved → resolve_thread (uses thread_id for GraphQL)
    - insist / reply → reply_to_thread (uses comment_id for REST API)
    - skip → (excluded, no action created)

    Args:
        decisions: Validated ThreadDecision objects from normalize_thread_decisions
        contexts: ThreadReviewContext list to look up comment IDs by thread_id

    Returns:
        List of ReviewActionProposal with source='thread_followup'
    """
    context_map = {ctx.thread_id: ctx for ctx in contexts}
    actions = []

    for decision in decisions:
        if decision.decision == ThreadDecisionType.SKIP:
            continue

        context = context_map.get(decision.thread_id)
        if not context:
            continue

        if decision.decision == ThreadDecisionType.RESOLVED:
            actions.append(
                ReviewActionProposal(
                    action_type=ReviewActionType.RESOLVE_THREAD,
                    source=ReviewActionSource.THREAD_FOLLOWUP,
                    thread_id=decision.thread_id,
                    title="Resolve thread (issue addressed)",
                    body="",
                    reasoning=decision.reasoning,
                    category=decision.category,
                    severity=decision.severity if decision.severity != ThreadSeverity.NONE else None,
                )
            )
        elif decision.decision in (ThreadDecisionType.INSIST, ThreadDecisionType.REPLY):
            # Fallback: use reasoning if suggested_reply is empty
            reply_body = (decision.suggested_reply or "").strip()
            if not reply_body:
                # Should not happen after validation, but be safe
                reply_body = decision.reasoning

            if not reply_body or not reply_body.strip():
                # Still empty after fallback - skip creating action
                continue

            label = "Insist" if decision.decision == ThreadDecisionType.INSIST else "Reply"
            actions.append(
                ReviewActionProposal(
                    action_type=ReviewActionType.REPLY_TO_THREAD,
                    source=ReviewActionSource.THREAD_FOLLOWUP,
                    thread_id=decision.thread_id,
                    comment_id=context.comment_id,
                    title=f"{label}: {decision.category or 'follow-up'}",
                    body=reply_body,
                    reasoning=decision.reasoning,
                    category=decision.category,
                    severity=decision.severity if decision.severity != ThreadSeverity.NONE else None,
                )
            )

    return actions
