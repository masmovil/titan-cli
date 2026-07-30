from titan_plugin_github.models.review_enums import FindingSeverity, ReviewActionSource, ReviewActionType
from titan_plugin_github.models.review_models import Finding, ReviewActionProposal
from titan_plugin_github.operations.review_action_operations import (
    build_new_comment_actions,
    build_review_action_payload,
    detect_head_sha_drift,
    extract_diff_hunk_for_action,
    resolve_action_anchors,
)
from titan_plugin_github.widgets.comment_view import CommentView


DIFF = """\
diff --git a/src/foo.py b/src/foo.py
index abc..def 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -10,3 +10,4 @@
 def hello():
     print(\"hello\")
+    print(\"world\")
     return True
"""


def test_build_new_comment_actions_keeps_anchor_data():
    finding = Finding(
        severity=FindingSeverity.IMPORTANT,
        category="functional_correctness",
        path="src/foo.py",
        line=999,
        title="Test finding",
        why="Why",
        evidence='print("world")',
        snippet='print("world")',
        suggested_comment="Comment",
    )

    actions = build_new_comment_actions([finding])

    assert actions[0].anchor_snippet == 'print("world")'
    assert actions[0].evidence == 'print("world")'


def test_build_review_action_payload_uses_pre_resolved_line():
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=999,
        resolved_line=12,
        resolution_source="snippet",
        title="Test",
        body="Comment body",
        reasoning="Why",
        anchor_snippet='print("world")',
        evidence='print("world")',
    )

    payload = build_review_action_payload([action], commit_sha="abc123", diff=DIFF)

    assert payload["comments"][0]["line"] == 12
    assert "body" not in payload


def test_build_review_action_payload_falls_back_without_resolved_line():
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=999,
        title="Test",
        body="Comment body",
        reasoning="Why",
        anchor_snippet='print("world")',
        evidence='print("world")',
    )

    payload = build_review_action_payload([action], commit_sha="abc123", diff=DIFF)

    assert payload["comments"] == []
    assert payload["body"] == "**src/foo.py** (line 999):\nComment body"


def test_extract_diff_hunk_for_action_returns_none_without_resolved_anchor():
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=999,
        title="Test",
        body="Comment body",
        reasoning="Why",
        anchor_snippet="missing_snippet",
        evidence="missing_snippet",
    )

    assert extract_diff_hunk_for_action(action, DIFF) is None


def test_extract_diff_hunk_for_action_uses_pre_resolved_line():
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=999,
        resolved_line=12,
        title="Test",
        body="Comment body",
        reasoning="Why",
        anchor_snippet='print("world")',
        evidence='print("world")',
    )

    hunk = extract_diff_hunk_for_action(action, DIFF)

    assert hunk is not None
    assert hunk.startswith("@@")
    assert 'print("world")' in hunk


def test_resolve_action_anchors_persists_resolved_line():
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=999,
        original_line=999,
        title="Test",
        body="Comment body",
        reasoning="Why",
        anchor_snippet='print("world")',
        evidence='print("world")',
    )

    resolved = resolve_action_anchors([action], DIFF)[0]

    assert resolved.resolved_line == 12
    assert resolved.original_line == 999
    assert resolved.resolution_source == "snippet"
    assert resolved.anchor_confidence == "high"
    assert resolved.inline_reason == "snippet_match"
    assert resolved.is_inline_safe_for_github is True
    assert "resolved via snippet" in resolved.why_inline_allowed


def test_comment_view_from_action_prefers_resolved_line_label():
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=999,
        original_line=999,
        resolved_line=12,
        resolution_source="snippet",
        title="Test",
        body="Comment body",
        reasoning="Why",
    )

    view = CommentView.from_action(action, diff_hunk="@@ -10,1 +10,2 @@")

    assert view.line == 12
    assert view.line_label == "Line 12 (AI 999 via snippet)"


# ---------------------------------------------------------------------------
# D-008: publish gate validates against GitHub's diff, not the -U20 context diff
# ---------------------------------------------------------------------------

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


def _make_action(resolved_line):
    return ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=resolved_line,
        resolved_line=resolved_line,
        resolution_source="validated_line",
        title="Test",
        body="Comment body",
        reasoning="Why",
    )


def test_payload_rejects_wide_context_only_line_with_github_diff_attached():
    """The D-004 422 case: line 10 is valid in the -U20 diff but absent from GitHub's."""
    from titan_plugin_github.managers.diff_context_manager import DiffContextManager

    manager = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)
    manager.attach_github_diff(GITHUB_U3_DIFF)

    payload = build_review_action_payload(
        [_make_action(10), _make_action(20)],
        commit_sha="abc123",
        diff=WIDE_CONTEXT_DIFF,
        diff_manager=manager,
    )

    # line 20 (added, in GitHub's hunk) goes inline; line 10 degrades to the body
    assert [c["line"] for c in payload["comments"]] == [20]
    assert "line 10" in payload["body"]


