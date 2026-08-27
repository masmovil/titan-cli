"""Operations for parsing structured JSON responses from AI CLI adapters.

Centralizes the response-cleanup and JSON-extraction logic shared by every step that asks a
headless CLI for a JSON array or object (ai_review_plan, ai_review_findings,
ai_thread_resolution), so there is exactly one implementation to fix or extend.
"""

import json
from typing import Literal, Union

from titan_cli.core.result import ClientError, ClientResult, ClientSuccess

# Distinct from the 300s/240s full-analysis timeouts: this retry only asks the CLI to
# reformat text it already produced, not to redo the review.
REFORMAT_RETRY_TIMEOUT_SECONDS = 45


def extract_json_payload(text: str, kind: Literal["array", "object"]) -> ClientResult[Union[list, dict]]:
    """Strip markdown fences and parse the outermost JSON array/object out of CLI output."""
    opening, closing = ("[", "]") if kind == "array" else ("{", "}")
    cleaned = _strip_markdown_fences(text)
    start = cleaned.find(opening)
    end = cleaned.rfind(closing) + 1
    if start == -1 or end == 0:
        return ClientError(
            error_message=f"No JSON {kind} found in response", error_code="NO_JSON_PAYLOAD", log_level="warning"
        )
    try:
        payload = json.loads(cleaned[start:end])
    except json.JSONDecodeError as e:
        return ClientError(error_message=str(e), error_code="JSON_PARSE_ERROR", log_level="warning")
    return ClientSuccess(data=payload)


def build_json_reformat_prompt(previous_output: str, kind: Literal["array", "object"]) -> str:
    """Build a short follow-up prompt asking the CLI to reformat its own prior output as JSON."""
    noun = "array" if kind == "array" else "object"
    return (
        "Your previous response could not be parsed as JSON.\n\n"
        f"--- Previous response ---\n{previous_output}\n--- End of previous response ---\n\n"
        f"Reformat that response as a single valid JSON {noun} matching the schema you were "
        "originally asked for. Do not redo the analysis and do not add any commentary — "
        f"respond with ONLY the JSON {noun}, nothing before or after it."
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove outer markdown code fences from a CLI response."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n")
    return "\n".join(lines[1:-1]) if len(lines) > 2 else stripped
