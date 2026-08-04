from titan_plugin_github.models.review_enums import ChecklistCategory, CommentContextKind
from titan_plugin_github.models.review_models import (
    CommentContextEntry,
    FileContextEntry,
    FocusContextBatch,
    PullRequestManifest,
    ReviewChecklistItem,
)
from titan_cli.core.result import ClientError, ClientSuccess
from titan_plugin_github.operations.findings_operations import (
    _annotate_diff_hunk,
    build_findings_prompt_parts,
    findings_json_schema,
    parse_findings_response,
    summarize_findings_prompt_parts,
)


def test_build_findings_prompt_parts_compacts_axes_and_pr_context():
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={"src/foo.py": FileContextEntry(path="src/foo.py", hunks=["@@ -1 +1 @@\n+print('x')"])},
        comment_context=[
            CommentContextEntry(
                kind=CommentContextKind.COMMENT,
                thread_id="t1",
                path="src/foo.py",
                line=1,
                title="Existing",
                summary="Already mentioned",
                is_resolved=False,
            )
        ],
        checklist_applicable=[
            ReviewChecklistItem(
                id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
                name="Functional",
                description="Long description that should not appear in findings prompt axes",
            ),
            ReviewChecklistItem(
                id=ChecklistCategory.ERROR_HANDLING,
                name="Errors",
                description="Another long description",
            ),
        ],
        pr_manifest=PullRequestManifest(
            number=123,
            title="A very long pull request title that should be shortened in the findings prompt context if needed",
            base="main",
            head="feature/foo",
            author="alex",
            description="desc",
        ),
    )

    parts = build_findings_prompt_parts(batch)

    assert '"functional_correctness"' in parts["review_axes"]
    # review-quality-001 (D-002 approved): applicable checklist items now include
    # name + description (capped) so the findings model knows what each axis means.
    assert "Long description that should not appear" in parts["review_axes"]
    assert '"name": "Functional"' in parts["review_axes"]
    assert "Base" not in parts["pr_context"]
    assert "Batch: batch_1" in parts["pr_context"]
    assert "observable meaning of data, events, labels, classifications, or results" in parts["instructions"]
    assert "Do not report code style preferences" in parts["instructions"]


def test_summarize_findings_prompt_parts_returns_char_breakdown():
    parts = {
        "pr_context": "abc",
        "comments": "de",
        "review_axes": "fghi",
        "files_context": "j",
        "related_context": "",
        "instructions": "klmno",
        "schema": "pq",
        "prompt": "ignored",
    }

    summary = summarize_findings_prompt_parts(parts)

    assert summary == {
        "pr_context_chars": 3,
        "comment_context_chars": 2,
        "review_axes_chars": 4,
        "files_context_chars": 1,
        "related_context_chars": 0,
        "instructions_chars": 5,
        "schema_chars": 2,
    }


def test_build_findings_prompt_parts_renders_worktree_reference():
    batch = FocusContextBatch(
        batch_id="batch_2",
        files_context={
            "src/big.py": FileContextEntry(
                path="src/big.py",
                worktree_reference=True,
                review_hint="Read this file from the worktree and inspect the changed regions first.",
                changed_hunk_headers=["@@ -10,20 +10,30 @@", "@@ -80,5 +90,12 @@"],
            )
        },
        checklist_applicable=[
            ReviewChecklistItem(
                id=ChecklistCategory.FUNCTIONAL_CORRECTNESS,
                name="Functional",
                description="desc",
            )
        ],
    )

    parts = build_findings_prompt_parts(batch)

    assert "Read from worktree instead of inline context." in parts["files_context"]
    assert "Changed regions to inspect first:" in parts["files_context"]
    assert "@@ -10,20 +10,30 @@" in parts["files_context"]


# ---------------------------------------------------------------------------
# _annotate_diff_hunk()
# ---------------------------------------------------------------------------


def test_annotate_diff_hunk_numbers_added_and_context_lines():
    hunk = "@@ -10,2 +10,3 @@\n def bar():\n+    return 1\n-    return 0"

    result = _annotate_diff_hunk(hunk)

    assert "10 [CONTEXT] def bar():" in result
    assert "11 [ADDED]     return 1" in result
    assert "[DELETED - do not review]     return 0" in result


