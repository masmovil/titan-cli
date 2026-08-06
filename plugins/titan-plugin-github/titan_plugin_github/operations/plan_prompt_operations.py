"""Operations for building AI prompts for focused review planning."""

import json

from ..models.review_models import (
    ChangeManifest,
    CommentContextEntry,
    ExcludedFileEntry,
    ReviewChecklistItem,
    ReviewPlan,
    ReviewStrategy,
    ScoredReviewCandidate,
)
from ..models.review_profile_models import ReviewProfile
from .prompt_formatting_operations import comment_context_to_json, extract_pr_intent
from .review_strategy_operations import build_deterministic_review_plan, summarize_candidate_clusters


def build_review_plan_prompt(
    manifest: ChangeManifest,
    comments: list[CommentContextEntry],
    checklist: list[ReviewChecklistItem],
    candidates: list[ScoredReviewCandidate],
    strategy: ReviewStrategy,
    excluded_files: list[ExcludedFileEntry],
    review_profile: ReviewProfile | None = None,
) -> str:
    manifest_json = _manifest_to_json(manifest)
    comments_json = comment_context_to_json(comments)
    checklist_json = _checklist_to_json(checklist)
    candidates_json = _candidates_to_json(candidates[: strategy.max_focus_files + 4])
    candidate_clusters_json = _candidate_clusters_to_json(candidates, review_profile)
    excluded_json = _excluded_to_json(excluded_files[:10])
    schema = _review_plan_schema()

    return f"""You are planning a focused pull request review.

Your job is NOT to review the code yet. Your job is to decide which changed files deserve deep review, which review axes matter, and what small amount of extra context is justified.

Use the candidate ranking as your starting point. Do not expand the focus unnecessarily.

## PR Manifest
{manifest_json}

## Existing Comment Context
{comments_json}

## Ranked Candidate Files
{candidates_json}

## Repeated Candidate Groups
{candidate_clusters_json}

## Already Deprioritized Files
{excluded_json}

## Review Checklist
{checklist_json}

## Execution Constraints
- Focus at most {strategy.max_focus_files} files
- Prefer expanded_hunks over full_file
- Request extra context only when truly needed
- If the repository exposes project instructions, skills, or review documentation in the current working tree, use them when relevant, but do not depend on them

Respond ONLY with valid JSON matching this schema:
{schema}

Rules:
- Select only files that are likely to contain correctness, validation, API, or error-handling issues
- Keep low-value files excluded unless there is a clear reason to bring one back
- review_axes should be a small subset of checklist categories that really apply
- excluded_files should explain what you are intentionally not reviewing deeply
- Return only JSON, no markdown fences"""


def build_default_review_plan(
    candidates: list[ScoredReviewCandidate],
    excluded_files: list[ExcludedFileEntry],
    checklist: list[ReviewChecklistItem],
    strategy: ReviewStrategy,
    review_profile: ReviewProfile | None = None,
) -> ReviewPlan:
    return build_deterministic_review_plan(
        candidates,
        excluded_files,
        checklist,
        strategy,
        review_profile=review_profile,
    )


def _manifest_to_json(manifest: ChangeManifest) -> str:
    return json.dumps(
        {
            "pr": {
                "number": manifest.pr.number,
                "title": manifest.pr.title,
                "base": manifest.pr.base,
                "head": manifest.pr.head,
                "author": manifest.pr.author,
                # Deterministic trim (strip images/HTML comments/checkboxes) instead of a
                # raw [:300] cut, which on real PRs often yields only a meme/badge URL.
                "description": extract_pr_intent(manifest.pr.description, max_chars=800),
            },
            "files_changed": len(manifest.files),
            "total_additions": manifest.total_additions,
            "total_deletions": manifest.total_deletions,
            "top_changed_files": [
                {
                    "path": f.path,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "is_test": f.is_test,
                    "is_docs": f.is_docs,
                    "is_generated": f.is_generated,
                    "is_config": f.is_config,
                    "is_lockfile": f.is_lockfile,
                    "is_rename_only": f.is_rename_only,
                }
                for f in sorted(manifest.files, key=lambda item: item.total_changes, reverse=True)[:12]
            ],
            "remaining_file_count": max(0, len(manifest.files) - 12),
        },
        indent=2,
    )
def _checklist_to_json(checklist: list[ReviewChecklistItem]) -> str:
    return json.dumps(
        [
            {"id": item.id, "name": item.name, "description": item.description}
            for item in checklist
        ],
        indent=2,
    )


def _candidates_to_json(candidates: list[ScoredReviewCandidate]) -> str:
    return json.dumps(
        [
            {
                "path": item.path,
                "score": item.score,
                "priority": item.priority,
                "suggested_read_mode": item.suggested_read_mode,
                "reasons": item.reasons,
            }
            for item in candidates
        ],
        indent=2,
    )


def _excluded_to_json(excluded_files: list[ExcludedFileEntry]) -> str:
    return json.dumps(
        [
            {"path": item.path, "reason": item.reason, "detail": item.detail}
            for item in excluded_files
        ],
        indent=2,
    )


def _candidate_clusters_to_json(
    candidates: list[ScoredReviewCandidate],
    review_profile: ReviewProfile | None = None,
) -> str:
    return json.dumps(summarize_candidate_clusters(candidates, review_profile), indent=2)


def _review_plan_schema() -> str:
    return json.dumps(
        {
            "focus_files": [
                {
                    "path": "<file_path>",
                    "priority": "<high|medium|low>",
                    "read_mode": "<hunks_only|expanded_hunks|full_file>",
                    "reasons": ["<why this file matters>"],
                }
            ],
            "review_axes": ["<functional_correctness|error_handling|...>"],
            "extra_context_requests": [
                {
                    "type": "<related_tests|related_context>",
                    "for_path": "<file_path>",
                    "reason": "<why needed>",
                }
            ],
            "excluded_files": [
                {
                    "path": "<file_path>",
                    "reason": "<docs|generated|lockfile|rename_only|deleted|low_signal_test|low_signal_config|budget_trimmed>",
                    "detail": "<optional detail>",
                }
            ],
        },
        indent=2,
    )
