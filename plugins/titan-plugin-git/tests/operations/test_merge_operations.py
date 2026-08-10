"""
Tests for Merge Operations

Tests for pure business logic related to merging branches.
"""

from titan_plugin_git.models.view.merge import MergeStatus, UIMergeResult
from titan_plugin_git.operations.merge_operations import (
    build_conflict_resolution_prompt,
    build_merge_ref,
    classify_merge_result,
    format_merge_summary,
    has_conflict_markers,
    resolve_merge_source,
)


class TestResolveMergeSource:
    """Tests for resolve_merge_source function."""

    def test_explicit_branch_wins(self):
        """Should use the explicit branch when provided."""
        source, reason = resolve_merge_source(
            explicit_branch="develop",
            main_branch="main",
            current_branch="feature/x"
        )
        assert source == "develop"
        assert reason is None

    def test_falls_back_to_main_branch(self):
        """Should fall back to the configured base branch."""
        source, reason = resolve_merge_source(
            explicit_branch=None,
            main_branch="main",
            current_branch="feature/x"
        )
        assert source == "main"
        assert reason is None

    def test_empty_string_falls_back_to_main_branch(self):
        """Should treat an empty param as 'not provided'."""
        source, reason = resolve_merge_source(
            explicit_branch="   ",
            main_branch="develop",
            current_branch="feature/x"
        )
        assert source == "develop"
        assert reason is None

    def test_no_source_and_no_main_branch(self):
        """Should report a reason when nothing can be resolved."""
        source, reason = resolve_merge_source(
            explicit_branch="",
            main_branch="",
            current_branch="feature/x"
        )
        assert source is None
        assert reason is not None

    def test_rejects_merging_branch_into_itself(self):
        """Should reject merging the current branch into itself."""
        source, reason = resolve_merge_source(
            explicit_branch="main",
            main_branch="main",
            current_branch="main"
        )
        assert source is None
        assert "itself" in reason

    def test_rejects_implicit_self_merge(self):
        """Should reject the fallback too when it equals the current branch."""
        source, reason = resolve_merge_source(
            explicit_branch=None,
            main_branch="develop",
            current_branch="develop"
        )
        assert source is None
        assert reason is not None


class TestBuildMergeRef:
    """Tests for build_merge_ref function."""

    def test_builds_remote_tracking_ref(self):
        """Should prefix the branch with the remote."""
        assert build_merge_ref("develop", "origin") == "origin/develop"

    def test_custom_remote(self):
        """Should honor a non-default remote."""
        assert build_merge_ref("develop", "upstream") == "upstream/develop"

    def test_no_remote_returns_plain_branch(self):
        """Should return the bare branch when no remote is given."""
        assert build_merge_ref("develop", "") == "develop"


class TestClassifyMergeResult:
    """Tests for classify_merge_result function."""

    def test_conflicted_files_win_over_head_movement(self):
        """Should report CONFLICTED whenever unmerged paths exist."""
        status = classify_merge_result(
            head_before="aaa",
            head_after="bbb",
            has_second_parent=False,
            conflicted_files=["src/app.py"],
            merge_in_progress=False
        )
        assert status == MergeStatus.CONFLICTED

    def test_merge_head_alone_means_conflicted(self):
        """Should report CONFLICTED when MERGE_HEAD exists."""
        status = classify_merge_result(
            head_before="aaa",
            head_after="aaa",
            has_second_parent=False,
            conflicted_files=[],
            merge_in_progress=True
        )
        assert status == MergeStatus.CONFLICTED

    def test_unchanged_head_is_up_to_date(self):
        """Should report UP_TO_DATE when the merge moved nothing."""
        status = classify_merge_result(
            head_before="aaa",
            head_after="aaa",
            has_second_parent=False,
            conflicted_files=[],
            merge_in_progress=False
        )
        assert status == MergeStatus.UP_TO_DATE

    def test_moved_head_without_second_parent_is_fast_forward(self):
        """Should report FAST_FORWARD when HEAD moved to a non-merge commit."""
        status = classify_merge_result(
            head_before="aaa",
            head_after="bbb",
            has_second_parent=False,
            conflicted_files=[],
            merge_in_progress=False
        )
        assert status == MergeStatus.FAST_FORWARD

    def test_second_parent_means_merge_commit(self):
        """Should report MERGED when the new HEAD is a merge commit."""
        status = classify_merge_result(
            head_before="aaa",
            head_after="bbb",
            has_second_parent=True,
            conflicted_files=[],
            merge_in_progress=False
        )
        assert status == MergeStatus.MERGED

    def test_ignores_localized_git_output(self):
        """Should not depend on git's message language at all."""
        # Same repo state classified twice; no output is involved
        assert classify_merge_result("aaa", "aaa", False, [], False) == MergeStatus.UP_TO_DATE
        assert classify_merge_result("aaa", "bbb", True, [], False) == MergeStatus.MERGED


