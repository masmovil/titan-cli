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
            continue
        code_parts.append(f"### {path}\n```\n{content[:code_cap_chars]}\n```")
    code_text = "\n".join(code_parts) if code_parts else "(no code context available)"

    instructions = """- For EACH finding, actively try to REFUTE it against the code shown
- Verdict "refuted": the code visibly contradicts the finding's claim (e.g. the claimed-missing check/handler/parameter is present, the claimed behavior cannot occur in the shown code) — quote the contradicting line in `reasoning`
- Verdict "confirmed": the code supports the claim
- Verdict "uncertain": the shown code is insufficient to judge — do NOT refute on missing context
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
    """Parse the verification CLI response into a list of verdict dicts."""
    if not structured:
        return extract_json_payload(stdout, kind="array")
    match extract_json_payload(stdout, kind="object"):
        case ClientSuccess(data=payload) if isinstance(payload, dict) and isinstance(payload.get("verdicts"), list):
            return ClientSuccess(data=payload["verdicts"])
        case ClientSuccess():
            return ClientError(
                error_message="Structured response missing 'verdicts' list",
                error_code="MISSING_VERDICTS_FIELD",
                log_level="warning",
            )
        case error:
            return error


def apply_verification_verdicts(
    verified_candidates: list[Finding],
    raw_verdicts: list,
    exempt: list[Finding],
) -> VerificationOutcome:
    """Apply AI verdicts to the finding set, fail-open.

    Only an explicit "refuted" verdict with non-empty reasoning removes a finding.
    Findings with no verdict, an out-of-range index, an unknown verdict value, or a
    reasoning-less refutation are all kept.
    """
    verdict_by_index: dict[int, VerificationVerdict] = {}
    for item in raw_verdicts or []:
        try:
            verdict = VerificationVerdict.model_validate(item)
        except Exception:
            continue
        if 0 <= verdict.index < len(verified_candidates):
            verdict_by_index[verdict.index] = verdict

    kept: list[Finding] = list(exempt)
    refuted: list[Finding] = []
    refuted_reasons: list[str] = []
    for i, finding in enumerate(verified_candidates):
        verdict = verdict_by_index.get(i)
        if verdict and verdict.verdict == "refuted" and verdict.reasoning.strip():
            refuted.append(finding)
            refuted_reasons.append(verdict.reasoning.strip())
        else:
            kept.append(finding)

    return VerificationOutcome(kept=kept, refuted=refuted, refuted_reasons=refuted_reasons)


def build_verification_code_map(
    findings: list[Finding], batches: list, *, cap_chars: int = _CODE_BLOCK_CAP_CHARS
) -> dict[str, str]:
    """Map each finding's path to its focused hunks from the review batches.

    Uses hunks (or expanded hunks) only — never `full_content` — so the verification
    prompt stays small regardless of how the finding's batch read the file.
    """
    relevant_paths = {finding.path for finding in findings}
    code_map: dict[str, str] = {}
    for batch in batches or []:
        for path, entry in batch.files_context.items():
            if path not in relevant_paths or path in code_map:
                continue
            hunks = entry.expanded_hunks or entry.hunks
            if hunks:
                code_map[path] = "\n".join(hunks)[:cap_chars]
    return code_map


def summarize_verification_prompt_parts(parts: dict[str, str]) -> dict[str, Any]:
    """Return character counts for each prompt block (telemetry, D-002)."""
    return {
        "findings_chars": len(parts["findings"]),
        "code_chars": len(parts["code"]),
        "instructions_chars": len(parts["instructions"]),
    }
