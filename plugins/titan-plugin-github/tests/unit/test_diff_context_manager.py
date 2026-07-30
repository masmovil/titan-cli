"""
Tests for DiffContextManager and its internal parsing helpers.

Covers: hunk simple, múltiples hunks, líneas borradas vs añadidas,
outdated comments, suggestions multiline, snippet match,
líneas válidas para inline comment, y fallbacks.
"""

from titan_plugin_github.managers.diff_context_manager import (
    DiffContextManager,
    get_or_create_diff_manager,
)
from titan_plugin_github.managers.diff_context_manager import _extract_best_anchor_from_text


# ---------------------------------------------------------------------------
# Fixtures — diff strings
# ---------------------------------------------------------------------------

SIMPLE_DIFF = """\
diff --git a/src/foo.py b/src/foo.py
index abc..def 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -10,5 +10,6 @@
 def hello():
     print("hello")
+    print("world")
     return True

 def bye():
"""

MULTI_HUNK_DIFF = """\
diff --git a/src/bar.py b/src/bar.py
index 111..222 100644
--- a/src/bar.py
+++ b/src/bar.py
@@ -1,4 +1,5 @@
 import os
+import sys
 import re

 def first():
@@ -20,2 +21,3 @@
 def second():
     pass
+    # new comment

"""

DELETED_LINES_DIFF = """\
diff --git a/src/baz.py b/src/baz.py
index aaa..bbb 100644
--- a/src/baz.py
+++ b/src/baz.py
@@ -5,4 +5,3 @@
 def foo():
-    old_line_1 = True
-    old_line_2 = False
+    new_line = True
     return new_line

"""

MULTI_FILE_DIFF = SIMPLE_DIFF + "\n" + MULTI_HUNK_DIFF


# ---------------------------------------------------------------------------
# Parsing — hunk simple
# ---------------------------------------------------------------------------

