"""
Baseline regression tests for `PromptBudgetManager`.

Pins the exact behavior extracted from the former free functions
`_content_budget()` (context_resolution_operations.py) and
`_fit_batch_to_budget()` (code_review_steps.py) so later heuristic changes
(worktree_reference cost penalty, per-batch limits) can be measured against
a known-good baseline.
"""

from titan_plugin_github.managers.prompt_budget_manager import (
    PromptBudgetManager,
    get_prompt_budget_manager,
)
from titan_plugin_github.models.review_enums import FileReadMode, PRSizeClass, ReviewStrategyType
from titan_plugin_github.models.review_models import FileContextEntry, FocusContextBatch, ReviewStrategy


def make_strategy(*, size_class: PRSizeClass, max_prompt_chars: int) -> ReviewStrategy:
    return ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=size_class,
        max_focus_files=10,
        max_prompt_chars=max_prompt_chars,
        max_comment_entries=5,
    )


def make_entry(path: str, *, chars: int, worktree_reference: bool = False) -> FileContextEntry:
    if worktree_reference:
        return FileContextEntry(
            path=path,
            read_mode=FileReadMode.WORKTREE_REFERENCE,
            worktree_reference=True,
            review_hint="Read this file from the worktree.",
            approximate_chars=chars,
        )
    return FileContextEntry(
        path=path,
        read_mode=FileReadMode.HUNKS_ONLY,
        hunks=["x" * chars],
        approximate_chars=chars,
    )


def make_batch(entries: dict[str, FileContextEntry], **overrides) -> FocusContextBatch:
    return FocusContextBatch(batch_id="batch_1", files_context=entries, **overrides)


# ---------------------------------------------------------------------------
# content_budget()
# ---------------------------------------------------------------------------


def test_content_budget_reserves_more_for_large_prs():
    manager = PromptBudgetManager()
    small_strategy = make_strategy(size_class=PRSizeClass.SMALL, max_prompt_chars=20000)
    large_strategy = make_strategy(size_class=PRSizeClass.LARGE, max_prompt_chars=20000)

    assert manager.content_budget(small_strategy) == 20000 - 3500
    assert manager.content_budget(large_strategy) == 20000 - 5000


def test_content_budget_never_goes_below_floor():
    manager = PromptBudgetManager()
    strategy = make_strategy(size_class=PRSizeClass.HUGE, max_prompt_chars=4000)

    assert manager.content_budget(strategy) == 2500


def test_get_prompt_budget_manager_returns_shared_instance():
    assert get_prompt_budget_manager() is get_prompt_budget_manager()


# ---------------------------------------------------------------------------
# estimate_entry_chars()
# ---------------------------------------------------------------------------


def test_estimate_entry_chars_uses_full_content_length():
    manager = PromptBudgetManager()
    entry = FileContextEntry(path="a.py", read_mode=FileReadMode.FULL_FILE, full_content="x" * 1234)

    assert manager.estimate_entry_chars(entry) == 1234


def test_estimate_entry_chars_sums_expanded_hunks():
    manager = PromptBudgetManager()
    entry = FileContextEntry(
        path="a.py", read_mode=FileReadMode.EXPANDED_HUNKS, expanded_hunks=["x" * 100, "y" * 50]
    )

    assert manager.estimate_entry_chars(entry) == 150


def test_estimate_entry_chars_sums_hunks():
    manager = PromptBudgetManager()
    entry = FileContextEntry(path="a.py", read_mode=FileReadMode.HUNKS_ONLY, hunks=["x" * 100, "y" * 50])

    assert manager.estimate_entry_chars(entry) == 150


def test_estimate_entry_chars_penalizes_worktree_reference_regardless_of_hint_size():
    manager = PromptBudgetManager()
    entry = FileContextEntry(
        path="a.py", read_mode=FileReadMode.WORKTREE_REFERENCE, worktree_reference=True, review_hint="short"
    )

    assert manager.estimate_entry_chars(entry) == PromptBudgetManager.WORKTREE_REFERENCE_ESTIMATED_CHARS
    assert manager.estimate_entry_chars(entry) > 800


def test_estimate_entry_chars_returns_zero_for_empty_entry():
    manager = PromptBudgetManager()
    entry = FileContextEntry(path="a.py")

    assert manager.estimate_entry_chars(entry) == 0