def test_annotate_diff_hunk_does_not_number_surrounding_context_lines():
    """Regression test: `expanded_hunks` entries prepend a raw, non-diff-prefixed
    surrounding-context block before the real diff hunk (DiffContextManager.build_expanded_hunks).
    Indented raw lines in that block must not be mislabeled as numbered [CONTEXT] diff lines."""
    hunk = (
        "@@ -10,2 +10,3 @@\n"
        "# --- surrounding context (lines 8-12) ---\n"
        "    def foo():\n"
        "        pass\n"
        "def bar():\n"
        "# --- diff hunk ---\n"
        " def bar():\n"
        "+    return 1\n"
        "-    return 0"
    )

    result = _annotate_diff_hunk(hunk)

    assert "    def foo():" in result
    assert "[CONTEXT]    def foo():" not in result
    assert "        pass" in result
    assert "[CONTEXT]        pass" not in result


def test_annotate_diff_hunk_real_hunk_numbering_unaffected_by_surrounding_context():
    """The actual diff-hunk lines after the '# --- diff hunk ---' marker must get the same
    line numbers they would get without the surrounding-context preamble at all — the raw
    preamble lines must not advance the line counter."""
    plain_hunk = "@@ -10,2 +10,3 @@\n def bar():\n+    return 1\n-    return 0"
    expanded_hunk = (
        "@@ -10,2 +10,3 @@\n"
        "# --- surrounding context (lines 8-12) ---\n"
        "    def foo():\n"
        "        pass\n"
        "def bar():\n"
        "# --- diff hunk ---\n"
        " def bar():\n"
        "+    return 1\n"
        "-    return 0"
    )

    plain_result = _annotate_diff_hunk(plain_hunk)
    expanded_result = _annotate_diff_hunk(expanded_hunk)

    plain_diff_lines = plain_result.splitlines()[1:]  # drop the @@ header
    expanded_diff_lines = expanded_result.splitlines()[-len(plain_diff_lines):]
    assert expanded_diff_lines == plain_diff_lines


# ---------------------------------------------------------------------------
# findings_json_schema() / parse_findings_response()
# ---------------------------------------------------------------------------


def test_findings_json_schema_wraps_array_in_object_with_findings_key():
    schema = findings_json_schema()

    assert schema["type"] == "object"
    assert schema["required"] == ["findings"]
    assert schema["properties"]["findings"]["type"] == "array"


def test_parse_findings_response_unstructured_parses_bare_array():
    result = parse_findings_response('[{"title": "Bug"}]', structured=False)

    assert isinstance(result, ClientSuccess)
    assert result.data == [{"title": "Bug"}]


def test_parse_findings_response_structured_unwraps_findings_key():
    result = parse_findings_response('{"findings": [{"title": "Bug"}]}', structured=True)

    assert isinstance(result, ClientSuccess)
    assert result.data == [{"title": "Bug"}]


def test_parse_findings_response_structured_errors_when_findings_key_missing():
    result = parse_findings_response('{"other": []}', structured=True)

    assert isinstance(result, ClientError)
    assert result.error_code == "MISSING_FINDINGS_FIELD"


def test_parse_findings_response_structured_falls_back_to_error_on_prose():
    result = parse_findings_response("I refuse to call that tool.", structured=True)

    assert isinstance(result, ClientError)


# ---------------------------------------------------------------------------
# review-quality-001/002: checklist content cap + PR intent (D-002 token mandate)
# ---------------------------------------------------------------------------

def test_checklist_descriptions_are_hard_capped():
    from titan_plugin_github.operations.findings_operations import _checklist_to_json

    items = [
        ReviewChecklistItem(
            id=ChecklistCategory.SECURITY,
            name="Security",
            description="x" * 500,
        )
    ]

    rendered = _checklist_to_json(items)

    assert "x" * 200 in rendered
    assert "x" * 201 not in rendered


def test_pr_context_includes_one_line_intent():
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={"src/foo.py": FileContextEntry(path="src/foo.py", hunks=["@@ -1 +1 @@\n+x"])},
        checklist_applicable=[],
        pr_manifest=PullRequestManifest(
            number=3597,
            title="Marketplace token retry",
            base="develop",
            head="feat/marketplace-token-retry",
            author="alex",
            # Real-world shape (PR #3597): meme image first, then the actual intent.
            description=(
                "\n![Token Refresh Meme](https://media.giphy.com/media/abc/giphy.gif)\n\n"
                "### PR's key points\n"
                "This PR implements a robust token retry mechanism for Marketplace API calls "
                "to handle scenarios where the local token expiration check is out of sync."
            ),
        ),
    )

    parts = build_findings_prompt_parts(batch)

    # The short section heading ("PR's key points") is skipped in favor of the
    # first substantive sentence.
    assert "Intent: This PR implements a robust token retry mechanism" in parts["pr_context"]
    assert "giphy" not in parts["pr_context"]
    # single line, capped
    intent_line = next(line for line in parts["pr_context"].splitlines() if line.startswith("Intent:"))
    assert len(intent_line) <= 210


