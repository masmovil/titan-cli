from titan_plugin_github.models.review_enums import (
    ChecklistCategory,
    ExclusionReason,
    FileReadMode,
    FileReviewPriority,
)
from titan_plugin_github.models.review_models import (
    ChangeManifest,
    ChangedFileEntry,
    ExcludedFileEntry,
    FileReviewPlan,
    PullRequestManifest,
    ReviewPlan,
)
from titan_plugin_github.models.validators import ReviewPlanValidator


def _make_manifest(paths: list[str] | None = None) -> ChangeManifest:
    return ChangeManifest(
        pr=PullRequestManifest(
            number=1,
            title="Test PR",
            base="main",
            head="feat/test",
            author="alex",
            description="Body",
        ),
        files=[
            ChangedFileEntry(path=path, status="modified", additions=10, deletions=2)
            for path in (paths or [])
        ],
        total_additions=0,
        total_deletions=0,
    )


def _focus(path: str) -> FileReviewPlan:
    return FileReviewPlan(
        path=path, priority=FileReviewPriority.HIGH, read_mode=FileReadMode.HUNKS_ONLY
    )


def test_validator_uses_all_checklist_ids_when_none_is_passed():
    validator = ReviewPlanValidator(_make_manifest(), offered_checklist_ids=None)

    assert "functional_correctness" in validator.offered_checklist_ids
    assert "error_handling" in validator.offered_checklist_ids


def test_validator_preserves_explicit_empty_checklist_ids():
    validator = ReviewPlanValidator(_make_manifest(), offered_checklist_ids=frozenset())

    assert validator.offered_checklist_ids == frozenset()


def test_sanitize_returns_valid_plan_untouched():
    validator = ReviewPlanValidator(_make_manifest(["src/a.py", "src/b.py"]))
    plan = ReviewPlan(
        focus_files=[_focus("src/a.py")],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS],
        excluded_files=[
            ExcludedFileEntry(path="src/b.py", reason=ExclusionReason.LOW_SIGNAL_TEST)
        ],
    )

    sanitized, warnings = validator.sanitize(plan)

    assert warnings == []
    assert sanitized is plan


def test_sanitize_drops_invalid_excluded_entry_and_keeps_the_ai_plan():
    """One hallucinated EXCLUDED path (advisory data) must cost that entry only,
    never the model's whole focus selection."""
    validator = ReviewPlanValidator(_make_manifest(["src/a.py"]))
    plan = ReviewPlan(
        focus_files=[_focus("src/a.py")],
        excluded_files=[
            ExcludedFileEntry(path="src/not_in_pr.py", reason=ExclusionReason.DOCS)
        ],
    )

    sanitized, warnings = validator.sanitize(plan)
    is_valid, errors = validator.validate_semantically(sanitized)

    assert is_valid and errors == []
    assert [f.path for f in sanitized.focus_files] == ["src/a.py"]
    assert sanitized.excluded_files == []
    assert any("Excluded path not in PR" in w for w in warnings)


def test_sanitize_drops_invalid_and_duplicate_focus_entries_keeping_valid_ones():
    validator = ReviewPlanValidator(_make_manifest(["src/a.py", "src/b.py"]))
    plan = ReviewPlan(
        focus_files=[_focus("src/a.py"), _focus("src/ghost.py"), _focus("src/a.py"), _focus("src/b.py")],
    )

    sanitized, warnings = validator.sanitize(plan)

    assert [f.path for f in sanitized.focus_files] == ["src/a.py", "src/b.py"]
    assert any("Focus path not in PR" in w for w in warnings)
    assert any("Duplicate focus file" in w for w in warnings)


def test_sanitize_drops_unknown_axes_and_conflicting_exclusions():
    validator = ReviewPlanValidator(
        _make_manifest(["src/a.py"]),
        offered_checklist_ids=frozenset({"functional_correctness"}),
    )
    plan = ReviewPlan(
        focus_files=[_focus("src/a.py")],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS, ChecklistCategory.SECURITY],
        excluded_files=[
            ExcludedFileEntry(path="src/a.py", reason=ExclusionReason.DOCS)
        ],
    )

    sanitized, warnings = validator.sanitize(plan)

    assert sanitized.review_axes == [ChecklistCategory.FUNCTIONAL_CORRECTNESS]
    # A path both focused and excluded keeps its focus (excluded entry dropped).
    assert sanitized.excluded_files == []
    assert [f.path for f in sanitized.focus_files] == ["src/a.py"]
    assert any("Unknown checklist item" in w for w in warnings)
    assert any("both focused and excluded" in w for w in warnings)


def test_validate_semantically_fails_only_when_no_focus_survives():
    validator = ReviewPlanValidator(_make_manifest(["src/a.py"]))
    plan = ReviewPlan(focus_files=[_focus("src/ghost.py")])

    sanitized, warnings = validator.sanitize(plan)
    is_valid, errors = validator.validate_semantically(sanitized)

    assert sanitized.focus_files == []
    assert is_valid is False
    assert errors == ["Plan has no valid focus_files"]