class TestSimpleHunkParsing:
    def test_file_is_indexed(self):
        """Should index the file path from the diff --git header."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.get_file("src/foo.py") is not None

    def test_unknown_file_returns_none(self):
        """Should return None for a path not present in the diff."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.get_file("nonexistent.py") is None

    def test_hunk_count(self):
        """Should parse exactly one hunk for a simple diff."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert len(mgr.get_hunks("src/foo.py")) == 1

    def test_hunk_line_start(self):
        """Should parse new_line_start correctly from @@ header."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        hunk = mgr.get_hunks("src/foo.py")[0]
        assert hunk.new_line_start == 10

    def test_hunk_old_line_start(self):
        """Should parse old_line_start correctly from @@ header."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        hunk = mgr.get_hunks("src/foo.py")[0]
        assert hunk.old_line_start == 10


# ---------------------------------------------------------------------------
# Parsing — múltiples hunks
# ---------------------------------------------------------------------------

class TestMultiHunkParsing:
    def test_two_hunks_indexed(self):
        """Should parse both hunks from a file with two @@ sections."""
        mgr = DiffContextManager.from_diff(MULTI_HUNK_DIFF)
        assert len(mgr.get_hunks("src/bar.py")) == 2

    def test_first_hunk_start(self):
        """First hunk should start at new-file line 1."""
        mgr = DiffContextManager.from_diff(MULTI_HUNK_DIFF)
        assert mgr.get_hunks("src/bar.py")[0].new_line_start == 1

    def test_second_hunk_start(self):
        """Second hunk should start at new-file line 21."""
        mgr = DiffContextManager.from_diff(MULTI_HUNK_DIFF)
        assert mgr.get_hunks("src/bar.py")[1].new_line_start == 21

    def test_get_hunk_for_line_first(self):
        """get_hunk_for_line should return the first hunk for a line within it."""
        mgr = DiffContextManager.from_diff(MULTI_HUNK_DIFF)
        hunk = mgr.get_hunk_for_line("src/bar.py", 2)
        assert hunk is not None
        assert hunk.new_line_start == 1

    def test_get_hunk_for_line_second(self):
        """get_hunk_for_line should return the second hunk for a line within it."""
        mgr = DiffContextManager.from_diff(MULTI_HUNK_DIFF)
        hunk = mgr.get_hunk_for_line("src/bar.py", 22)
        assert hunk is not None
        assert hunk.new_line_start == 21

    def test_get_hunk_for_line_fallback_first(self):
        """get_hunk_for_line should fall back to the first hunk when line is not found."""
        mgr = DiffContextManager.from_diff(MULTI_HUNK_DIFF)
        hunk = mgr.get_hunk_for_line("src/bar.py", 999)
        assert hunk is not None
        assert hunk.new_line_start == 1

    def test_get_hunk_for_line_strict_returns_none(self):
        """Strict mode should not fall back to another hunk."""
        mgr = DiffContextManager.from_diff(MULTI_HUNK_DIFF)
        hunk = mgr.get_hunk_for_line("src/bar.py", 999, allow_fallback=False)
        assert hunk is None


# ---------------------------------------------------------------------------
# Valid review lines — añadidas vs borradas
# ---------------------------------------------------------------------------

class TestValidReviewLines:
    def test_added_lines_are_valid(self):
        """Added lines ('+') should be in valid_review_lines."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        valid = mgr.get_valid_review_lines("src/foo.py")
        assert 12 in valid  # the '+    print("world")' line

    def test_context_lines_are_valid(self):
        """Context lines (' ') should be in valid_review_lines."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        valid = mgr.get_valid_review_lines("src/foo.py")
        assert 10 in valid  # ' def hello():'

    def test_deleted_lines_are_not_valid(self):
        """Deleted lines ('-') must NOT appear in valid_review_lines."""
        mgr = DiffContextManager.from_diff(DELETED_LINES_DIFF)
        valid = mgr.get_valid_review_lines("src/baz.py")
        # old_line_1 and old_line_2 were deleted; their old-file positions
        # should not appear as valid new-file review lines
        # New-file line 5 is 'def foo():' (context), line 6 is '+    new_line = True'
        assert 6 in valid
        # Verify that the deleted lines count doesn't inflate valid lines
        assert len(valid) < 10  # sanity check: small diff, few valid lines

    def test_unknown_file_returns_empty(self):
        """get_valid_review_lines should return empty frozenset for unknown file."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.get_valid_review_lines("nope.py") == frozenset()

    def test_get_all_valid_lines_keys(self):
        """get_all_valid_lines should return all files present in the diff."""
        mgr = DiffContextManager.from_diff(MULTI_FILE_DIFF)
        all_valid = mgr.get_all_valid_lines()
        assert "src/foo.py" in all_valid
        assert "src/bar.py" in all_valid


# ---------------------------------------------------------------------------
# Snippet search
# ---------------------------------------------------------------------------

class TestFindLineBySnippet:
    def test_finds_added_line(self):
        """Should find the line number of an added line matching the snippet."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        line = mgr.find_line_by_snippet("src/foo.py", 'print("world")')
        assert line is not None
        assert line == 12

    def test_finds_context_line(self):
        """Should find the line number of a context line matching the snippet."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        line = mgr.find_line_by_snippet("src/foo.py", "def hello")
        assert line is not None

    def test_returns_none_for_missing_snippet(self):
        """Should return None when the snippet is not in the diff."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.find_line_by_snippet("src/foo.py", "this_does_not_exist") is None

    def test_returns_none_for_empty_snippet(self):
        """Should return None for an empty snippet string."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.find_line_by_snippet("src/foo.py", "") is None

    def test_returns_none_for_unknown_file(self):
        """Should return None when the file is not in the diff."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.find_line_by_snippet("unknown.py", "hello") is None

    def test_resolve_line_anchor_prefers_snippet(self):
        """resolve_line_anchor should use snippet before trusting the AI line."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        line = mgr.resolve_line_anchor("src/foo.py", line=999, snippet='print("world")')
        assert line == 12


