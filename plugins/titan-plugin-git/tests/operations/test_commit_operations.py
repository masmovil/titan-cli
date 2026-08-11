"""
Tests for Commit Operations

Tests for pure business logic related to commit message handling.
"""

from titan_plugin_git.operations.commit_operations import (
    build_ai_commit_prompt,
    normalize_commit_message,
    capitalize_commit_subject,
    validate_message_length,
    process_ai_commit_message,
)


class TestBuildAICommitPrompt:
    """Tests for build_ai_commit_prompt function."""

    def test_build_basic_prompt(self):
        """Should build prompt with diff and files."""
        diff = "diff --git a/file.py\n+new line"
        files = ["file.py"]
        prompt = build_ai_commit_prompt(diff, files)
        assert "Changed files" in prompt
        assert "file.py" in prompt
        assert "diff --git a/file.py" in prompt
        assert "CRITICAL Instructions" in prompt

    def test_truncate_long_diff(self):
        """Should cut a diff that busts the budget, and say it did."""
        diff = "a" * 10000
        files = ["file.py"]
        prompt = build_ai_commit_prompt(diff, files, max_diff_chars=100)
        assert len(prompt) < 2500  # Much shorter than the original diff
        assert "omitted" in prompt.lower()

    def test_no_truncation_for_short_diff(self):
        """Should not cut a short diff."""
        diff = "short diff"
        files = ["file.py"]
        prompt = build_ai_commit_prompt(diff, files, max_diff_chars=100)
        assert "omitted" not in prompt.lower()
        assert "sampled" not in prompt.lower()
        assert "short diff" in prompt

    def test_every_file_is_represented_when_the_diff_is_cut(self):
        """
        The bug this guards: clipping the first N characters gave the whole budget to
        whichever files git emitted first, so a message could confidently describe a
        fraction of the commit. A commit of production code plus tests was once summarised
        as `test:` because the tests were all that fit.
        """
        diff = "".join(
            f"diff --git a/file{i}.py b/file{i}.py\n"
            f"--- a/file{i}.py\n+++ b/file{i}.py\n"
            + "".join(f"+line {j} of file {i}\n" for j in range(200))
            for i in range(6)
        )
        files = [f"file{i}.py" for i in range(6)]

        prompt = build_ai_commit_prompt(diff, files, max_diff_chars=3000)

        for i in range(6):
            assert f"diff --git a/file{i}.py" in prompt, f"file{i}.py has no diff at all"

    def test_prompt_size_does_not_grow_with_the_number_of_files(self):
        """
        A per-file floor is what makes each slice worth reading, and it is also how a fixed
        cost quietly becomes one that scales with the commit. Both the diff body and the
        file summary are capped, so a 3000-file commit costs about what a 20-file one does.
        """

        def diff_of(n_files):
            return "".join(
                f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n"
                + "".join(f"+line {j} in file {i}\n" for j in range(200))
                for i in range(n_files)
            )

        small = build_ai_commit_prompt(diff_of(20), [f"f{i}.py" for i in range(20)])
        huge = build_ai_commit_prompt(diff_of(3000), [f"f{i}.py" for i in range(3000)])

        assert len(huge) < len(small) * 1.5
        assert "more changed files" in huge

    def test_the_total_file_count_is_always_stated(self):
        """Even when most files are only counted, the message needs to know how many."""
        files = [f"f{i}.py" for i in range(500)]
        diff = "".join(f"diff --git a/f{i}.py b/f{i}.py\n+one\n" for i in range(500))

        prompt = build_ai_commit_prompt(diff, files)

        assert "500 total" in prompt

    def test_per_file_line_counts_cover_every_file(self):
        """The counts are the complete picture even when the diff body is not."""
        diff = (
            "diff --git a/small.py b/small.py\n--- a/small.py\n+++ b/small.py\n+one\n-two\n"
            "diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n"
            + "".join(f"+line {j}\n" for j in range(500))
        )

        prompt = build_ai_commit_prompt(diff, ["small.py", "big.py"], max_diff_chars=200)

        assert "small.py: +1 -1" in prompt
        assert "big.py: +500 -0" in prompt

    def test_multiple_files(self):
        """Should list all files."""
        diff = "diff content"
        files = ["file1.py", "file2.py", "file3.py"]
        prompt = build_ai_commit_prompt(diff, files)
        assert "file1.py" in prompt
        assert "file2.py" in prompt
        assert "file3.py" in prompt
        assert "3 total" in prompt

    def test_empty_files_list(self):
        """Should handle empty files list."""
        diff = "diff content"
        files = []
        prompt = build_ai_commit_prompt(diff, files)
        assert "(checking diff)" in prompt


