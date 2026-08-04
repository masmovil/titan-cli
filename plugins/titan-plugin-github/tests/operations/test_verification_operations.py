"""Tests for the adversarial findings-verification operations (review-quality-003)."""

import json

from titan_cli.core.result import ClientError, ClientSuccess
from titan_plugin_github.models.review_enums import FileReadMode, FindingSeverity
from titan_plugin_github.models.review_models import FileContextEntry, Finding, FocusContextBatch
from titan_plugin_github.operations.verification_operations import (
    apply_verification_verdicts,
    build_verification_code_map,
    build_verification_prompt_parts,
    parse_verification_response,
    select_findings_for_verification,
    summarize_verification_prompt_parts,
    verification_json_schema,
)


def _make_finding(
    title: str = "Null check missing",
    severity: FindingSeverity = FindingSeverity.IMPORTANT,
    path: str = "a.py",
) -> Finding:
    return Finding(
        severity=severity,
        category="error_handling",
        path=path,
        line=10,
        title=title,
        why="The value may be None",
        evidence="value.method()",
        suggested_comment="Add a null check",
    )


def test_select_findings_exempts_nits():
    important = _make_finding("Important one")
    nit = _make_finding("Nit one", severity=FindingSeverity.NIT)

    to_verify, exempt = select_findings_for_verification([important, nit])

    assert to_verify == [important]
    assert exempt == [nit]


def test_prompt_includes_findings_and_capped_code():
    finding = _make_finding(path="a.py")
    parts = build_verification_prompt_parts(
        [finding], {"a.py": "x" * 5000, "unrelated.py": "y" * 100}, code_cap_chars=100
    )

    findings_payload = json.loads(parts["findings"])
    assert findings_payload[0]["title"] == "Null check missing"
    assert findings_payload[0]["index"] == 0
    # Code is capped and only the findings' paths are included.
    assert "x" * 100 in parts["code"]
    assert "x" * 101 not in parts["code"]
    assert "unrelated.py" not in parts["code"]
    assert "REFUTE" in parts["prompt"]


def test_prompt_survives_missing_code_context():
    parts = build_verification_prompt_parts([_make_finding(path="gone.py")], {})
    assert "### gone.py" in parts["code"]
    assert "no code context available for this file" in parts["code"]


def test_parse_structured_response_unwraps_verdicts():
    stdout = json.dumps({"verdicts": [{"index": 0, "verdict": "refuted", "reasoning": "line 12 has the check"}]})
    result = parse_verification_response(stdout, structured=True)
    assert isinstance(result, ClientSuccess)
    assert result.data[0]["verdict"] == "refuted"


def test_parse_structured_response_without_verdicts_list_errors():
    result = parse_verification_response(json.dumps({"verdicts": {"index": 0}}), structured=True)
    assert isinstance(result, ClientError)
    assert result.error_code == "MISSING_VERDICTS_FIELD"


def test_parse_unstructured_response_extracts_array():
    stdout = '```json\n[{"index": 0, "verdict": "confirmed"}]\n```'
    result = parse_verification_response(stdout, structured=False)
    assert isinstance(result, ClientSuccess)
    assert result.data[0]["verdict"] == "confirmed"


def test_apply_verdicts_drops_only_evidenced_refutations():
    refuted = _make_finding("Refuted one")
    confirmed = _make_finding("Confirmed one")
    nit = _make_finding("Nit one", severity=FindingSeverity.NIT)

    outcome = apply_verification_verdicts(
        [refuted, confirmed, nit],
        [refuted, confirmed],
        [
            {"index": 0, "verdict": "refuted", "reasoning": "the check exists at line 12"},
            {"index": 1, "verdict": "confirmed", "reasoning": "claim holds"},
        ],
    )

    assert refuted in outcome.refuted
    assert outcome.refuted_reasons == ["the check exists at line 12"]
    assert confirmed in outcome.kept
    assert nit in outcome.kept
    assert refuted not in outcome.kept
    # Kept must preserve the input order (most-severe first) — exempt nits must not
    # jump ahead of verified blocking findings in the gate or the posted comments.
    assert outcome.kept == [confirmed, nit]


def test_apply_verdicts_fails_open():
    """Missing verdicts, out-of-range indices, unknown verdict values, malformed items,
    and reasoning-less refutations must all KEEP the finding."""
    findings = [_make_finding(f"f{i}") for i in range(5)]

    outcome = apply_verification_verdicts(
        findings,
        findings,
        [
            {"index": 1, "verdict": "refuted", "reasoning": ""},  # no evidence → kept
            {"index": 2, "verdict": "maybe", "reasoning": "?"},  # unknown verdict → kept
            {"index": 99, "verdict": "refuted", "reasoning": "x"},  # out of range → ignored
            {"verdict": "refuted"},  # malformed (no index) → ignored
            # index 0, 3, 4: no verdict at all → kept
        ],
    )

    assert outcome.refuted == []
    assert len(outcome.kept) == 5


def test_code_map_uses_hunks_never_full_content():
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={
            "a.py": FileContextEntry(
                path="a.py",
                read_mode=FileReadMode.FULL_FILE,
                full_content="FULL FILE CONTENT " * 500,
                hunks=["@@ -1,2 +1,3 @@\n+added line"],
            )
        },
    )

    code_map = build_verification_code_map([_make_finding(path="a.py")], [batch])

    assert "added line" in code_map["a.py"]
    assert "FULL FILE CONTENT" not in code_map["a.py"]


