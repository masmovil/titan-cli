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