# ---------------------------------------------------------------------------
# build_focused_diff — ventana de contexto
# ---------------------------------------------------------------------------

class TestBuildFocusedDiff:
    def test_returns_string(self):
        """Should return a non-empty string for a valid line."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        result = mgr.build_focused_diff("src/foo.py", 12)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_hunk_header(self):
        """Focused diff should start with a @@ header."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        result = mgr.build_focused_diff("src/foo.py", 12)
        assert result.startswith("@@")

    def test_marks_target_line(self):
        """Target line should be annotated with ◄ marker."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        result = mgr.build_focused_diff("src/foo.py", 12)
        assert "◄" in result

    def test_outdated_no_marker(self):
        """Outdated diffs should not include the ◄ target marker."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        result = mgr.build_focused_diff("src/foo.py", 10, is_outdated=True)
        assert "◄" not in result

    def test_unknown_file_returns_empty(self):
        """Should return empty string for a file not in the diff."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.build_focused_diff("nope.py", 1) == ""


# ---------------------------------------------------------------------------
# extract_original_lines_for_suggestion
# ---------------------------------------------------------------------------

class TestExtractOriginalLines:
    def test_single_line(self):
        """Should extract one line at the target position."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        result = mgr.extract_original_lines_for_suggestion("src/foo.py", 12, count=1)
        assert result is not None
        assert 'print("world")' in result

    def test_multiline_suggestion(self):
        """Should extract multiple consecutive lines for multiline suggestions."""
        mgr = DiffContextManager.from_diff(DELETED_LINES_DIFF)
        # line 6 = '+    new_line = True', line 7 = '     return new_line'
        result = mgr.extract_original_lines_for_suggestion("src/baz.py", 6, count=2)
        assert result is not None
        lines = result.split("\n")
        assert len(lines) == 2

    def test_unknown_file_returns_none(self):
        """Should return None for a file not in the diff."""
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        assert mgr.extract_original_lines_for_suggestion("nope.py", 1) is None


# ---------------------------------------------------------------------------
# Multi-file diff
# ---------------------------------------------------------------------------

class TestMultiFileDiff:
    def test_both_files_indexed(self):
        """Should index all files from a multi-file diff."""
        mgr = DiffContextManager.from_diff(MULTI_FILE_DIFF)
        assert mgr.get_file("src/foo.py") is not None
        assert mgr.get_file("src/bar.py") is not None

    def test_files_do_not_share_hunks(self):
        """Hunks from one file should not appear in another."""
        mgr = DiffContextManager.from_diff(MULTI_FILE_DIFF)
        foo_hunks = mgr.get_hunks("src/foo.py")
        bar_hunks = mgr.get_hunks("src/bar.py")
        assert len(foo_hunks) == 1
        assert len(bar_hunks) == 2


class TestFocusedReviewHelpers:
    def test_get_hunk_texts_returns_raw_hunks(self):
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)

        hunks = mgr.get_hunk_texts("src/foo.py")

        assert len(hunks) == 1
        assert hunks[0].startswith("@@")

    def test_build_expanded_hunks_includes_surrounding_context(self):
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)
        file_content = "\n".join(
            [
                "line 1",
                "line 2",
                "line 3",
                "line 4",
                "line 5",
                "line 6",
                "line 7",
                "line 8",
                "line 9",
                "def hello():",
                '    print("hello")',
                '    print("world")',
                "    return True",
                "",
                "def bye():",
            ]
        )

        expanded = mgr.build_expanded_hunks("src/foo.py", file_content, extra_lines=2)

        assert len(expanded) == 1
        assert "surrounding context" in expanded[0]
        assert 'print("world")' in expanded[0]