class TestBuildConflictResolutionPrompt:
    """Tests for build_conflict_resolution_prompt function."""

    def test_lists_every_conflicted_file(self):
        """Should mention each conflicted path."""
        prompt = build_conflict_resolution_prompt(
            conflicted_files=["src/a.py", "src/b.py"],
            source_ref="origin/develop",
            target_branch="feature/x"
        )
        assert "src/a.py" in prompt
        assert "src/b.py" in prompt

    def test_mentions_both_refs(self):
        """Should state what is being merged into what."""
        prompt = build_conflict_resolution_prompt(
            conflicted_files=["src/a.py"],
            source_ref="origin/develop",
            target_branch="feature/x"
        )
        assert "origin/develop" in prompt
        assert "feature/x" in prompt

    def test_tells_cli_not_to_commit(self):
        """Should instruct the CLI to leave the merge uncommitted."""
        prompt = build_conflict_resolution_prompt(
            conflicted_files=["src/a.py"],
            source_ref="origin/develop",
            target_branch="feature/x"
        )
        assert "git commit" in prompt


class TestFormatMergeSummary:
    """Tests for format_merge_summary function."""

    def _result(self, status, conflicted_files=None):
        return UIMergeResult(
            status=status,
            source_ref="origin/develop",
            target_branch="feature/x",
            conflicted_files=conflicted_files or [],
        )

    def test_header_shows_direction(self):
        """Should lead with source → target."""
        lines = format_merge_summary(self._result(MergeStatus.MERGED))
        assert lines[0] == "origin/develop → feature/x"

    def test_up_to_date(self):
        """Should describe a no-op merge."""
        lines = format_merge_summary(self._result(MergeStatus.UP_TO_DATE))
        assert "up to date" in lines[1].lower()

    def test_fast_forward(self):
        """Should describe a fast-forward."""
        lines = format_merge_summary(self._result(MergeStatus.FAST_FORWARD))
        assert "fast-forward" in lines[1].lower()

    def test_conflicts_singular(self):
        """Should use the singular noun for one conflicted file."""
        lines = format_merge_summary(
            self._result(MergeStatus.CONFLICTED, ["a.py"])
        )
        assert "1 file" in lines[1]

    def test_conflicts_plural(self):
        """Should use the plural noun for several conflicted files."""
        lines = format_merge_summary(
            self._result(MergeStatus.CONFLICTED, ["a.py", "b.py"])
        )
        assert "2 files" in lines[1]


class TestUIMergeResultFlags:
    """Tests for the convenience flags on UIMergeResult."""

    def test_has_conflicts(self):
        """Should be True only for a conflicted merge."""
        conflicted = UIMergeResult(
            status=MergeStatus.CONFLICTED,
            source_ref="origin/develop",
            target_branch="feature/x"
        )
        clean = UIMergeResult(
            status=MergeStatus.MERGED,
            source_ref="origin/develop",
            target_branch="feature/x"
        )
        assert conflicted.has_conflicts is True
        assert clean.has_conflicts is False

    def test_created_commit(self):
        """Should be True only when a merge commit was made."""
        merged = UIMergeResult(
            status=MergeStatus.MERGED,
            source_ref="origin/develop",
            target_branch="feature/x"
        )
        ff = UIMergeResult(
            status=MergeStatus.FAST_FORWARD,
            source_ref="origin/develop",
            target_branch="feature/x"
        )
        assert merged.created_commit is True
        assert ff.created_commit is False


class TestHasConflictMarkers:
    """Tests for has_conflict_markers"""

    def test_detects_full_conflict_block(self):
        """Should detect a complete conflict block."""
        content = "a\n<<<<<<< HEAD\nmine\n=======\ntheirs\n>>>>>>> origin/develop\nb\n"

        assert has_conflict_markers(content) is True

    def test_resolved_content_has_no_markers(self):
        """Should report clean content as resolved."""
        assert has_conflict_markers("merged content\n") is False

    def test_ignores_lone_start_marker(self):
        """A start marker with no closing marker is not an unresolved conflict."""
        assert has_conflict_markers("<<<<<<< HEAD\nmine\n") is False

    def test_ignores_markers_not_at_line_start(self):
        """Text mentioning markers mid-line is not a conflict."""
        content = "docs say <<<<<<< and >>>>>>> are markers\n"

        assert has_conflict_markers(content) is False

    def test_handles_empty_content(self):
        """Empty files are resolved."""
        assert has_conflict_markers("") is False
