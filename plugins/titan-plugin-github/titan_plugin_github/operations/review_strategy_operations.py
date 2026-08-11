"""Deterministic operations for selecting PR review focus."""

from .review_profile_operations import (
    classify_file_role,
    is_reviewable_documentation,
    match_change_patterns,
    matching_scoring_rules,
    select_review_axes,
)
from ..models.review_enums import (
    ExclusionReason,
    FileReadMode,
    FileReviewPriority,
    PRSizeClass,
    ReviewStrategyType,
)
from ..models.review_profile_models import ReviewProfile
from ..models.review_models import (
    ChangeManifest,
    ExcludedFileEntry,
    FileReviewPlan,
    PRClassification,
    ReviewChecklistItem,
    ReviewPlan,
    ReviewStrategy,
    ScoredReviewCandidate,
)
from ..review_profiles import DEFAULT_REVIEW_PROFILE


def classify_pr(
    manifest: ChangeManifest,
    comment_entries: int = 0,
    comment_threads: int = 0,
    review_profile: ReviewProfile | None = None,
) -> PRClassification:
    review_profile = review_profile or DEFAULT_REVIEW_PROFILE
    total_lines = manifest.total_additions + manifest.total_deletions
    files_changed = len(manifest.files)
    repeated_callsite_files = sum(
        1 for f in manifest.files if "repeated_callsite" in match_change_patterns(f.path, review_profile)
    )
    high_signal_files = sum(
        1
        for f in manifest.files
        if {"central_behavior", "entrypoint"}.intersection(match_change_patterns(f.path, review_profile))
    )
    repetition_ratio = (repeated_callsite_files / files_changed) if files_changed else 0.0
    roles = sorted(
        {
            classify_file_role(
                f.path,
                review_profile,
                is_test=f.is_test,
                is_docs=f.is_docs,
                is_generated=f.is_generated,
                is_config=f.is_config,
            )
            for f in manifest.files
        }
    )
    role_count = len(roles)
    active_review = comment_threads >= 5 or comment_entries >= 10
    is_repetitive_migration = files_changed >= 12 and total_lines <= 700 and repetition_ratio >= 0.35
    complexity_score = _compute_complexity_score(
        files_changed=files_changed,
        total_lines=total_lines,
        high_signal_files=high_signal_files,
        role_count=role_count,
        is_repetitive_migration=is_repetitive_migration,
        repetition_ratio=repetition_ratio,
    )
    size_class = _score_to_size_class(complexity_score)

    if files_changed >= 35 and total_lines >= 4000 and role_count >= 3:
        size_class = PRSizeClass.HUGE

    if size_class == PRSizeClass.HUGE and is_repetitive_migration:
        size_class = PRSizeClass.LARGE
    elif size_class == PRSizeClass.HUGE and files_changed <= 15 and role_count <= 4 and high_signal_files <= 6:
        size_class = PRSizeClass.LARGE
    elif size_class == PRSizeClass.LARGE and files_changed <= 8 and total_lines <= 300:
        size_class = PRSizeClass.SMALL

    rationale_parts = [f"{files_changed} files", f"{total_lines} changed lines"]
    if high_signal_files:
        rationale_parts.append(f"{high_signal_files} high-signal files")
    if repeated_callsite_files:
        rationale_parts.append(f"{repeated_callsite_files} repeated call sites")
    if role_count:
        rationale_parts.append(f"roles: {', '.join(roles)}")
    if active_review:
        rationale_parts.append("active review in progress")
    if is_repetitive_migration:
        rationale_parts.append("repetitive migration pattern detected")
    rationale_parts.append(f"complexity score {complexity_score}")

    return PRClassification(
        size_class=size_class,
        files_changed=files_changed,
        total_lines_changed=total_lines,
        doc_files=sum(1 for f in manifest.files if f.is_docs),
        test_files=sum(1 for f in manifest.files if f.is_test),
        config_files=sum(1 for f in manifest.files if f.is_config),
        generated_files=sum(1 for f in manifest.files if f.is_generated),
        comment_threads=comment_threads,
        comment_entries=comment_entries,
        high_signal_files=high_signal_files,
        repeated_callsite_files=repeated_callsite_files,
        role_count=role_count,
        roles=roles,
        complexity_score=complexity_score,
        active_review=active_review,
        is_repetitive_migration=is_repetitive_migration,
        rationale=", ".join(rationale_parts),
    )


