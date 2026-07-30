"""
Baseline regression test proving `build_review_context_package()` batches files
according to `PromptBudgetManager.content_budget()` (review-batching-003
extraction). Guards against silently reverting to the old inline
`_content_budget()` free function.
"""

from titan_plugin_github.managers.prompt_budget_manager import get_prompt_budget_manager
from titan_plugin_github.models.review_enums import (
    ChecklistCategory,
    ContextRequestType,
    FileChangeStatus,
    FileReadMode,
    FileReviewPriority,
    PRSizeClass,
    ReviewStrategyType,
)
from titan_plugin_github.models.review_models import (
    ChangeManifest,
    ChangedFileEntry,
    ContextRequest,
    FileReviewPlan,
    PullRequestManifest,
    ReviewChecklistItem,
    ReviewPlan,
    ReviewStrategy,
)
from titan_plugin_github.operations.context_resolution_operations import (
    build_review_context_package,
    resolve_file_read_access,
)


def make_diff(path: str, added_line: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index abc..def 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,1 +1,2 @@\n"
        f" context line\n"
        f"+{added_line}\n"
    )


def make_manifest(paths: list[str]) -> ChangeManifest:
    files = [
        ChangedFileEntry(path=path, status=FileChangeStatus.MODIFIED, additions=1, deletions=0) for path in paths
    ]
    return ChangeManifest(
        pr=PullRequestManifest(number=1, title="Test PR", base="main", head="feat/test", author="alex", description=""),
        files=files,
        total_additions=len(files),
        total_deletions=0,
    )


def test_build_review_context_package_batches_by_manager_content_budget():
    paths = ["a.py", "b.py", "c.py"]
    diff = "".join(make_diff(path, "x" * 3000) for path in paths)
    plan = ReviewPlan(
        focus_files=[
            FileReviewPlan(path=path, priority=FileReviewPriority.HIGH, read_mode=FileReadMode.HUNKS_ONLY)
            for path in paths
        ],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS],
    )
    manifest = make_manifest(paths)
    checklist = [
        ReviewChecklistItem(
            id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
            name="Functional correctness",
            description="Does it work",
        )
    ]
    strategy = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=4000,
        max_comment_entries=5,
        batching_enabled=True,
    )

    package = build_review_context_package(plan, diff, manifest, checklist, comment_context=[], strategy=strategy)

    # content_budget(strategy) == max(2500, 4000 - 3500) == 2500; each ~3000-char
    # hunk alone exceeds that budget, so every file must land in its own batch.
    assert len(package.batches) == 3
    assert [batch.batch_id for batch in package.batches] == ["batch_1", "batch_2", "batch_3"]
    assert [list(batch.files_context.keys()) for batch in package.batches] == [["a.py"], ["b.py"], ["c.py"]]


def test_build_review_context_package_keeps_small_files_in_one_batch():
    paths = ["a.py", "b.py", "c.py"]
    diff = "".join(make_diff(path, "x" * 10) for path in paths)
    plan = ReviewPlan(
        focus_files=[
            FileReviewPlan(path=path, priority=FileReviewPriority.HIGH, read_mode=FileReadMode.HUNKS_ONLY)
            for path in paths
        ],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS],
    )
    manifest = make_manifest(paths)
    checklist = [
        ReviewChecklistItem(
            id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
            name="Functional correctness",
            description="Does it work",
        )
    ]
    strategy = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=20000,
        max_comment_entries=5,
        batching_enabled=True,
    )

    package = build_review_context_package(plan, diff, manifest, checklist, comment_context=[], strategy=strategy)

    assert len(package.batches) == 1
    assert set(package.batches[0].files_context.keys()) == set(paths)


def test_worktree_reference_entries_get_a_high_fixed_cost_and_split_batches():
    """review-batching-004: worktree_reference used to cost ~800 chars, cheap enough that
    several of them fit in one batch even though the CLI must read each file for real from
    the worktree. Now they carry a fixed high cost, so they no longer group together under a
    budget that would have fit them at the old estimate."""
    paths = ["a.py", "b.py"]
    diff = "".join(make_diff(path, "x" * 10) for path in paths)
    plan = ReviewPlan(
        focus_files=[
            FileReviewPlan(path=path, priority=FileReviewPriority.HIGH, read_mode=FileReadMode.WORKTREE_REFERENCE)
            for path in paths
        ],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS],
    )
    manifest = make_manifest(paths)
    checklist = [
        ReviewChecklistItem(
            id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
            name="Functional correctness",
            description="Does it work",
        )
    ]
    # Budget that would have fit two ~800-char entries (old estimate) but not two
    # WORKTREE_REFERENCE_ESTIMATED_CHARS-sized ones.
    strategy = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=2000 + 3500,
        max_comment_entries=5,
        batching_enabled=True,
    )

    package = build_review_context_package(plan, diff, manifest, checklist, comment_context=[], strategy=strategy)

    first_entry = package.batches[0].files_context["a.py"]
    assert first_entry.worktree_reference is True
    assert first_entry.approximate_chars == get_prompt_budget_manager().WORKTREE_REFERENCE_ESTIMATED_CHARS
    assert len(package.batches) == 2
    assert list(package.batches[0].files_context.keys()) == ["a.py"]
    assert list(package.batches[1].files_context.keys()) == ["b.py"]


