"""Operations for the adversarial verification pass over review findings.

One batched AI call (effort low) that tries to REFUTE each finding against the code it
targets, before findings reach the human approval gate. Fail-open by design: any error in
the pass keeps all findings — verification can only remove findings when the AI refutes
them with evidence.
"""

import json
from typing import Any

from pydantic import BaseModel

from titan_cli.core.result import ClientError, ClientResult, ClientSuccess

from ..models.review_enums import FindingSeverity
from ..models.review_models import Finding
from .ai_response_parsing_operations import extract_json_payload

VERIFICATION_EFFORT = "low"
"""Reasoning-effort tier for the verification call.

The pass re-reads findings against code already reviewed at higher effort — it judges
claims, it doesn't explore. Low keeps the added latency/cost per review small (D-002).
"""

VERIFICATION_TIMEOUT_SECONDS = 180
"""Shorter than the 300s findings timeout: one small prompt, no exploration expected."""

_CODE_BLOCK_CAP_CHARS = 3000
"""Per-file cap for the code shown to the verifier. The verifier gets each finding's
focused hunks only — never the full batch context (D-002 token mandate)."""


class VerificationVerdict(BaseModel):
    """AI verdict for one finding in the batched verification call."""

    index: int
    verdict: str  # "confirmed" | "refuted" | "uncertain"
    reasoning: str = ""


class VerificationOutcome(BaseModel):
    """Result of applying verdicts to the finding set."""

    kept: list[Finding]
    refuted: list[Finding]
    refuted_reasons: list[str]


def select_findings_for_verification(findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    """Split findings into (to_verify, exempt).

    Nit-severity findings skip verification (D-002): they are cheap for the human to
    dismiss and not worth AI time — they go straight to the gate.
    """
    to_verify = [finding for finding in findings if finding.severity != FindingSeverity.NIT]
    exempt = [finding for finding in findings if finding.severity == FindingSeverity.NIT]
    return to_verify, exempt


def build_verification_prompt_parts(
    findings: list[Finding],
    code_by_path: dict[str, str],
    *,
    code_cap_chars: int = _CODE_BLOCK_CAP_CHARS,
) -> dict[str, str]:
    """Build the batched refute-or-confirm prompt.

    `code_by_path` maps each finding's path to the visible code (hunks) it was found
    in; each block is capped so the pass stays a single small call.
    """
    findings_json = json.dumps(
        [
            {
                "index": i,
                "severity": str(finding.severity),
                "path": finding.path,
                "line": finding.line,
                "title": finding.title,
                "why": finding.why,
                "evidence": finding.evidence,
            }
            for i, finding in enumerate(findings)
        ],
        indent=2,
    )

    relevant_paths = {finding.path for finding in findings}
    code_parts: list[str] = []
    for path in sorted(relevant_paths):
        content = code_by_path.get(path)
        if not content:
            # The finding still gets a verdict slot, so the model must know there is
            # no code to judge it against — otherwise it can read absence as
            # contradiction and refute a real finding.
            code_parts.append(
                f"### {path}\n(no code context available for this file — "
                'verdicts for its findings must be "uncertain")'
            )
            continue
        code_parts.append(f"### {path}\n```\n{_cap_code(content, code_cap_chars)}\n```")
    code_text = "\n".join(code_parts) if code_parts else "(no code context available)"

    instructions = """- For EACH finding, actively try to REFUTE it against the code shown
- Verdict "refuted": the code visibly contradicts the finding's claim (e.g. the claimed-missing check/handler/parameter is present, the claimed behavior cannot occur in the shown code) — quote the contradicting line in `reasoning`
- Verdict "confirmed": the code supports the claim
- Verdict "uncertain": the shown code is insufficient to judge — do NOT refute on missing context
- The code blocks may be truncated: never treat something as absent because it is not visible in the shown excerpt
- Judge only what is claimed; do not invent new findings or re-review the code
- Return exactly one verdict per finding index"""

    prompt = f"""You are verifying findings from an automated pull request review before they reach a human reviewer. Your job is quality control: catch false positives.

## Findings to Verify
{findings_json}

## Code the Findings Refer To
{code_text}

## Instructions
{instructions}

Respond ONLY with a valid JSON array matching this schema. Do not include any prose before or after the JSON.
{_verdict_schema()}
"""

    return {
        "findings": findings_json,
        "code": code_text,
        "instructions": instructions,
        "prompt": prompt,
    }


_TRUNCATION_MARKER = "\n… [code truncated here — anything beyond this point is NOT shown, not absent]"


def _cap_code(content: str, cap_chars: int) -> str:
    """Cap a code block, marking the cut so the verifier can't read it as complete."""
    if len(content) <= cap_chars:
        return content
    return content[:cap_chars] + _TRUNCATION_MARKER


def _verdict_schema() -> str:
    return json.dumps(
        [
            {
                "index": "<finding index from the list above>",
                "verdict": "<confirmed|refuted|uncertain>",
                "reasoning": "<short justification; for refuted, quote the contradicting code>",
            }
        ],
        indent=2,
    )


def verification_json_schema() -> dict[str, Any]:
    """JSON Schema for `--json-schema`, mirroring findings_json_schema()'s object wrapper."""
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "verdict": {"type": "string", "enum": ["confirmed", "refuted", "uncertain"]},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["index", "verdict"],
                },
            }
        },
        "required": ["verdicts"],
    }