# ---------------------------------------------------------------------------
# fit_batch_to_budget()
# ---------------------------------------------------------------------------


def test_fit_batch_within_budget_is_unchanged():
    manager = PromptBudgetManager()
    batch = make_batch({"a.py": make_entry("a.py", chars=100)})
    prompt_parts = {"prompt": "x" * 100}

    fitted, changed = manager.fit_batch_to_budget(batch, prompt_parts, budget_chars=1000)

    assert changed is False
    assert len(fitted) == 1
    assert fitted[0].batch_id == "batch_1"
    assert fitted[0].prompt_actual_chars == 100


def test_fit_batch_splits_multi_file_batch_in_half():
    manager = PromptBudgetManager()
    batch = make_batch(
        {
            "a.py": make_entry("a.py", chars=100),
            "b.py": make_entry("b.py", chars=100),
            "c.py": make_entry("c.py", chars=100),
            "d.py": make_entry("d.py", chars=100),
        }
    )
    prompt_parts = {"prompt": "x" * 5000}

    fitted, changed = manager.fit_batch_to_budget(batch, prompt_parts, budget_chars=1000)

    assert changed is True
    assert len(fitted) == 2
    assert fitted[0].batch_id == "batch_1a"
    assert fitted[1].batch_id == "batch_1b"
    assert list(fitted[0].files_context.keys()) == ["a.py", "b.py"]
    assert list(fitted[1].files_context.keys()) == ["c.py", "d.py"]
    assert fitted[0].degraded_context is True
    assert fitted[1].degraded_context is True


def test_fit_batch_degrades_single_file_to_worktree_reference():
    manager = PromptBudgetManager()
    batch = make_batch({"a.py": make_entry("a.py", chars=100)})
    prompt_parts = {"prompt": "x" * 5000}

    fitted, changed = manager.fit_batch_to_budget(batch, prompt_parts, budget_chars=1000)

    assert changed is True
    assert len(fitted) == 1
    entry = fitted[0].files_context["a.py"]
    assert entry.worktree_reference is True
    assert entry.read_mode == FileReadMode.WORKTREE_REFERENCE
    assert entry.full_content is None
    assert entry.approximate_chars <= 800
    assert fitted[0].degraded_context is True


def test_fit_batch_drops_related_files_when_only_worktree_reference_left():
    manager = PromptBudgetManager()
    batch = make_batch(
        {"a.py": make_entry("a.py", chars=100, worktree_reference=True)},
        related_files={"b.py": "some related content"},
    )
    prompt_parts = {"prompt": "x" * 5000}

    fitted, changed = manager.fit_batch_to_budget(batch, prompt_parts, budget_chars=1000)

    assert changed is True
    assert fitted[0].related_files == {}
    assert fitted[0].degraded_context is True


def test_fit_batch_drops_comment_context_when_related_files_already_empty():
    from titan_plugin_github.models.review_enums import CommentContextKind
    from titan_plugin_github.models.review_models import CommentContextEntry

    manager = PromptBudgetManager()
    batch = make_batch(
        {"a.py": make_entry("a.py", chars=100, worktree_reference=True)},
        comment_context=[
            CommentContextEntry(kind=CommentContextKind.COMMENT, thread_id="t1", path="a.py", summary="hi")
        ],
    )
    prompt_parts = {"prompt": "x" * 5000}

    fitted, changed = manager.fit_batch_to_budget(batch, prompt_parts, budget_chars=1000)

    assert changed is True
    assert fitted[0].comment_context == []
    assert fitted[0].degraded_context is True


def test_fit_batch_marks_oversized_when_nothing_left_to_trim():
    manager = PromptBudgetManager()
    batch = make_batch({"a.py": make_entry("a.py", chars=100, worktree_reference=True)})
    prompt_parts = {"prompt": "x" * 5000}

    fitted, changed = manager.fit_batch_to_budget(batch, prompt_parts, budget_chars=1000)

    assert changed is False
    assert len(fitted) == 1
    assert fitted[0].prompt_still_too_large is True
    assert fitted[0].prompt_actual_chars == 5000
    assert fitted[0].degraded_context is True