def test_worktree_reference_files_are_capped_at_one_per_batch_even_with_ample_budget():
    """review-batching-005: even when the char budget alone would fit several
    worktree_reference files in one batch, at most one is allowed per batch — each
    additional one forces a new batch, since every worktree_reference file means another
    full file read by the CLI regardless of prompt size."""
    paths = ["a.py", "b.py", "c.py"]
    diff = "".join(make_diff(path, "x" * 10) for path in paths)
    plan = ReviewPlan(
        focus_files=[
            FileReviewPlan(path=path, priority=FileReviewPriority.HIGH, read_mode=FileReadMode.WORKTREE_REFERENCE)
            for path in paths
        ],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS],
    )
    manifest = make_manifest(paths)
    checklist = [
        ReviewChecklistItem(
            id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
            name="Functional correctness",
            description="Does it work",
        )
    ]
    strategy = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=100_000,
        max_comment_entries=5,
        batching_enabled=True,
    )

    package = build_review_context_package(plan, diff, manifest, checklist, comment_context=[], strategy=strategy)

    assert len(package.batches) == 3
    assert [list(batch.files_context.keys()) for batch in package.batches] == [["a.py"], ["b.py"], ["c.py"]]


def test_mixed_batch_closes_before_a_second_worktree_reference_file():
    """A batch may hold inline files plus one worktree_reference file, but a second
    worktree_reference file must start a new batch even though the char budget has room."""
    plan = ReviewPlan(
        focus_files=[
            FileReviewPlan(path="inline.py", priority=FileReviewPriority.HIGH, read_mode=FileReadMode.HUNKS_ONLY),
            FileReviewPlan(path="a.py", priority=FileReviewPriority.HIGH, read_mode=FileReadMode.WORKTREE_REFERENCE),
            FileReviewPlan(path="b.py", priority=FileReviewPriority.HIGH, read_mode=FileReadMode.WORKTREE_REFERENCE),
        ],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS],
    )
    diff = "".join(make_diff(path, "x" * 10) for path in ["inline.py", "a.py", "b.py"])
    manifest = make_manifest(["inline.py", "a.py", "b.py"])
    checklist = [
        ReviewChecklistItem(
            id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
            name="Functional correctness",
            description="Does it work",
        )
    ]
    strategy = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=100_000,
        max_comment_entries=5,
        batching_enabled=True,
    )

    package = build_review_context_package(plan, diff, manifest, checklist, comment_context=[], strategy=strategy)

    assert len(package.batches) == 2
    assert list(package.batches[0].files_context.keys()) == ["inline.py", "a.py"]
    assert list(package.batches[1].files_context.keys()) == ["b.py"]


# ---------------------------------------------------------------------------
# File-read access: never pair the PR's diff with another revision's file content
# ---------------------------------------------------------------------------

HEAD_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class TestResolveFileReadAccess:
    def test_worktree_is_always_trusted(self):
        access = resolve_file_read_access("/tmp/titan-review-1")

        assert access.allowed is True
        assert access.source == "worktree"

    def test_worktree_does_not_need_sha_verification(self):
        """The worktree is checked out at the PR ref, so a mismatching local
        checkout is irrelevant."""
        access = resolve_file_read_access(
            "/tmp/titan-review-1", head_sha=HEAD_SHA, checkout_sha=OTHER_SHA, checkout_dirty=True
        )

        assert access.allowed is True

    def test_clean_checkout_at_head_is_trusted(self):
        access = resolve_file_read_access(
            None, head_sha=HEAD_SHA, checkout_sha=HEAD_SHA, checkout_dirty=False
        )

        assert access.allowed is True
        assert access.source == "checkout"

    def test_checkout_on_another_revision_is_rejected(self):
        """The bug this guards: worktree creation failed, the user is on another
        branch, and full-file reads would review code that is not in the PR."""
        access = resolve_file_read_access(
            None, head_sha=HEAD_SHA, checkout_sha=OTHER_SHA, checkout_dirty=False
        )

        assert access.allowed is False
        assert access.source == "none"
        assert "aaaaaaaa" in access.reason and "bbbbbbbb" in access.reason

    def test_dirty_checkout_at_head_is_rejected(self):
        access = resolve_file_read_access(
            None, head_sha=HEAD_SHA, checkout_sha=HEAD_SHA, checkout_dirty=True
        )

        assert access.allowed is False
        assert "uncommitted" in access.reason

    def test_unknown_checkout_sha_is_rejected(self):
        access = resolve_file_read_access(None, head_sha=HEAD_SHA, checkout_sha=None)

        assert access.allowed is False

    def test_unknown_head_sha_is_rejected(self):
        access = resolve_file_read_access(None, head_sha=None, checkout_sha=HEAD_SHA)

        assert access.allowed is False

    def test_no_information_at_all_is_rejected(self):
        assert resolve_file_read_access(None).allowed is False