class TestNormalizeCommitMessage:
    """Tests for normalize_commit_message function."""

    def test_remove_double_quotes(self):
        """Should remove surrounding double quotes."""
        result = normalize_commit_message('"feat: Add feature"')
        assert result == "feat: Add feature"

    def test_remove_single_quotes(self):
        """Should remove surrounding single quotes."""
        result = normalize_commit_message("'fix: Fix bug'")
        assert result == "fix: Fix bug"

    def test_strip_whitespace(self):
        """Should strip leading/trailing whitespace."""
        result = normalize_commit_message("  feat: Add feature  ")
        assert result == "feat: Add feature"

    def test_take_first_line(self):
        """Should take only first line."""
        result = normalize_commit_message("feat: Add feature\n\nBody text\nMore body")
        assert result == "feat: Add feature"

    def test_combined_normalization(self):
        """Should apply all normalizations."""
        result = normalize_commit_message('  "feat: Add feature"  \n\nBody')
        assert result == "feat: Add feature"

    def test_already_normalized(self):
        """Should not change already normalized message."""
        result = normalize_commit_message("feat: Add feature")
        assert result == "feat: Add feature"

    def test_empty_string(self):
        """Should handle empty string."""
        result = normalize_commit_message("")
        assert result == ""


class TestCapitalizeCommitSubject:
    """Tests for capitalize_commit_subject function."""

    def test_capitalize_lowercase_subject(self):
        """Should capitalize lowercase subject."""
        result = capitalize_commit_subject("feat: add new feature")
        assert result == "feat: Add new feature"

    def test_preserve_capitalized_subject(self):
        """Should preserve already capitalized subject."""
        result = capitalize_commit_subject("feat: Add new feature")
        assert result == "feat: Add new feature"

    def test_no_colon(self):
        """Should return unchanged if no colon."""
        result = capitalize_commit_subject("no colon here")
        assert result == "no colon here"

    def test_multiple_colons(self):
        """Should handle multiple colons (split on first)."""
        result = capitalize_commit_subject("feat: add feature: with colon")
        assert result == "feat: Add feature: with colon"

    def test_empty_subject(self):
        """Should handle empty subject after colon."""
        result = capitalize_commit_subject("feat:")
        assert result == "feat: "  # Strip adds space for empty subject

    def test_whitespace_after_colon(self):
        """Should handle whitespace after colon."""
        result = capitalize_commit_subject("feat:   add feature")
        assert result == "feat: Add feature"

    def test_different_commit_types(self):
        """Should work with all commit types."""
        assert capitalize_commit_subject("fix: resolve bug") == "fix: Resolve bug"
        assert capitalize_commit_subject("refactor: improve code") == "refactor: Improve code"
        assert capitalize_commit_subject("docs: update readme") == "docs: Update readme"


class TestValidateMessageLength:
    """Tests for validate_message_length function."""

    def test_valid_length(self):
        """Should pass for short messages."""
        is_valid, length = validate_message_length("Short message")
        assert is_valid is True
        assert length == 13

    def test_exactly_max_length(self):
        """Should pass for message exactly at max length."""
        message = "a" * 72
        is_valid, length = validate_message_length(message, max_length=72)
        assert is_valid is True
        assert length == 72

    def test_too_long(self):
        """Should fail for too long messages."""
        message = "a" * 100
        is_valid, length = validate_message_length(message, max_length=72)
        assert is_valid is False
        assert length == 100

    def test_custom_max_length(self):
        """Should use custom max length."""
        message = "a" * 50
        is_valid, _ = validate_message_length(message, max_length=40)
        assert is_valid is False

        is_valid, _ = validate_message_length(message, max_length=60)
        assert is_valid is True

    def test_empty_string(self):
        """Should handle empty string."""
        is_valid, length = validate_message_length("")
        assert is_valid is True
        assert length == 0


class TestProcessAICommitMessage:
    """Tests for process_ai_commit_message function."""

    def test_complete_pipeline(self):
        """Should normalize and capitalize."""
        result = process_ai_commit_message('"feat: add new feature"')
        assert result == "feat: Add new feature"

    def test_quoted_lowercase(self):
        """Should handle quoted lowercase message."""
        result = process_ai_commit_message("'fix: resolve bug'")
        assert result == "fix: Resolve bug"

    def test_multiline_with_quotes(self):
        """Should handle multiline quoted message."""
        result = process_ai_commit_message('"feat: add feature"\n\nBody text')
        assert result == "feat: Add feature"

    def test_whitespace_and_quotes(self):
        """Should handle whitespace and quotes."""
        result = process_ai_commit_message('  "refactor: improve code"  ')
        assert result == "refactor: Improve code"

    def test_already_perfect(self):
        """Should not change already perfect message."""
        result = process_ai_commit_message("feat: Add new feature")
        assert result == "feat: Add new feature"

    def test_no_conventional_format(self):
        """Should handle non-conventional format."""
        result = process_ai_commit_message('"Add new feature"')
        assert result == "Add new feature"