def _compute_complexity_score(
    *,
    files_changed: int,
    total_lines: int,
    high_signal_files: int,
    role_count: int,
    is_repetitive_migration: bool,
    repetition_ratio: float,
) -> int:
    # The size class measures the CODE, so review activity deliberately plays no part
    # here: comments don't make a PR bigger, and counting them meant a review's own
    # published comments could push the same unchanged PR into a bigger size class on
    # the next run. Review activity is captured separately as `active_review`.
    score = 0

    if files_changed <= 3:
        score += 0
    elif files_changed <= 8:
        score += 2
    elif files_changed <= 15:
        score += 3
    elif files_changed <= 40:
        score += 4
    else:
        score += 6

    if total_lines <= 80:
        score += 0
    elif total_lines <= 300:
        score += 1
    elif total_lines <= 900:
        score += 2
    elif total_lines <= 2500:
        score += 3
    elif total_lines <= 10000:
        score += 4
    else:
        score += 6

    if high_signal_files >= 8:
        score += 3
    elif high_signal_files >= 4:
        score += 2
    elif high_signal_files >= 1:
        score += 1

    if role_count >= 6:
        score += 3
    elif role_count >= 4:
        score += 2
    elif role_count >= 2:
        score += 1

    if is_repetitive_migration:
        score -= 2
    elif repetition_ratio >= 0.35:
        score -= 1

    return max(0, score)


def _score_to_size_class(score: int) -> PRSizeClass:
    if score <= 2:
        return PRSizeClass.TINY
    if score <= 4:
        return PRSizeClass.SMALL
    if score <= 6:
        return PRSizeClass.MEDIUM
    if score <= 10:
        return PRSizeClass.LARGE
    return PRSizeClass.HUGE


def score_review_candidates(
    manifest: ChangeManifest,
    review_profile: ReviewProfile | None = None,
) -> tuple[list[ScoredReviewCandidate], list[ExcludedFileEntry]]:
    review_profile = review_profile or DEFAULT_REVIEW_PROFILE
    candidates: list[ScoredReviewCandidate] = []
    excluded: list[ExcludedFileEntry] = []
    repeated_callsite_paths = _detect_repeated_callsite_paths(manifest, review_profile)

    for entry in manifest.files:
        reasons: list[str] = []

        if entry.status.value == "deleted":
            excluded.append(ExcludedFileEntry(path=entry.path, reason=ExclusionReason.DELETED))
            continue
        if entry.is_rename_only:
            excluded.append(ExcludedFileEntry(path=entry.path, reason=ExclusionReason.RENAME_ONLY))
            continue
        if entry.is_lockfile:
            excluded.append(ExcludedFileEntry(path=entry.path, reason=ExclusionReason.LOCKFILE))
            continue
        if entry.is_generated:
            excluded.append(ExcludedFileEntry(path=entry.path, reason=ExclusionReason.GENERATED))
            continue
        if entry.is_docs and not is_reviewable_documentation(entry.path, review_profile):
            excluded.append(ExcludedFileEntry(path=entry.path, reason=ExclusionReason.DOCS))
            continue

        score = 0
        if entry.total_changes >= 200:
            score += 6
            reasons.append("large change set")
        elif entry.total_changes >= 80:
            score += 4
            reasons.append("medium change set")
        elif entry.total_changes >= 20:
            score += 2
            reasons.append("non-trivial change")

        if entry.status.value == "added":
            score += 3
            reasons.append("new file")

        if not entry.is_test:
            # Scoring rules describe production roles (viewmodels, utils, config
            # surfaces...). A test file matching them by name would inherit the
            # criticality of the code it tests; tests score on their own change
            # size plus the explicit test bonus below.
            for rule in matching_scoring_rules(entry.path, review_profile):
                score += rule.score_delta
                reasons.append(rule.reason)

        if entry.path in repeated_callsite_paths:
            score -= 2
            reasons.append("repeated call-site migration")

        if (
            entry.is_config
            and entry.total_changes <= review_profile.candidate_exclusions.low_signal_config_max_changes
        ):
            excluded.append(ExcludedFileEntry(path=entry.path, reason=ExclusionReason.LOW_SIGNAL_CONFIG))
            continue

        if entry.is_test and entry.total_changes <= review_profile.candidate_exclusions.low_signal_test_max_changes:
            excluded.append(ExcludedFileEntry(path=entry.path, reason=ExclusionReason.LOW_SIGNAL_TEST))
            continue
        if entry.is_test:
            score += 1
            reasons.append("test file with meaningful changes")

        if score <= 0:
            score = 1
            reasons.append("changed source file")

        if score >= 10:
            priority = FileReviewPriority.HIGH
            read_mode = FileReadMode.EXPANDED_HUNKS
        elif score >= 5:
            priority = FileReviewPriority.MEDIUM
            read_mode = FileReadMode.EXPANDED_HUNKS
        else:
            priority = FileReviewPriority.LOW
            read_mode = FileReadMode.HUNKS_ONLY

        candidates.append(
            ScoredReviewCandidate(
                path=entry.path,
                score=score,
                priority=priority,
                suggested_read_mode=read_mode,
                reasons=reasons,
            )
        )

    candidates.sort(key=lambda item: (item.score, item.priority == FileReviewPriority.HIGH), reverse=True)
    return candidates, excluded