def test_code_map_only_includes_finding_paths_without_truncating():
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={
            "a.py": FileContextEntry(path="a.py", read_mode=FileReadMode.HUNKS_ONLY, hunks=["h" * 9000]),
            "b.py": FileContextEntry(path="b.py", read_mode=FileReadMode.HUNKS_ONLY, hunks=["other"]),
        },
    )

    code_map = build_verification_code_map([_make_finding(path="a.py")], [batch])

    # Capping (with its visible marker) happens at prompt build, not here.
    assert set(code_map) == {"a.py"}
    assert len(code_map["a.py"]) == 9000


def test_schema_and_telemetry_shapes():
    schema = verification_json_schema()
    assert schema["required"] == ["verdicts"]
    assert schema["properties"]["verdicts"]["items"]["properties"]["verdict"]["enum"] == [
        "confirmed",
        "refuted",
        "uncertain",
    ]

    parts = build_verification_prompt_parts([_make_finding()], {"a.py": "code"})
    telemetry = summarize_verification_prompt_parts(parts)
    assert set(telemetry) == {"findings_chars", "code_chars", "instructions_chars"}


# ============================================================================
# Fixes from the 2026-08-03 validation-run findings
# ============================================================================


def test_prompt_marks_paths_without_code_context():
    """A finding whose path has no code must not silently share the prompt with other
    files' code — the model could read absence as contradiction and refute it."""
    parts = build_verification_prompt_parts(
        [_make_finding(path="missing.py"), _make_finding(path="a.py")],
        {"a.py": "some code"},
    )

    assert "### missing.py" in parts["code"]
    assert "no code context available for this file" in parts["code"]
    assert 'must be "uncertain"' in parts["code"]


def test_prompt_marks_truncated_code_blocks():
    parts = build_verification_prompt_parts(
        [_make_finding(path="a.py")], {"a.py": "x" * 5000}, code_cap_chars=100
    )

    assert "code truncated here" in parts["code"]

    intact = build_verification_prompt_parts(
        [_make_finding(path="a.py")], {"a.py": "short"}, code_cap_chars=100
    )
    assert "code truncated here" not in intact["code"]


def test_apply_verdicts_ignores_refutation_without_code_context():
    """The model cannot legitimately contradict code it never saw: a refutation for a
    path outside `paths_with_code` is dropped (finding kept), deterministically."""
    no_code = _make_finding("No code one", path="missing.py")
    with_code = _make_finding("With code one", path="a.py")

    outcome = apply_verification_verdicts(
        [no_code, with_code],
        [no_code, with_code],
        [
            {"index": 0, "verdict": "refuted", "reasoning": "not present in the code"},
            {"index": 1, "verdict": "refuted", "reasoning": "check exists at line 12"},
        ],
        paths_with_code={"a.py"},
    )

    assert no_code in outcome.kept
    assert with_code in outcome.refuted
    assert outcome.refuted_reasons == ["check exists at line 12"]


def test_apply_verdicts_keeps_uncertain_findings():
    """`uncertain` is a declared verdict value and must behave as keep, not drop."""
    finding = _make_finding("Uncertain one")

    outcome = apply_verification_verdicts(
        [finding],
        [finding],
        [{"index": 0, "verdict": "uncertain", "reasoning": "not enough code shown"}],
    )

    assert outcome.refuted == []
    assert finding in outcome.kept


def test_parse_verification_response_handles_non_json_and_empty():
    """Fail-open depends on parse returning an error, never raising, on prose or
    empty output — the most likely real-world CLI failure shapes."""
    for stdout in ("I could not verify these findings, sorry.", "", "   \n"):
        for structured in (True, False):
            result = parse_verification_response(stdout, structured=structured)
            assert isinstance(result, ClientError)


def test_apply_verdicts_conflicting_duplicate_indices_prefer_keep():
    """Duplicate indices are malformed output — whichever order they arrive in, the
    verdict that KEEPS the finding must win (fail-open)."""
    finding = _make_finding("Contested one")

    for verdicts in (
        [
            {"index": 0, "verdict": "refuted", "reasoning": "stray refutation"},
            {"index": 0, "verdict": "confirmed", "reasoning": "holds"},
        ],
        [
            {"index": 0, "verdict": "confirmed", "reasoning": "holds"},
            {"index": 0, "verdict": "refuted", "reasoning": "stray refutation"},
        ],
    ):
        outcome = apply_verification_verdicts([finding], [finding], verdicts)
        assert outcome.refuted == []
        assert finding in outcome.kept


def test_parse_structured_response_accepts_bare_array():
    """The shared prompt text asks for a bare JSON array (the unstructured shape);
    a model honoring the prompt over the schema must still be parseable."""
    stdout = '[{"index": 0, "verdict": "confirmed", "reasoning": "holds"}]'
    result = parse_verification_response(stdout, structured=True)
    assert isinstance(result, ClientSuccess)
    assert result.data[0]["verdict"] == "confirmed"


def test_code_map_prefers_expanded_hunks_over_hunks():
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={
            "a.py": FileContextEntry(
                path="a.py",
                read_mode=FileReadMode.EXPANDED_HUNKS,
                hunks=["plain hunk"],
                expanded_hunks=["expanded hunk with surrounding context"],
            ),
        },
    )

    code_map = build_verification_code_map([_make_finding(path="a.py")], [batch])

    assert code_map["a.py"] == "expanded hunk with surrounding context"


def test_code_map_skips_entries_with_only_full_content():
    """A hunk-less entry contributes no code, so its findings have no context to be
    refuted against and survive verification (see `apply_verdicts`)."""
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={
            "a.py": FileContextEntry(
                path="a.py",
                read_mode=FileReadMode.FULL_FILE,
                full_content="FULL FILE CONTENT " * 500,
            ),
        },
    )

    code_map = build_verification_code_map([_make_finding(path="a.py")], [batch])

    assert "a.py" not in code_map