def parse_verification_response(stdout: str, *, structured: bool) -> ClientResult[list]:
    """Parse the verification CLI response into a list of verdict dicts.

    Structured mode expects the schema's object wrapper, but the shared prompt text
    asks for a bare JSON array (the unstructured shape) — a model that honors the
    prompt over the schema must still be parseable, so structured mode falls back
    to array extraction before giving up. Fail-open downstream depends on
    recovering verdicts wherever they are.
    """
    if not structured:
        return extract_json_payload(stdout, kind="array")
    object_result = extract_json_payload(stdout, kind="object")
    match object_result:
        case ClientSuccess(data=payload) if isinstance(payload, dict) and isinstance(payload.get("verdicts"), list):
            return ClientSuccess(data=payload["verdicts"])
    match extract_json_payload(stdout, kind="array"):
        case ClientSuccess(data=payload) if isinstance(payload, list):
            return ClientSuccess(data=payload)
    match object_result:
        case ClientSuccess():
            return ClientError(
                error_message="Structured response missing 'verdicts' list",
                error_code="MISSING_VERDICTS_FIELD",
                log_level="warning",
            )
        case error:
            return error


def apply_verification_verdicts(
    findings: list[Finding],
    verified_candidates: list[Finding],
    raw_verdicts: list,
    *,
    paths_with_code: set[str] | None = None,
) -> VerificationOutcome:
    """Apply AI verdicts to the finding set, fail-open.

    This is a pure filter over `findings`: the kept list preserves the input order
    (most-severe first), because downstream consumers — the human gate and the
    posted comments — render findings in that order. `verified_candidates` only
    supplies the index space the verdicts refer to.

    Only an explicit "refuted" verdict with non-empty reasoning removes a finding.
    Findings with no verdict, an out-of-range index, an unknown verdict value, or a
    reasoning-less refutation are all kept. When `paths_with_code` is given, a
    refutation of a finding whose path had NO code in the prompt is also ignored —
    the model cannot legitimately contradict code it never saw.
    """
    verdict_by_index: dict[int, VerificationVerdict] = {}
    for item in raw_verdicts or []:
        try:
            verdict = VerificationVerdict.model_validate(item)
        except Exception:
            continue
        if not (0 <= verdict.index < len(verified_candidates)):
            continue
        existing = verdict_by_index.get(verdict.index)
        if existing is None:
            verdict_by_index[verdict.index] = verdict
        elif existing.verdict == "refuted" and verdict.verdict != "refuted":
            # Duplicate indices are malformed output; when they conflict, fail-open
            # means the verdict that KEEPS the finding wins, regardless of order.
            verdict_by_index[verdict.index] = verdict

    refuted: list[Finding] = []
    refuted_reasons: list[str] = []
    refuted_ids: set[int] = set()
    for i, finding in enumerate(verified_candidates):
        verdict = verdict_by_index.get(i)
        refutable = paths_with_code is None or finding.path in paths_with_code
        if refutable and verdict and verdict.verdict == "refuted" and verdict.reasoning.strip():
            refuted.append(finding)
            refuted_reasons.append(verdict.reasoning.strip())
            refuted_ids.add(id(finding))

    kept = [finding for finding in findings if id(finding) not in refuted_ids]

    return VerificationOutcome(kept=kept, refuted=refuted, refuted_reasons=refuted_reasons)


def build_verification_code_map(findings: list[Finding], batches: list) -> dict[str, str]:
    """Map each finding's path to its focused hunks from the review batches.

    Uses hunks (or expanded hunks) only — never `full_content` — so the verification
    prompt stays small regardless of how the finding's batch read the file. Capping
    (with a visible truncation marker) happens once, in
    `build_verification_prompt_parts` — not here, or the marker could never fire.
    """
    relevant_paths = {finding.path for finding in findings}
    code_map: dict[str, str] = {}
    for batch in batches or []:
        for path, entry in batch.files_context.items():
            if path not in relevant_paths or path in code_map:
                continue
            hunks = entry.expanded_hunks or entry.hunks
            if hunks:
                code_map[path] = "\n".join(hunks)
    return code_map


def summarize_verification_prompt_parts(parts: dict[str, str]) -> dict[str, Any]:
    """Return character counts for each prompt block (telemetry, D-002)."""
    return {
        "findings_chars": len(parts["findings"]),
        "code_chars": len(parts["code"]),
        "instructions_chars": len(parts["instructions"]),
    }