def summarize_candidate_clusters(
    candidates: list[ScoredReviewCandidate],
    review_profile: ReviewProfile | None = None,
) -> list[dict]:
    """Build a compact summary of repeated candidate groups for planning prompts."""
    review_profile = review_profile or DEFAULT_REVIEW_PROFILE
    clusters: dict[str, list[ScoredReviewCandidate]] = {}
    for candidate in candidates:
        group = _candidate_group(candidate.path, review_profile)
        clusters.setdefault(group, []).append(candidate)

    summary: list[dict] = []
    for group, grouped_candidates in clusters.items():
        if len(grouped_candidates) < 3:
            continue
        summary.append(
            {
                "group": group,
                "count": len(grouped_candidates),
                "representatives": [candidate.path for candidate in grouped_candidates[:3]],
            }
        )
    summary.sort(key=lambda item: item["count"], reverse=True)
    return summary[:5]


def select_review_strategy(classification: PRClassification) -> ReviewStrategy:
    if classification.size_class == PRSizeClass.TINY:
        return ReviewStrategy(
            strategy=ReviewStrategyType.DIRECT_FINDINGS,
            size_class=classification.size_class,
            max_focus_files=4,
            max_prompt_chars=14000,
            max_comment_entries=8,
            batching_enabled=False,
            suspicious_empty_findings=False,
            reason="small enough for direct findings without planning overhead",
        )
    if classification.size_class == PRSizeClass.SMALL:
        return ReviewStrategy(
            strategy=ReviewStrategyType.DIRECT_FINDINGS,
            size_class=classification.size_class,
            max_focus_files=6,
            max_prompt_chars=22000,
            max_comment_entries=10,
            batching_enabled=False,
            suspicious_empty_findings=True,
            reason="limited scope; direct findings remain affordable",
        )
    if classification.size_class == PRSizeClass.MEDIUM:
        return ReviewStrategy(
            strategy=ReviewStrategyType.LIGHT_PLAN,
            size_class=classification.size_class,
            max_focus_files=8,
            max_prompt_chars=32000,
            max_comment_entries=10,
            batching_enabled=False,
            suspicious_empty_findings=True,
            reason="moderate PR size benefits from a lightweight focus plan",
        )
    if classification.size_class == PRSizeClass.LARGE:
        return ReviewStrategy(
            strategy=ReviewStrategyType.BATCHED_FINDINGS,
            size_class=classification.size_class,
            max_focus_files=8 if classification.is_repetitive_migration else 10,
            max_prompt_chars=18000 if classification.is_repetitive_migration else 24000,
            max_comment_entries=8,
            batching_enabled=True,
            suspicious_empty_findings=True,
            reason=(
                "repetitive migration pattern; prioritize shared helpers and representative call sites"
                if classification.is_repetitive_migration
                else "large PR requires batching to keep findings prompts bounded"
            ),
        )
    return ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=classification.size_class,
        max_focus_files=12,
        max_prompt_chars=18000,
        max_comment_entries=6,
        batching_enabled=True,
        suspicious_empty_findings=True,
        reason="very large PR requires strict batching and narrow prompt budgets",
    )


def build_deterministic_review_plan(
    candidates: list[ScoredReviewCandidate],
    excluded_files: list[ExcludedFileEntry],
    checklist: list[ReviewChecklistItem],
    strategy: ReviewStrategy,
    review_profile: ReviewProfile | None = None,
) -> ReviewPlan:
    review_profile = review_profile or DEFAULT_REVIEW_PROFILE
    focus_candidates = candidates[: strategy.max_focus_files]
    focus_files = [
        FileReviewPlan(
            path=candidate.path,
            priority=candidate.priority,
            read_mode=candidate.suggested_read_mode,
            reasons=candidate.reasons,
        )
        for candidate in focus_candidates
    ]

    review_axes = select_review_axes(checklist, focus_candidates, review_profile)
    trimmed_excluded = list(excluded_files)
    for candidate in candidates[strategy.max_focus_files :]:
        trimmed_excluded.append(
            ExcludedFileEntry(
                path=candidate.path,
                reason=ExclusionReason.BUDGET_TRIMMED,
                detail="outside deterministic focus limit",
            )
        )

    return ReviewPlan(
        focus_files=focus_files,
        review_axes=review_axes,
        extra_context_requests=[],
        excluded_files=trimmed_excluded,
    )


def _detect_repeated_callsite_paths(
    manifest: ChangeManifest,
    review_profile: ReviewProfile,
) -> set[str]:
    repeated: set[str] = set()
    callsite_like = [
        entry for entry in manifest.files
        if "repeated_callsite" in match_change_patterns(entry.path, review_profile) and entry.total_changes <= 20
    ]
    if len(callsite_like) < 4:
        return repeated
    repeated.update(entry.path for entry in callsite_like)
    return repeated


def _candidate_group(path: str, review_profile: ReviewProfile) -> str:
    matches = match_change_patterns(path, review_profile)
    if "central_behavior" in matches:
        return "central_behavior"
    if "entrypoint" in matches:
        return "entrypoint"
    if "repeated_callsite" in matches:
        return "repeated_callsite"
    return "other"