def test_pr_context_omits_intent_when_description_is_only_noise():
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={"src/foo.py": FileContextEntry(path="src/foo.py", hunks=["@@ -1 +1 @@\n+x"])},
        checklist_applicable=[],
        pr_manifest=PullRequestManifest(
            number=1,
            title="T",
            base="main",
            head="f",
            author="a",
            description="<!-- template -->\n![img](https://x.com/i.png)\n- [ ] checkbox\n",
        ),
    )

    parts = build_findings_prompt_parts(batch)

    assert "Intent:" not in parts["pr_context"]


def test_extract_pr_intent_strips_noise_and_caps():
    from titan_plugin_github.operations.prompt_formatting_operations import extract_pr_intent

    description = (
        "<!-- PR template: fill everything -->\n"
        "![badge](https://img.shields.io/badge.svg)\n"
        "## Summary\n"
        "Adds retry logic to the token refresh flow.\n"
        "- [x] Tests added\n"
        "- [ ] Docs updated\n"
        "https://jira.example.com/TICKET-123\n"
        "More prose here.\n"
    )

    result = extract_pr_intent(description, max_chars=800)

    assert "Summary" in result
    assert "Adds retry logic" in result
    assert "More prose here." in result
    assert "badge" not in result
    assert "Tests added" not in result
    assert "jira.example.com" not in result
    assert "template" not in result


def test_extract_pr_intent_line_returns_first_meaningful_line_capped():
    from titan_plugin_github.operations.prompt_formatting_operations import extract_pr_intent_line

    assert extract_pr_intent_line("") == ""
    assert extract_pr_intent_line("A" * 500).startswith("A")
    assert len(extract_pr_intent_line("A" * 500)) == 200
    assert extract_pr_intent_line("![m](http://x.gif)\nReal intent sentence.") == "Real intent sentence."


def test_default_titan_checklist_renders_with_descriptions_too():
    """The checklist content fix must work without a project override: Titan's
    built-in DEFAULT_REVIEW_CHECKLIST (served by ChecklistManager when no
    .titan/review/checklist.yaml exists) must reach the findings prompt with
    name + description, same as any project checklist."""
    from titan_plugin_github.checklists.defaults import DEFAULT_REVIEW_CHECKLIST
    from titan_plugin_github.operations.findings_operations import _checklist_to_json

    assert all(item.name and item.description for item in DEFAULT_REVIEW_CHECKLIST)

    rendered = _checklist_to_json(list(DEFAULT_REVIEW_CHECKLIST)[:4])

    assert '"name": "Functional Correctness"' in rendered
    assert "Logic bugs" in rendered


# ============================================================================
# build_empty_findings_rescue_batch (review-quality-007)
# ============================================================================


def _rescue_diff() -> str:
    return (
        "diff --git a/border.py b/border.py\n"
        "index 111..222 100644\n"
        "--- a/border.py\n"
        "+++ b/border.py\n"
        "@@ -1,2 +1,3 @@\n"
        " context\n"
        "+added line\n"
        " context\n"
    )


def test_rescue_batch_builds_hunks_only_entries():
    from titan_plugin_github.models.review_enums import FileReadMode
    from titan_plugin_github.operations.findings_operations import (
        RESCUE_BATCH_ID,
        build_empty_findings_rescue_batch,
    )

    batch = build_empty_findings_rescue_batch(["border.py"], _rescue_diff(), [], None)

    assert batch is not None
    assert batch.batch_id == RESCUE_BATCH_ID
    entry = batch.files_context["border.py"]
    assert entry.read_mode == FileReadMode.HUNKS_ONLY
    assert any("added line" in hunk for hunk in entry.hunks)
    assert entry.full_content is None