def _single_file_setup(read_mode, path="a.py"):
    diff = make_diff(path, "added_line = 1")
    plan = ReviewPlan(
        focus_files=[
            FileReviewPlan(path=path, priority=FileReviewPriority.HIGH, read_mode=read_mode)
        ],
        review_axes=[ChecklistCategory.FUNCTIONAL_CORRECTNESS],
    )
    checklist = [
        ReviewChecklistItem(
            id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
            name="Functional correctness",
            description="Does it work",
        )
    ]
    strategy = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=100_000,
        max_comment_entries=5,
        batching_enabled=True,
    )
    return diff, plan, make_manifest([path]), checklist, strategy


class TestBuildPackageWithoutFileReads:
    def test_full_file_degrades_to_hunks_only(self, tmp_path):
        """A real file exists at cwd, but it is the wrong revision — it must be ignored."""
        (tmp_path / "a.py").write_text("content from the wrong branch\n" * 5)
        diff, plan, manifest, checklist, strategy = _single_file_setup(FileReadMode.FULL_FILE)

        package = build_review_context_package(
            plan, diff, manifest, checklist,
            comment_context=[], strategy=strategy,
            cwd=str(tmp_path), allow_file_reads=False,
        )

        entry = package.batches[0].files_context["a.py"]
        assert entry.read_mode == FileReadMode.HUNKS_ONLY
        assert entry.full_content is None
        assert "wrong branch" not in "".join(entry.hunks)

    def test_expanded_hunks_degrades_to_hunks_only(self, tmp_path):
        (tmp_path / "a.py").write_text("content from the wrong branch\n" * 5)
        diff, plan, manifest, checklist, strategy = _single_file_setup(FileReadMode.EXPANDED_HUNKS)

        package = build_review_context_package(
            plan, diff, manifest, checklist,
            comment_context=[], strategy=strategy,
            cwd=str(tmp_path), allow_file_reads=False,
        )

        entry = package.batches[0].files_context["a.py"]
        assert entry.read_mode == FileReadMode.HUNKS_ONLY
        assert entry.expanded_hunks == []

    def test_full_file_is_used_when_reads_are_allowed(self, tmp_path):
        (tmp_path / "a.py").write_text("verified content\n")
        diff, plan, manifest, checklist, strategy = _single_file_setup(FileReadMode.FULL_FILE)

        package = build_review_context_package(
            plan, diff, manifest, checklist,
            comment_context=[], strategy=strategy,
            cwd=str(tmp_path), allow_file_reads=True,
        )

        entry = package.batches[0].files_context["a.py"]
        assert entry.read_mode == FileReadMode.FULL_FILE
        assert entry.full_content == "verified content\n"

    def test_never_falls_back_to_worktree_reference(self):
        """worktree_reference has the CLI read the file itself — the same
        wrong-revision read, just delegated."""
        path = "big.py"
        diff, plan, manifest, checklist, strategy = _single_file_setup(
            FileReadMode.FULL_FILE, path=path
        )
        # Oversized hunk: normally this ends up as a worktree_reference entry.
        diff = make_diff(path, "x" * 40_000)

        package = build_review_context_package(
            plan, diff, manifest, checklist,
            comment_context=[], strategy=strategy,
            allow_file_reads=False,
        )

        entry = package.batches[0].files_context[path]
        assert entry.worktree_reference is False
        assert entry.read_mode == FileReadMode.HUNKS_ONLY

    def test_file_absent_from_diff_gets_headers_only_with_a_hint(self):
        diff, plan, manifest, checklist, strategy = _single_file_setup(
            FileReadMode.FULL_FILE, path="in_plan.py"
        )
        diff = make_diff("something_else.py", "y = 2")

        package = build_review_context_package(
            plan, diff, manifest, checklist,
            comment_context=[], strategy=strategy,
            allow_file_reads=False,
        )

        entry = package.batches[0].files_context["in_plan.py"]
        assert entry.worktree_reference is False
        assert entry.hunks == []
        assert "not at this PR's head commit" in entry.review_hint

    def test_related_context_requests_are_skipped(self, tmp_path):
        (tmp_path / "test_a.py").write_text("def test_something(): pass\n")
        diff, plan, manifest, checklist, strategy = _single_file_setup(FileReadMode.HUNKS_ONLY)
        plan = ReviewPlan(
            focus_files=plan.focus_files,
            review_axes=plan.review_axes,
            extra_context_requests=[
                ContextRequest(type=ContextRequestType.RELATED_TESTS, for_path="a.py")
            ],
        )

        package = build_review_context_package(
            plan, diff, manifest, checklist,
            comment_context=[], strategy=strategy,
            cwd=str(tmp_path), allow_file_reads=False,
        )

        assert package.batches[0].related_files == {}
