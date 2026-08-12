"""
Tests for fitting a unified diff into a prompt.

The behaviour these pin down was learned from a real failure: a prompt that kept the first
N characters of a diff described a 13-file commit using only the 3 files git happened to
emit first - all of them tests - and the model dutifully typed the whole commit as `test:`.
Breadth is what a summary needs; depth is what it can afford to lose.
"""

from titan_cli.core.diffs import (
    budget_diff_across_files,
    format_file_summary,
    split_diff_by_file,
    summarize_diff_files,
)


def _diff(n_files, lines_per_file=200):
    return "".join(
        f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n"
        + "".join(f"+line {j} in file {i}\n" for j in range(lines_per_file))
        for i in range(n_files)
    )


class TestSplitDiffByFile:
    def test_splits_on_file_headers(self):
        chunks = split_diff_by_file(_diff(3, lines_per_file=1))

        assert [path for path, _ in chunks] == ["f0.py", "f1.py", "f2.py"]

    def test_text_without_headers_is_one_anonymous_chunk(self):
        chunks = split_diff_by_file("just some text")

        assert chunks == [("", "just some text")]

    def test_empty_diff_has_no_chunks(self):
        assert split_diff_by_file("") == []


class TestSummarizeDiffFiles:
    def test_counts_additions_and_removals_per_file(self):
        diff = (
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n+one\n+two\n-three\n"
            "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n+only\n"
        )

        assert summarize_diff_files(diff) == [("a.py", 2, 1), ("b.py", 1, 0)]

    def test_file_headers_are_not_counted_as_changes(self):
        """`+++ b/x` and `--- a/x` start with the same characters as real changes."""
        diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n+one\n"

        assert summarize_diff_files(diff) == [("a.py", 1, 0)]


class TestBudgetDiffAcrossFiles:
    def test_a_diff_within_budget_is_untouched(self):
        diff = _diff(2, lines_per_file=2)

        assert budget_diff_across_files(diff, 100_000) == diff

    def test_every_file_gets_a_share(self):
        result = budget_diff_across_files(_diff(6), 3000)

        for i in range(6):
            assert f"diff --git a/f{i}.py" in result

    def test_the_budget_is_not_blown_by_the_per_file_floor(self):
        """
        A floor alone turns a fixed cost into one that scales with the commit: 3000 files at
        a 400-character minimum is 1.2M characters from an 8000-character budget.
        """
        result = budget_diff_across_files(_diff(3000), 8000)

        assert len(result) < 8000 * 2
        assert "more changed files not shown here" in result


class TestFormatFileSummary:
    def test_lists_every_file_with_its_counts(self):
        summary = format_file_summary(_diff(3, lines_per_file=2))

        assert "f0.py: +2 -0" in summary
        assert "f2.py: +2 -0" in summary

    def test_caps_the_list_and_says_how_many_are_missing(self):
        summary = format_file_summary(_diff(200, lines_per_file=1), max_files=60)

        assert summary.count(": +") == 60
        assert "and 140 more changed files" in summary

    def test_returns_empty_for_text_that_is_not_a_diff(self):
        """Callers fall back to their own file list rather than printing a fake summary."""
        assert format_file_summary("not a diff at all") == ""
