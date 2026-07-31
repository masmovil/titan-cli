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
    assert "(no code context available)" in parts["code"]


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
        [refuted, confirmed],
        [
            {"index": 0, "verdict": "refuted", "reasoning": "the check exists at line 12"},
            {"index": 1, "verdict": "confirmed", "reasoning": "claim holds"},
        ],
        exempt=[nit],
    )

    assert refuted in outcome.refuted
    assert outcome.refuted_reasons == ["the check exists at line 12"]
    assert confirmed in outcome.kept
    assert nit in outcome.kept
    assert refuted not in outcome.kept


def test_apply_verdicts_fails_open():
    """Missing verdicts, out-of-range indices, unknown verdict values, malformed items,
    and reasoning-less refutations must all KEEP the finding."""
    findings = [_make_finding(f"f{i}") for i in range(5)]

    outcome = apply_verification_verdicts(
        findings,
        [
            {"index": 1, "verdict": "refuted", "reasoning": ""},  # no evidence → kept
            {"index": 2, "verdict": "maybe", "reasoning": "?"},  # unknown verdict → kept
            {"index": 99, "verdict": "refuted", "reasoning": "x"},  # out of range → ignored
            {"verdict": "refuted"},  # malformed (no index) → ignored
            # index 0, 3, 4: no verdict at all → kept
        ],
        exempt=[],
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


def test_code_map_only_includes_finding_paths_and_caps():
    batch = FocusContextBatch(
        batch_id="batch_1",
        files_context={
            "a.py": FileContextEntry(path="a.py", read_mode=FileReadMode.HUNKS_ONLY, hunks=["h" * 9000]),
            "b.py": FileContextEntry(path="b.py", read_mode=FileReadMode.HUNKS_ONLY, hunks=["other"]),
        },
    )

    code_map = build_verification_code_map([_make_finding(path="a.py")], [batch], cap_chars=100)

    assert set(code_map) == {"a.py"}
    assert len(code_map["a.py"]) == 100


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