def test_rescue_batch_caps_files_and_skips_paths_without_hunks():
    from titan_plugin_github.operations.findings_operations import build_empty_findings_rescue_batch

    diff = _rescue_diff() + _rescue_diff().replace("border.py", "second.py") + _rescue_diff().replace(
        "border.py", "third.py"
    )
    batch = build_empty_findings_rescue_batch(
        ["missing_a.py", "border.py", "second.py", "third.py"], diff, [], None
    )

    # Paths without hunks don't burn a rescue slot; the cap (2) applies to files
    # that actually made it into the batch.
    assert batch is not None
    assert set(batch.files_context) == {"border.py", "second.py"}


def test_rescue_batch_returns_none_when_no_paths_have_hunks():
    from titan_plugin_github.operations.findings_operations import build_empty_findings_rescue_batch

    assert build_empty_findings_rescue_batch(["nope.py"], _rescue_diff(), [], None) is None


# ============================================================================
# build_cross_file_synthesis_batch + dedupe_synthesis_findings (review-quality-004)
# ============================================================================


def _synthesis_diff() -> str:
    return (
        _rescue_diff()
        + _rescue_diff().replace("border.py", "second.py")
        + _rescue_diff().replace("border.py", "third.py")
    )


def test_synthesis_batch_builds_hunks_only_entries_for_all_paths():
    from titan_plugin_github.models.review_enums import FileReadMode
    from titan_plugin_github.operations.findings_operations import (
        SYNTHESIS_BATCH_ID,
        build_cross_file_synthesis_batch,
    )

    batch = build_cross_file_synthesis_batch(
        ["border.py", "second.py", "third.py"], _synthesis_diff(), None
    )

    assert batch is not None
    assert batch.batch_id == SYNTHESIS_BATCH_ID
    # No file cap: unlike the rescue batch, every path with hunks gets an entry.
    assert set(batch.files_context) == {"border.py", "second.py", "third.py"}
    for entry in batch.files_context.values():
        assert entry.read_mode == FileReadMode.HUNKS_ONLY
        assert entry.full_content is None
        assert entry.expanded_hunks == []
        assert entry.approximate_chars > 0
    assert batch.checklist_applicable == []


def test_synthesis_batch_skips_paths_without_hunks():
    from titan_plugin_github.operations.findings_operations import (
        build_cross_file_synthesis_batch,
    )

    batch = build_cross_file_synthesis_batch(
        ["missing.py", "border.py", "second.py"], _synthesis_diff(), None
    )

    assert batch is not None
    assert set(batch.files_context) == {"border.py", "second.py"}


def test_synthesis_batch_returns_none_with_fewer_than_two_hunk_files():
    from titan_plugin_github.operations.findings_operations import (
        build_cross_file_synthesis_batch,
    )

    # Only one path with hunks (plus one without): a synthesis over one file is
    # meaningless.
    assert (
        build_cross_file_synthesis_batch(["border.py", "missing.py"], _rescue_diff(), None)
        is None
    )


def test_build_findings_prompt_parts_instructions_override():
    from titan_plugin_github.operations.findings_operations import (
        SYNTHESIS_INSTRUCTIONS,
        build_cross_file_synthesis_batch,
        build_findings_prompt_parts,
        summarize_findings_prompt_parts,
    )

    batch = build_cross_file_synthesis_batch(
        ["border.py", "second.py"], _synthesis_diff(), None
    )
    parts = build_findings_prompt_parts(batch, instructions_override=SYNTHESIS_INSTRUCTIONS)

    assert parts["instructions"] == SYNTHESIS_INSTRUCTIONS
    assert "cross-file inconsistencies" in parts["prompt"]
    assert "Only report actionable issues" not in parts["prompt"]
    # The summarizer's hardcoded keys must keep working on overridden parts.
    summary = summarize_findings_prompt_parts(parts)
    assert summary["instructions_chars"] == len(SYNTHESIS_INSTRUCTIONS)

    default_parts = build_findings_prompt_parts(batch)
    assert "Only report actionable issues" in default_parts["instructions"]


