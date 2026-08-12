"""Validators and deduplication logic for the code review system."""

from difflib import SequenceMatcher

from .review_enums import ChecklistCategory, ContextRequestType
from .review_models import (
    ChangeManifest,
    ExistingCommentIndexEntry,
    Finding,
    ReviewPlan,
)

MAX_EXTRA_CONTEXT_REQUESTS = 3

_ALL_CHECKLIST_IDS: frozenset[str] = frozenset(c.value for c in ChecklistCategory)


class ReviewPlanValidator:
    """Semantic validator for focused review plans."""

    def __init__(
        self,
        change_manifest: ChangeManifest,
        offered_checklist_ids: frozenset[str] | None = None,
    ):
        self.manifest = change_manifest
        self.offered_checklist_ids = (
            _ALL_CHECKLIST_IDS if offered_checklist_ids is None else offered_checklist_ids
        )

    def sanitize(self, plan: ReviewPlan) -> tuple[ReviewPlan, list[str]]:
        """Drop invalid entries from the plan, one warning per dropped entry.

        Every plan list is advisory entry-by-entry: one hallucinated path in a
        12-file plan should cost that entry, not the model's whole selection.
        Discarding the full plan is the caller's decision, reserved for the one
        genuinely fatal outcome — no valid focus file survives (see
        ``validate_semantically``).
        """
        warnings: list[str] = []
        manifest_paths = {f.path for f in self.manifest.files}

        focus_files = []
        seen_focus: set[str] = set()
        for file_plan in plan.focus_files:
            if file_plan.path not in manifest_paths:
                warnings.append(f"Focus path not in PR, dropped: {file_plan.path}")
                continue
            if file_plan.path in seen_focus:
                warnings.append(f"Duplicate focus file, dropped: {file_plan.path}")
                continue
            seen_focus.add(file_plan.path)
            focus_files.append(file_plan)

        allowed_context_types = {
            ContextRequestType.RELATED_TESTS,
            ContextRequestType.RELATED_CONTEXT,
        }
        context_requests = []
        for req in plan.extra_context_requests:
            if req.type not in allowed_context_types:
                warnings.append(f"Invalid context type, request dropped: {req.type}")
                continue
            if req.for_path not in manifest_paths:
                warnings.append(f"Context request path not in PR, dropped: {req.for_path}")
                continue
            context_requests.append(req)
        if len(context_requests) > MAX_EXTRA_CONTEXT_REQUESTS:
            warnings.append(
                f"Too many context requests, keeping first {MAX_EXTRA_CONTEXT_REQUESTS} "
                f"of {len(context_requests)}"
            )
            context_requests = context_requests[:MAX_EXTRA_CONTEXT_REQUESTS]

        review_axes = []
        for item_id in plan.review_axes:
            if item_id not in self.offered_checklist_ids:
                warnings.append(f"Unknown checklist item, dropped: {item_id}")
                continue
            review_axes.append(item_id)

        excluded_files = []
        for excluded in plan.excluded_files:
            if excluded.path not in manifest_paths:
                warnings.append(f"Excluded path not in PR, dropped: {excluded.path}")
                continue
            if excluded.path in seen_focus:
                warnings.append(
                    f"Path both focused and excluded, keeping focus: {excluded.path}"
                )
                continue
            excluded_files.append(excluded)

        if not warnings:
            return plan, []
        return (
            plan.model_copy(
                update={
                    "focus_files": focus_files,
                    "extra_context_requests": context_requests,
                    "review_axes": review_axes,
                    "excluded_files": excluded_files,
                }
            ),
            warnings,
        )

    def validate_semantically(self, plan: ReviewPlan) -> tuple[bool, list[str]]:
        """Fatal-only check, meant to run on a sanitized plan."""
        if not plan.focus_files:
            return False, ["Plan has no valid focus_files"]
        return True, []


def is_duplicate(
    new_finding: Finding,
    existing: ExistingCommentIndexEntry,
    line_proximity_window: int = 5,
    title_similarity_threshold: float = 0.75,
) -> bool:
    """Return True if a finding likely duplicates an existing comment."""

    if new_finding.path != existing.path:
        return False

    if not _lines_are_close(new_finding.line, existing.line, line_proximity_window):
        return False

    similarity = SequenceMatcher(
        None,
        new_finding.title.lower(),
        existing.title.lower(),
    ).ratio()

    same_category = new_finding.category.lower() == (existing.category or "").lower()
    if same_category and not existing.is_resolved:
        return True

    if existing.is_adjudicated and similarity > 0.58:
        return True

    return similarity > title_similarity_threshold


def _lines_are_close(line_a: int | None, line_b: int | None, window: int) -> bool:
    if line_a is None and line_b is None:
        return True
    if line_a is None or line_b is None:
        return False
    return abs(line_a - line_b) <= window