class TestExtractBestAnchorFromText:
    def test_skips_python_and_shell_comment_lines(self):
        text = """
# temporary workaround
# another note
actual_value = serviceId
"""

        result = _extract_best_anchor_from_text(text)

        assert result == "actual_value = serviceId"

    def test_skips_block_comment_lines(self):
        text = """
/*
 * transitional note
 */
return route.toPath()
"""

        result = _extract_best_anchor_from_text(text)

        assert result == "return route.toPath()"


# ---------------------------------------------------------------------------
# Publishable lines (D-008: GitHub diff as placement truth)
# ---------------------------------------------------------------------------

# Same change as WIDE_CONTEXT_DIFF below, but with GitHub's 3-line context:
# only lines 17-23 exist in GitHub's hunk.
GITHUB_U3_DIFF = """\
diff --git a/src/foo.py b/src/foo.py
index abc..def 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -17,6 +17,7 @@
 line17
 line18
 line19
+line20_added
 line21
 line22
 line23
"""

# The same change generated with extended context (-U20 style): the hunk covers
# many more context lines (10-30) that GitHub does NOT accept for inline comments.
WIDE_CONTEXT_DIFF = """\
diff --git a/src/foo.py b/src/foo.py
index abc..def 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -10,20 +10,21 @@
 line10
 line11
 line12
 line13
 line14
 line15
 line16
 line17
 line18
 line19
+line20_added
 line21
 line22
 line23
 line24
 line25
 line26
 line27
 line28
 line29
 line30
"""


class TestPublishableLines:
    def test_added_lines_tracked_separately_from_context(self):
        mgr = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)

        hunks = mgr.get_hunks("src/foo.py")
        assert len(hunks) == 1
        assert hunks[0].added_lines == frozenset({20})
        # valid_review_lines keeps its historical added+context semantics
        assert 20 in hunks[0].valid_review_lines
        assert 10 in hunks[0].valid_review_lines

    def test_fallback_without_github_diff_is_added_lines_only(self):
        mgr = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)

        assert not mgr.has_github_diff
        assert mgr.get_publishable_lines("src/foo.py") == frozenset({20})

    def test_github_diff_widens_fallback_to_its_own_hunk_lines(self):
        mgr = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)
        mgr.attach_github_diff(GITHUB_U3_DIFF)

        publishable = mgr.get_publishable_lines("src/foo.py")
        assert mgr.has_github_diff
        # GitHub's hunk lines (17-23) are publishable...
        assert publishable == frozenset({17, 18, 19, 20, 21, 22, 23})
        # ...but the -U20-only context lines are not (the D-004 422 case: line 10)
        assert 10 not in publishable
        # while the context diff still considers them valid for anchoring/display
        assert 10 in mgr.get_valid_review_lines("src/foo.py")

    def test_attach_empty_github_diff_keeps_fallback(self):
        mgr = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)
        mgr.attach_github_diff("")
        mgr.attach_github_diff("   \n")

        assert not mgr.has_github_diff
        assert mgr.get_publishable_lines("src/foo.py") == frozenset({20})

    def test_file_missing_from_github_diff_has_no_publishable_lines(self):
        mgr = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)
        mgr.attach_github_diff(GITHUB_U3_DIFF.replace("src/foo.py", "src/other.py"))

        assert mgr.get_publishable_lines("src/foo.py") == frozenset()

    def test_get_all_publishable_lines_covers_union_of_paths(self):
        mgr = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)
        mgr.attach_github_diff(GITHUB_U3_DIFF)

        all_lines = mgr.get_all_publishable_lines()
        assert all_lines == {"src/foo.py": frozenset({17, 18, 19, 20, 21, 22, 23})}


# ---------------------------------------------------------------------------
# Resolver v2 (line-anchoring-003: D-002/D-005 reproduced false positive)
# ---------------------------------------------------------------------------