def test_dedupe_synthesis_findings_drops_similar_and_keeps_distinct():
    from titan_plugin_github.operations.findings_operations import dedupe_synthesis_findings

    existing = [
        {"path": "a.py", "line": 10, "title": "Null pointer risk in parse_config"},
        {"path": "b.py", "line": None, "title": "Missing error handling"},
        "not-a-dict",
    ]
    synthesis = [
        # Exact duplicate (same path/line/title) -> dropped.
        {"path": "a.py", "line": 10, "title": "Null pointer risk in parse_config"},
        # Near-duplicate: line within window, very similar title -> dropped.
        {"path": "a.py", "line": 12, "title": "Null pointer risk in parse_config()"},
        # Same title but different path -> kept.
        {"path": "c.py", "line": 10, "title": "Null pointer risk in parse_config"},
        # Same path/title but line far outside the window -> kept.
        {"path": "a.py", "line": 200, "title": "Null pointer risk in parse_config"},
        # Both lines None with similar title -> dropped.
        {"path": "b.py", "line": None, "title": "Missing error handling"},
        # One line None, the other not -> kept.
        {"path": "b.py", "line": 5, "title": "Missing error handling"},
        # Non-dict synthesis item dropped (it would inflate the unique count and
        # normalize would reject it anyway).
        42,
    ]

    unique = dedupe_synthesis_findings(synthesis, existing)

    assert unique == [
        {"path": "c.py", "line": 10, "title": "Null pointer risk in parse_config"},
        {"path": "a.py", "line": 200, "title": "Null pointer risk in parse_config"},
        {"path": "b.py", "line": 5, "title": "Missing error handling"},
    ]


# ============================================================================
# build_timeout_fallback_batch (worktree_reference timeout fallback)
# ============================================================================


def test_timeout_fallback_batch_builds_hunks_only_from_original():
    from titan_plugin_github.models.review_enums import FileReadMode
    from titan_plugin_github.models.review_models import FileContextEntry, FocusContextBatch
    from titan_plugin_github.operations.findings_operations import build_timeout_fallback_batch

    original = FocusContextBatch(
        batch_id="batch_2",
        files_context={
            "border.py": FileContextEntry(
                path="border.py",
                read_mode=FileReadMode.WORKTREE_REFERENCE,
                worktree_reference=True,
                review_hint="huge file",
            )
        },
    )

    fallback = build_timeout_fallback_batch(original, _rescue_diff())

    assert fallback is not None
    assert fallback.batch_id == "batch_2_retry"
    entry = fallback.files_context["border.py"]
    assert entry.read_mode == FileReadMode.HUNKS_ONLY
    assert entry.worktree_reference is False
    assert any("added line" in hunk for hunk in entry.hunks)


def test_timeout_fallback_batch_returns_none_without_hunks():
    from titan_plugin_github.models.review_enums import FileReadMode
    from titan_plugin_github.models.review_models import FileContextEntry, FocusContextBatch
    from titan_plugin_github.operations.findings_operations import build_timeout_fallback_batch

    original = FocusContextBatch(
        batch_id="batch_9",
        files_context={
            "binary.bin": FileContextEntry(
                path="binary.bin",
                read_mode=FileReadMode.WORKTREE_REFERENCE,
                worktree_reference=True,
            )
        },
    )

    assert build_timeout_fallback_batch(original, _rescue_diff()) is None


# ============================================================================
# trim_hunks_for_synthesis (synthesis budget fix)
# ============================================================================


def test_trim_hunks_keeps_line_numbering_exact():
    from titan_plugin_github.operations.findings_operations import (
        _annotate_diff_hunk,
        trim_hunks_for_synthesis,
    )

    # One change buried in 8 context lines each side (like -U20 diffs).
    body = [f" ctx{i}" for i in range(8)] + ["+added line"] + [f" ctx{i + 8}" for i in range(8)]
    hunk = "@@ -100,16 +100,17 @@\n" + "\n".join(body)

    [trimmed] = trim_hunks_for_synthesis([hunk], context_lines=3)

    # 3 context lines each side survive; header is recalculated so the annotator
    # still numbers the added line as 108 (100 + 8 lines above it originally).
    assert trimmed.startswith("@@ -105,6 +105,7 @@")
    annotated = _annotate_diff_hunk(trimmed)
    assert "108 [ADDED] added line" in annotated
    assert "ctx0" not in trimmed
    assert "ctx5" in trimmed


def test_trim_hunks_splits_distant_changes_into_sub_hunks():
    from titan_plugin_github.operations.findings_operations import trim_hunks_for_synthesis

    body = (
        ["+first change"]
        + [f" gap{i}" for i in range(20)]
        + ["+second change"]
    )
    hunk = "@@ -1,20 +1,22 @@\n" + "\n".join(body)

    trimmed = trim_hunks_for_synthesis([hunk], context_lines=3)

    assert len(trimmed) == 2
    assert "first change" in trimmed[0] and "second change" not in trimmed[0]
    assert "second change" in trimmed[1]
    # Bulk of the gap is gone.
    assert sum(len(t) for t in trimmed) < len(hunk)