def test_payload_without_github_diff_falls_back_to_added_lines_only():
    from titan_plugin_github.managers.diff_context_manager import DiffContextManager

    manager = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)

    payload = build_review_action_payload(
        [_make_action(18), _make_action(20)],
        commit_sha="abc123",
        diff=WIDE_CONTEXT_DIFF,
        diff_manager=manager,
    )

    # only the added line survives inline; the context line (18) degrades safely
    assert [c["line"] for c in payload["comments"]] == [20]
    assert "line 18" in payload["body"]


def test_resolve_action_anchors_marks_inline_safety_from_publishable_lines():
    from titan_plugin_github.managers.diff_context_manager import DiffContextManager

    manager = DiffContextManager.from_diff(WIDE_CONTEXT_DIFF)
    manager.attach_github_diff(GITHUB_U3_DIFF)

    actions = resolve_action_anchors(
        [_make_action(10), _make_action(20)],
        diff=WIDE_CONTEXT_DIFF,
        diff_manager=manager,
    )

    by_line = {a.resolved_line: a for a in actions}
    assert by_line[20].is_inline_safe_for_github is True
    assert by_line[10].is_inline_safe_for_github is False


# ---------------------------------------------------------------------------
# Unresolved anchors must not be displayed as if they were verified
# ---------------------------------------------------------------------------


def _unresolved_action(action_type=ReviewActionType.NEW_COMMENT, line=102):
    return ReviewActionProposal(
        action_type=action_type,
        source=ReviewActionSource.NEW_FINDING,
        path="src/findings_operations.py",
        line=line,
        original_line=line,
        resolved_line=None,
        title="Test",
        body="Comment body",
        reasoning="Why",
        thread_id="t1" if action_type != ReviewActionType.NEW_COMMENT else None,
    )


def test_unresolved_new_comment_is_labelled_as_outside_the_diff():
    """The finding is real but about pre-existing code the PR never touched, so the AI's
    line number was never validated — showing it bare claimed precision nothing backs."""
    view = CommentView.from_action(_unresolved_action())

    assert view.line_label == "⚠ outside this PR's diff (AI said 102)"


def test_unresolved_new_comment_carries_no_line():
    """With no line there is no code block, which matches
    extract_diff_hunk_for_action returning no hunk for an unresolved anchor."""
    view = CommentView.from_action(_unresolved_action())

    assert view.line is None


def test_unresolved_new_comment_without_any_line_still_says_outside_diff():
    view = CommentView.from_action(_unresolved_action(line=None))

    assert view.line_label == "⚠ outside this PR's diff"


def test_thread_reply_keeps_its_line_when_unresolved():
    """A reply inherits the existing thread's position, which GitHub already accepted —
    it is not an anchoring failure and must not be labelled as one."""
    view = CommentView.from_action(_unresolved_action(ReviewActionType.REPLY_TO_THREAD, line=541))

    assert view.line_label == "Line 541"
    assert view.line == 541


def test_resolved_new_comment_is_unaffected():
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="src/foo.py",
        line=12,
        original_line=12,
        resolved_line=12,
        resolution_source="validated_line",
        title="Test",
        body="Comment body",
        reasoning="Why",
    )

    view = CommentView.from_action(action)

    assert view.line == 12
    assert view.line_label == "Line 12"


# ---------------------------------------------------------------------------
# Head SHA drift: resolved lines describe one specific commit's diff
# ---------------------------------------------------------------------------

_SHA_A = "a1b2c3d4" + "0" * 32
_SHA_B = "e5f6a7b8" + "0" * 32


class TestDetectHeadShaDrift:
    def test_same_sha_is_not_drift(self):
        drift = detect_head_sha_drift(_SHA_A, _SHA_A)

        assert drift.drifted is False
        assert drift.message == ""

    def test_different_sha_is_drift_with_both_shas_in_the_message(self):
        drift = detect_head_sha_drift(_SHA_A, _SHA_B)

        assert drift.drifted is True
        assert "a1b2c3d4" in drift.message
        assert "e5f6a7b8" in drift.message

    def test_unknown_current_sha_is_not_reported_as_drift(self):
        """An unverifiable comparison is not evidence of a change, and the publish
        gate still validates every line against the diff."""
        assert detect_head_sha_drift(_SHA_A, None).drifted is False
        assert detect_head_sha_drift(_SHA_A, "").drifted is False

    def test_unknown_reviewed_sha_is_not_reported_as_drift(self):
        assert detect_head_sha_drift(None, _SHA_B).drifted is False

    def test_whitespace_is_ignored(self):
        assert detect_head_sha_drift(f"  {_SHA_A}\n", _SHA_A).drifted is False


def test_force_general_body_sends_publishable_lines_to_the_body():
    """The drift response: line 12 is perfectly publishable, but it describes the
    old commit's diff, so it must not be published inline."""
    payload = build_review_action_payload(
        [_make_action(12)], commit_sha="abc123", diff=DIFF, force_general_body=True
    )

    assert payload["comments"] == []
    assert "src/foo.py" in payload["body"]
    assert "(line 12)" in payload["body"]


def test_force_general_body_defaults_to_inline_placement():
    payload = build_review_action_payload([_make_action(12)], commit_sha="abc123", diff=DIFF)

    assert payload["comments"][0]["line"] == 12