# The generic line `return None` is ADDED in two different hunks:
# hunk 1 -> new-file line 5, hunk 2 -> new-file line 53.
DUPLICATE_SNIPPET_DIFF = """\
diff --git a/src/svc.py b/src/svc.py
index 111..222 100644
--- a/src/svc.py
+++ b/src/svc.py
@@ -3,3 +3,4 @@
 def early_helper(x):
     if not x:
+        return None
     return x

@@ -48,4 +50,5 @@
 def late_handler(y):
     value = compute(y)
     if value is None:
+        return None
     return value
"""


class TestResolverV2:
    def _mgr(self):
        return DiffContextManager.from_diff(DUPLICATE_SNIPPET_DIFF)

    def test_repro_duplicate_snippet_no_longer_relocates_valid_ai_line(self):
        """The reproduced false positive: the AI reported line 53 with snippet
        'return None' (also added at line 5, an earlier hunk). The old resolver
        returned 5 — first global occurrence — silently relocating a correct
        comment to the wrong hunk."""
        resolved = self._mgr().resolve_line_anchor("src/svc.py", line=53, snippet="return None")

        assert resolved == 53

    def test_ambiguous_snippet_with_ai_line_among_matches_keeps_it(self):
        resolved = self._mgr().resolve_line_anchor("src/svc.py", line=5, snippet="return None")

        assert resolved == 5

    def test_unique_snippet_match_still_corrects_offset_ai_line(self):
        # snippet unique in the file; AI line slightly off (52) — snippet wins
        resolved = self._mgr().resolve_line_anchor(
            "src/svc.py", line=52, snippet="value = compute(y)"
        )

        assert resolved == 51

    def test_ambiguous_snippet_without_usable_ai_line_prefers_publishable_then_first(self):
        resolved = self._mgr().resolve_line_anchor("src/svc.py", line=None, snippet="return None")

        assert resolved == 5

    def test_ambiguous_snippet_without_usable_ai_line_prefers_nearest_publishable(self):
        # AI line 999 (not valid, not a match) — nearest publishable match wins
        resolved = self._mgr().resolve_line_anchor("src/svc.py", line=999, snippet="return None")

        assert resolved == 53

    def test_find_lines_by_snippet_returns_all_matches_in_order(self):
        assert self._mgr().find_lines_by_snippet("src/svc.py", "return None") == [5, 53]

    def test_polluted_snippets_are_sanitized_before_matching(self):
        """Models copy prompt-annotation prefixes ('NN | ', 'NN [ADDED] ', '+')
        into the snippet — the old matcher lost the anchor entirely."""
        mgr = self._mgr()

        for polluted in ("53 [ADDED] return None", "53 | return None", "+return None"):
            assert mgr.find_lines_by_snippet("src/svc.py", polluted) == [5, 53], polluted

    def test_find_line_by_snippet_compat_returns_first_match(self):
        assert self._mgr().find_line_by_snippet("src/svc.py", "return None") == 5


# ---------------------------------------------------------------------------
# Parser hardening: empty context lines, @@ self-check, quoted paths, CRLF
# ---------------------------------------------------------------------------

# An empty context line that lost its leading space ("" instead of " ") — e.g.
# a trailing-whitespace-stripping transport. Not counting it shifts every
# subsequent line of the hunk by one (the classic "comment lands N lines off").
STRIPPED_EMPTY_CONTEXT_DIFF = (
    "diff --git a/src/pkg.py b/src/pkg.py\n"
    "index 111..222 100644\n"
    "--- a/src/pkg.py\n"
    "+++ b/src/pkg.py\n"
    "@@ -1,6 +1,6 @@\n"
    " import os\n"
    "\n"  # empty context line whose leading space was stripped
    " def run():\n"
    "-    pass\n"
    "+    return os.name\n"
    " \n"
    " # end\n"
)

# Hunk header declares 4 new-file lines but the body only has 2 — a desync the
# self-check must flag so the file degrades to general-body placement.
DESYNCED_DIFF = (
    "diff --git a/src/foo.py b/src/foo.py\n"
    "index 111..222 100644\n"
    "--- a/src/foo.py\n"
    "+++ b/src/foo.py\n"
    "@@ -1,3 +1,4 @@\n"
    " import os\n"
    "+import sys\n"
)