def test_trim_hunks_passes_through_short_or_headerless_hunks():
    from titan_plugin_github.operations.findings_operations import trim_hunks_for_synthesis

    short = "@@ -1,2 +1,3 @@\n context\n+added\n context"
    headerless = "not a hunk at all"

    assert trim_hunks_for_synthesis([short]) == [short]
    assert trim_hunks_for_synthesis([headerless]) == [headerless]


def test_synthesis_batch_trims_wide_context_hunks():
    from titan_plugin_github.operations.findings_operations import build_cross_file_synthesis_batch

    def _wide_diff(path: str) -> str:
        body = [f" pad{i}" for i in range(20)] + ["+added line"] + [f" pad{i + 20}" for i in range(20)]
        return (
            f"diff --git a/{path} b/{path}\n"
            "index 111..222 100644\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1,40 +1,41 @@\n" + "\n".join(body) + "\n"
        )

    diff = _wide_diff("a.py") + _wide_diff("b.py")
    batch = build_cross_file_synthesis_batch(["a.py", "b.py"], diff, None)

    assert batch is not None
    for entry in batch.files_context.values():
        assert entry.approximate_chars < 200  # vs ~360 chars of untrimmed padding
        assert all("pad0" not in hunk for hunk in entry.hunks)


def test_timeout_fallback_batch_propagates_batch_context():
    """The bounded retry must not silently lose the original batch's guidance:
    checklist, existing-comment context, related files and PR manifest carry over."""
    from titan_plugin_github.models.review_enums import FileReadMode
    from titan_plugin_github.models.review_models import (
        FileContextEntry,
        FocusContextBatch,
        PullRequestManifest,
        ReviewChecklistItem,
    )
    from titan_plugin_github.models.review_enums import ChecklistCategory
    from titan_plugin_github.operations.findings_operations import build_timeout_fallback_batch

    manifest = PullRequestManifest(
        number=7, title="T", base="main", head="feat", author="a", description=""
    )
    checklist = [
        ReviewChecklistItem(id=ChecklistCategory.ERROR_HANDLING, name="Errors", description="d")
    ]
    original = FocusContextBatch(
        batch_id="batch_2",
        files_context={
            "border.py": FileContextEntry(
                path="border.py",
                read_mode=FileReadMode.WORKTREE_REFERENCE,
                worktree_reference=True,
            )
        },
        checklist_applicable=checklist,
        related_files={"helper.py": "def helper(): ..."},
        pr_manifest=manifest,
    )

    fallback = build_timeout_fallback_batch(original, _rescue_diff())

    assert fallback is not None
    assert fallback.checklist_applicable == checklist
    assert fallback.related_files == {"helper.py": "def helper(): ..."}
    assert fallback.pr_manifest is manifest


def test_dedupe_synthesis_findings_dedupes_within_its_own_list():
    from titan_plugin_github.operations.findings_operations import dedupe_synthesis_findings

    synthesis = [
        {"path": "a.py", "line": 10, "title": "Contract mismatch"},
        {"path": "a.py", "line": 12, "title": "Contract mismatch!"},  # near-dup of the first
        {"path": "b.py", "line": 3, "title": "Other issue"},
    ]

    unique = dedupe_synthesis_findings(synthesis, [])

    assert unique == [
        {"path": "a.py", "line": 10, "title": "Contract mismatch"},
        {"path": "b.py", "line": 3, "title": "Other issue"},
    ]


def test_dedupe_synthesis_findings_lineless_requires_exact_title():
    from titan_plugin_github.operations.findings_operations import dedupe_synthesis_findings

    existing = [{"path": "a.py", "line": None, "title": "Missing error handling"}]
    synthesis = [
        # Similar-but-not-identical title with no line info on either side: kept —
        # proximity says nothing, similarity alone must not drop it.
        {"path": "a.py", "line": None, "title": "Missing error handling in retries"},
        # Exact title repeat with no lines: dropped.
        {"path": "a.py", "line": None, "title": "Missing error handling"},
    ]

    unique = dedupe_synthesis_findings(synthesis, existing)

    assert unique == [{"path": "a.py", "line": None, "title": "Missing error handling in retries"}]