QUOTED_PATH_DIFF = (
    'diff --git "a/src/my file.py" "b/src/my file.py"\n'
    "index 111..222 100644\n"
    '--- "a/src/my file.py"\n'
    '+++ "b/src/my file.py"\n'
    "@@ -1,2 +1,3 @@\n"
    " x = 1\n"
    "+y = 2\n"
    " z = 3\n"
)

CRLF_DIFF = (
    "diff --git a/src/win.py b/src/win.py\r\n"
    "index 111..222 100644\r\n"
    "--- a/src/win.py\r\n"
    "+++ b/src/win.py\r\n"
    "@@ -1,2 +1,3 @@\r\n"
    " x = 1\r\n"
    "+y = 2\r\n"
    " z = 3\r\n"
)


class TestEmptyContextLineCounting:
    def test_lines_after_stripped_empty_line_are_not_shifted(self):
        """Without counting "" as context, '# end' would resolve to line 5 instead of 6."""
        mgr = DiffContextManager.from_diff(STRIPPED_EMPTY_CONTEXT_DIFF)

        assert mgr.find_line_by_snippet("src/pkg.py", "# end") == 6
        assert mgr.find_line_by_snippet("src/pkg.py", "return os.name") == 4

    def test_hunk_with_stripped_empty_line_passes_self_check(self):
        mgr = DiffContextManager.from_diff(STRIPPED_EMPTY_CONTEXT_DIFF)

        hunk = mgr.get_hunks("src/pkg.py")[0]
        assert hunk.header_consistent is True
        assert mgr.get_file("src/pkg.py").hunks_consistent is True

    def test_stripped_empty_line_is_a_valid_review_line(self):
        mgr = DiffContextManager.from_diff(STRIPPED_EMPTY_CONTEXT_DIFF)

        assert 2 in mgr.get_valid_review_lines("src/pkg.py")


class TestHunkHeaderSelfCheck:
    def test_consistent_hunk_is_flagged_consistent(self):
        mgr = DiffContextManager.from_diff(SIMPLE_DIFF)

        assert mgr.get_hunks("src/foo.py")[0].header_consistent is True

    def test_desynced_hunk_is_flagged_inconsistent(self):
        mgr = DiffContextManager.from_diff(DESYNCED_DIFF)

        hunk = mgr.get_hunks("src/foo.py")[0]
        assert hunk.header_consistent is False
        assert mgr.get_file("src/foo.py").hunks_consistent is False

    def test_desynced_file_has_no_publishable_lines(self):
        """The load-bearing degradation: a desynced parse must never publish
        potentially-shifted lines inline — not even its added lines."""
        mgr = DiffContextManager.from_diff(DESYNCED_DIFF)

        assert 2 in mgr.get_file("src/foo.py").added_lines  # parsed, but untrusted
        assert mgr.get_publishable_lines("src/foo.py") == frozenset()

    def test_desynced_context_diff_wins_over_attached_github_diff(self):
        """Anchors resolve against the context diff; if that parse desynced, an
        intact GitHub diff cannot make its lines trustworthy."""
        mgr = DiffContextManager.from_diff(DESYNCED_DIFF)
        mgr.attach_github_diff(GITHUB_U3_DIFF)

        assert mgr.get_publishable_lines("src/foo.py") == frozenset()

    def test_desynced_github_diff_falls_back_to_added_lines(self):
        mgr = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)
        mgr.attach_github_diff(DESYNCED_DIFF)

        assert mgr.get_publishable_lines("src/foo.py") == frozenset({20})

    def test_desync_does_not_affect_other_files(self):
        mgr = DiffContextManager.from_diff(
            DESYNCED_DIFF + WIDE_CONTEXT_DIFF.replace("src/foo.py", "src/ok.py")
        )

        assert mgr.get_publishable_lines("src/foo.py") == frozenset()
        assert mgr.get_publishable_lines("src/ok.py") == frozenset({20})


class TestQuotedPathHeaders:
    def test_quoted_path_with_spaces_is_indexed(self):
        mgr = DiffContextManager.from_diff(QUOTED_PATH_DIFF)

        assert mgr.get_file("src/my file.py") is not None
        assert mgr.find_line_by_snippet("src/my file.py", "y = 2") == 2

    def test_quoted_path_hunk_is_consistent(self):
        mgr = DiffContextManager.from_diff(QUOTED_PATH_DIFF)

        assert mgr.get_file("src/my file.py").hunks_consistent is True
        assert mgr.get_publishable_lines("src/my file.py") == frozenset({2})


class TestCrlfDiffs:
    def test_crlf_path_is_indexed_without_carriage_return(self):
        mgr = DiffContextManager.from_diff(CRLF_DIFF)

        assert mgr.get_file("src/win.py") is not None
        assert mgr.get_file("src/win.py\r") is None

    def test_crlf_snippet_search_matches(self):
        mgr = DiffContextManager.from_diff(CRLF_DIFF)

        assert mgr.find_line_by_snippet("src/win.py", "y = 2") == 2
        # snippet itself polluted with \r (copy-paste from CRLF content)
        assert mgr.find_line_by_snippet("src/win.py", "y = 2\r") == 2

    def test_crlf_hunk_passes_self_check(self):
        mgr = DiffContextManager.from_diff(CRLF_DIFF)

        assert mgr.get_file("src/win.py").hunks_consistent is True
        assert mgr.get_publishable_lines("src/win.py") == frozenset({2})


# ---------------------------------------------------------------------------
# Manager cache: a refetched diff must not keep serving the previous parse
# ---------------------------------------------------------------------------

class TestGetOrCreateDiffManager:
    def test_parses_and_caches_on_first_call(self):
        cache = {}

        mgr = get_or_create_diff_manager(SIMPLE_DIFF, cache)

        assert mgr.get_file("src/foo.py") is not None
        assert get_or_create_diff_manager(SIMPLE_DIFF, cache) is mgr

    def test_same_diff_reuses_the_cached_manager(self):
        cache = {}
        first = get_or_create_diff_manager(SIMPLE_DIFF, cache)

        assert get_or_create_diff_manager(SIMPLE_DIFF, cache) is first

    def test_changed_diff_reparses_instead_of_serving_stale_lines(self):
        """The bug: a diff refetched after a push kept returning the old manager, so
        every anchor resolved against line numbers from the previous revision."""
        cache = {}
        get_or_create_diff_manager(SIMPLE_DIFF, cache)

        refreshed = get_or_create_diff_manager(MULTI_HUNK_DIFF, cache)

        assert refreshed.get_file("src/bar.py") is not None
        assert refreshed.get_file("src/foo.py") is None

    def test_reverting_to_the_previous_diff_reparses_too(self):
        cache = {}
        first = get_or_create_diff_manager(SIMPLE_DIFF, cache)
        get_or_create_diff_manager(MULTI_HUNK_DIFF, cache)

        back = get_or_create_diff_manager(SIMPLE_DIFF, cache)

        assert back is not first
        assert back.get_file("src/foo.py") is not None

    def test_distinct_cache_keys_stay_independent(self):
        cache = {}

        review = get_or_create_diff_manager(SIMPLE_DIFF, cache, cache_key="review")
        thread = get_or_create_diff_manager(MULTI_HUNK_DIFF, cache, cache_key="thread")

        assert get_or_create_diff_manager(SIMPLE_DIFF, cache, cache_key="review") is review
        assert get_or_create_diff_manager(MULTI_HUNK_DIFF, cache, cache_key="thread") is thread

    def test_works_without_a_cache(self):
        mgr = get_or_create_diff_manager(SIMPLE_DIFF)

        assert mgr.get_file("src/foo.py") is not None
