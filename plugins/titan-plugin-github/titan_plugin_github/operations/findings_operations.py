"""Operations for building AI prompts for focused findings review."""

import json
from typing import Any

from titan_cli.core.result import ClientError, ClientResult, ClientSuccess

from ..models.review_models import Finding, FocusContextBatch, ReviewChecklistItem
from .ai_response_parsing_operations import extract_json_payload
from .prompt_formatting_operations import comment_context_to_json, extract_pr_intent_line


def build_findings_prompt_parts(
    batch: FocusContextBatch, *, instructions_override: str | None = None
) -> dict[str, str]:
    """Build prompt parts separately so callers can log size breakdowns.

    `instructions_override` replaces the default instructions block while keeping the
    rest of the prompt skeleton (PR context, existing comments, axes, code, schema)
    identical — used by the cross-file synthesis batch, whose review target is
    different from a normal per-file batch.
    """
    checklist_json = _checklist_to_json(batch.checklist_applicable)
    comments_json = comment_context_to_json(batch.comment_context)
    files_text = _files_context_to_text(batch.files_context)
    related_text = _related_files_to_text(batch.related_files)
    pr_context = _pr_context_to_text(batch)
    schema = _finding_schema()

    instructions = instructions_override or """- Only report actionable issues: correctness, error handling, security, validation, API, concurrency, meaningful semantic correctness, state consistency, or missing regression coverage when clearly required
- Also report changes that preserve execution but alter the observable meaning of data, events, labels, classifications, or results
- Also report changes that degrade fidelity of recorded, serialized, converted, or displayed data even if the code still runs
- Also report changes that remove an important previous guarantee such as success/failure signaling, fallback behavior, or state consistency
- Do not repeat issues already covered by Existing Comments
- Do not report deleted lines as findings
- Do not speculate beyond the shown code
- Do not claim that a function, overload, or parameter does not exist unless the relevant declaration is clearly visible in the provided context
- Prefer describing an observable behavior risk over making an unverified compilation claim
- Do not report code style preferences, refactor suggestions, architecture preferences, or naming opinions without observable impact
- Include a short `snippet` copied from the exact added/context line that should anchor the comment; use null only if no stable inline anchor exists
- If the repository exposes project instructions, skills, or review documentation in the current working tree, use them when relevant, but do not depend on them
- If there are no findings, return []"""

    prompt = f"""You are performing a focused pull request code review.

This is one bounded review batch. Review only the provided code and report actionable problems that are actually present.

## PR Context
{pr_context}

## Existing Comments (do not duplicate these)
{comments_json}

## Review Axes
{checklist_json}

## Code to Review
{files_text}{related_text}

## Instructions
{instructions}

Respond ONLY with a valid JSON array matching this schema. Do not include any prose before or after the JSON.
{schema}
"""

    return {
        "pr_context": pr_context,
        "comments": comments_json,
        "review_axes": checklist_json,
        "files_context": files_text,
        "related_context": related_text,
        "instructions": instructions,
        "schema": schema,
        "prompt": prompt,
    }


def _pr_context_to_text(batch: FocusContextBatch) -> str:
    if not batch.pr_manifest:
        return f"Batch {batch.batch_id}"
    pr = batch.pr_manifest
    # One-line intent only (cap 200 chars ≈ 50 tokens): this block repeats once per
    # batch, so it must stay minimal (D-002 token mandate). The fuller trimmed
    # description goes to the single-call plan phase instead.
    intent = extract_pr_intent_line(pr.description)
    return (
        f"PR #{pr.number}: {_short_title(pr.title)}\n"
        + (f"Intent: {intent}\n" if intent else "")
        + f"{pr.base} -> {pr.head}\n"
        f"Batch: {batch.batch_id}"
    )


_CHECKLIST_DESCRIPTION_CAP = 200
"""Hard cap per checklist description in the findings prompt (D-002 token mandate:
~590 chars ≈ 150 tokens per batch for 4 real items — measured on ragnarok's checklist)."""


def _checklist_to_json(checklist: list[ReviewChecklistItem]) -> str:
    return json.dumps(
        [
            {
                "id": str(item.id),
                "name": item.name,
                "description": item.description[:_CHECKLIST_DESCRIPTION_CAP],
            }
            for item in checklist[:4]
        ],
        indent=2,
    )
def _files_context_to_text(files_context: dict) -> str:
    if not files_context:
        return "(no files to review)\n"

    parts: list[str] = []
    for path, entry in files_context.items():
        parts.append(f"### {path}")
        if entry.worktree_reference:
            parts.append("Read from worktree instead of inline context.")
            if entry.review_hint:
                parts.append(entry.review_hint)
            if entry.changed_hunk_headers:
                parts.append("Changed regions to inspect first:")
                parts.extend(f"- {header}" for header in entry.changed_hunk_headers)
        elif entry.full_content:
            parts.append("```")
            parts.append(_add_line_numbers(entry.full_content))
            parts.append("```")
        elif entry.expanded_hunks:
            for hunk in entry.expanded_hunks:
                parts.append("```")
                parts.append(_annotate_diff_hunk(hunk))
                parts.append("```")
        else:
            for hunk in entry.hunks:
                parts.append("```")
                parts.append(_annotate_diff_hunk(hunk))
                parts.append("```")
        parts.append("")
    return "\n".join(parts)


def _related_files_to_text(related_files: dict[str, str]) -> str:
    if not related_files:
        return ""
    parts = ["\n## Related Context"]
    for label, content in related_files.items():
        parts.extend([f"\n### {label}", "```", content[:2000], "```"])
    return "\n".join(parts) + "\n"


def _add_line_numbers(content: str) -> str:
    lines = content.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{str(i + 1).rjust(width)} | {line}" for i, line in enumerate(lines))


_DIFF_HUNK_MARKER = "# --- diff hunk ---"


def _annotate_diff_hunk(hunk: str) -> str:
    import re

    lines = hunk.splitlines()
    if not lines:
        return ""

    new_line_start = None
    header_line = None
    for line in lines:
        if line.startswith("@@"):
            header_line = line
            match = re.search(r"\+(\d+)", line)
            if match:
                new_line_start = int(match.group(1))
            break

    if new_line_start is None:
        return "\n".join(lines)

    # `expanded_hunks` entries (DiffContextManager.build_expanded_hunks) prepend a
    # "surrounding context" block of raw file lines (no diff +/-/space prefixes) before the
    # real diff hunk. Only the portion after the marker is actual diff content — annotating
    # the preamble too would misread indented raw code lines as numbered [CONTEXT] diff lines
    # and corrupt the line counter for everything that follows.
    preamble: list[str] = []
    diff_lines = lines
    if _DIFF_HUNK_MARKER in lines:
        marker_idx = lines.index(_DIFF_HUNK_MARKER)
        preamble = lines[: marker_idx + 1]
        diff_lines = lines[marker_idx + 1 :]

    result = list(preamble) if preamble else ([header_line] if header_line else [])
    current_line = new_line_start
    width = len(str(current_line + 100))

    for line in diff_lines:
        if line.startswith("@@"):
            continue
        if line.startswith("---") or line.startswith("+++"):
            result.append(line)
        elif line.startswith("-"):
            result.append(f"[DELETED - do not review] {line[1:]}")
        elif line.startswith("+"):
            result.append(f"{str(current_line).rjust(width)} [ADDED] {line[1:]}")
            current_line += 1
        elif line.startswith(" "):
            result.append(f"{str(current_line).rjust(width)} [CONTEXT] {line[1:]}")
            current_line += 1
        else:
            result.append(line)
    return "\n".join(result)


def _finding_schema() -> str:
    return json.dumps(
        [
            {
                "severity": "<blocking|important|nit>",
                "category": "<problem category>",
                "path": "<file path>",
                "line": "<line or null>",
                "title": "<short actionable title>",
                "why": "<why this is a problem>",
                "evidence": "<exact supporting snippet>",
                "snippet": "<short anchor snippet from the target line or null>",
                "suggested_comment": "<ready-to-post GitHub review comment>",
            }
        ],
        indent=2,
    )


FINDINGS_DISALLOWED_TOOLS = ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent")
"""Tools removed from the CLI's session for `ai_review_findings` calls.

A findings-review call never needs to modify files, fetch the web, or spawn a subagent, and
`Bash` is the exact vector traced (D-011) to unbounded, mostly unproductive exploration —
recursive shell greps/finds across whole directory trees, not scoped to the worktree the way
`Read`/`Grep`/`Glob` are. Those three stay available: they cover the same legitimate
cross-file lookups (an imported type, a caller, a test) through Claude Code's own bounded
tools instead of arbitrary shell recursion.
"""

FINDINGS_WORKTREE_REFERENCE_EFFORT = "medium"
"""Reasoning-effort tier for findings batches that include a worktree_reference file.

Removing Bash alone (`FINDINGS_DISALLOWED_TOOLS`) didn't reduce O-003's duration/timeout —
a real replay showed Claude still takes ~15 Read/Grep turns and ~330s regardless of which
tool is available, while Codex/Gemini cover similar ground in far fewer output tokens and a
fraction of the time. Capping effort at "medium" (vs. the session default) cut a real replay
from ~330s/$1.10 to ~170s/$0.78 while still surfacing a genuine bug an independent CLI
(Gemini) also found — "low" was faster still (~50s/$0.34) but missed that bug, so "medium" is
the current balance. Provisional pending more real-PR data, same as
`WORKTREE_REFERENCE_ESTIMATED_CHARS` (O-001).
"""


def findings_json_schema() -> dict[str, Any]:
    """JSON Schema for `--json-schema`, enforcing findings as a tool call instead of
    relying on the model to follow a "respond only with JSON" prompt instruction.

    Wrapped in an object because Anthropic's structured-output tool schema requires a
    top-level "object" type; the array of findings lives under the "findings" key.
    """
    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": ["blocking", "important", "nit"]},
                        "category": {"type": "string"},
                        "path": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "title": {"type": "string"},
                        "why": {"type": "string"},
                        "evidence": {"type": "string"},
                        "snippet": {"type": ["string", "null"]},
                        "suggested_comment": {"type": "string"},
                    },
                    "required": ["severity", "category", "path", "title", "why", "evidence", "suggested_comment"],
                },
            }
        },
        "required": ["findings"],
    }


def parse_findings_response(stdout: str, *, structured: bool) -> ClientResult[list]:
    """Parse a findings-batch CLI response.

    When `structured` is True (the adapter enforced `findings_json_schema()`), stdout is
    the schema envelope `{"findings": [...]}` and this unwraps the `findings` key.
    Otherwise stdout is free text and this falls back to extracting a bare JSON array.
    """
    if not structured:
        return extract_json_payload(stdout, kind="array")
    match extract_json_payload(stdout, kind="object"):
        case ClientSuccess(data=payload) if isinstance(payload, dict) and "findings" in payload:
            return ClientSuccess(data=payload["findings"])
        case ClientSuccess():
            return ClientError(
                error_message="Structured response missing 'findings' field",
                error_code="MISSING_FINDINGS_FIELD",
                log_level="warning",
            )
        case error:
            return error


def build_default_findings() -> list[Finding]:
    return []


RESCUE_BATCH_ID = "rescue_1"
RESCUE_MAX_FILES = 2


def build_empty_findings_rescue_batch(
    borderline_paths: list[str],
    diff: str,
    checklist: list[ReviewChecklistItem],
    pr_manifest,
    diff_manager=None,
) -> FocusContextBatch | None:
    """Build one extra findings batch from borderline candidate files.

    Used when the main batches return zero findings on a PR the strategy flagged as
    suspicious-if-empty: instead of just noting that borderline files went unreviewed,
    review up to RESCUE_MAX_FILES of them in hunks_only mode. Returns None when none
    of the paths have diff hunks.
    """
    from ..models.review_enums import FileReadMode
    from ..models.review_models import FileContextEntry
    from .context_resolution_operations import extract_hunks_only

    files_context: dict[str, FileContextEntry] = {}
    for path in borderline_paths:
        if len(files_context) >= RESCUE_MAX_FILES:
            break
        hunks = extract_hunks_only(diff, path, diff_manager=diff_manager)
        # A borderline candidate without hunks (binary, rename-only) shouldn't burn
        # one of the rescue slots.
        if not hunks:
            continue
        files_context[path] = FileContextEntry(
            path=path,
            read_mode=FileReadMode.HUNKS_ONLY,
            hunks=hunks,
            approximate_chars=sum(len(hunk) for hunk in hunks),
        )

    if not files_context:
        return None

    return FocusContextBatch(
        batch_id=RESCUE_BATCH_ID,
        files_context=files_context,
        checklist_applicable=checklist[:4],
        pr_manifest=pr_manifest,
    )


SYNTHESIS_BATCH_ID = "synthesis_1"

FINDINGS_SYNTHESIS_EFFORT = "medium"
"""The synthesis prompt is the largest findings prompt shape (every hunk of the PR at
once); cap reasoning at medium like worktree_reference batches — big context, bounded
reasoning."""

SYNTHESIS_INSTRUCTIONS = """- This batch shows ALL changed hunks of this PR together. Look ONLY for cross-file inconsistencies introduced by this PR
- Report contract mismatches: a signature, return shape, field, event, or error contract changed in one file while a caller/consumer in another file shown here still uses the old contract
- Report missed call sites: a rename, parameter change, or behavior change applied in some of these files but not in others shown here
- Report inconsistent naming or semantics for the same concept across the changed files
- Do NOT report single-file issues of any kind — those were already reviewed in earlier batches
- Do not repeat issues already covered by Existing Comments
- Do not report deleted lines as findings
- Do not speculate beyond the shown hunks; unchanged call sites outside this diff are out of scope
- Include a short `snippet` copied from the exact added/context line that should anchor the comment; use null only if no stable inline anchor exists
- If there are no cross-file inconsistencies, return []"""


def build_cross_file_synthesis_batch(
    focus_paths: list[str],
    diff: str,
    pr_manifest,
    diff_manager=None,
) -> FocusContextBatch | None:
    """Build the cross-file synthesis batch: every focus file's hunks together.

    Per-file batches are structurally blind to interactions between the PR's own
    changes; this batch re-combines all reviewed paths in hunks_only mode (no
    expansion, no full files) so the model can look for cross-file inconsistencies.
    ">1 focus file" means >1 distinct path — a single batch holding several files
    qualifies. Paths without diff hunks (binary, rename-only) are skipped. Returns
    None when fewer than 2 paths end up with hunks: a synthesis over one file is
    meaningless. There is deliberately no file cap — the caller's budget check is
    the cap (over budget -> skip, no split/degrade).

    `checklist_applicable` stays empty: the synthesis instructions are the single
    review axis, and this batch already re-sends every hunk (D-002 token mandate).
    """
    from ..models.review_enums import FileReadMode
    from ..models.review_models import FileContextEntry
    from .context_resolution_operations import extract_hunks_only

    files_context: dict[str, FileContextEntry] = {}
    for path in focus_paths:
        hunks = extract_hunks_only(diff, path, diff_manager=diff_manager)
        if not hunks:
            continue
        files_context[path] = FileContextEntry(
            path=path,
            read_mode=FileReadMode.HUNKS_ONLY,
            hunks=hunks,
            approximate_chars=sum(len(hunk) for hunk in hunks),
        )

    if len(files_context) < 2:
        return None

    return FocusContextBatch(
        batch_id=SYNTHESIS_BATCH_ID,
        files_context=files_context,
        checklist_applicable=[],
        pr_manifest=pr_manifest,
    )


def dedupe_synthesis_findings(
    synthesis_raw: list,
    existing_raw: list,
    *,
    line_window: int = 5,
    title_similarity_threshold: float = 0.75,
) -> list:
    """Drop synthesis findings that duplicate a per-file batch finding.

    Works on raw (pre-normalization) dicts because it runs inside the findings step,
    before Finding models exist. A synthesis finding is a duplicate when an existing
    raw finding has the same path AND a line within the window (both-None counts as
    close, one-None does not) AND a similar title (exact lowercase match or
    SequenceMatcher ratio above the threshold). Thresholds mirror
    `validators.is_duplicate`, which cannot be reused directly — it compares a Finding
    against an existing-comment index entry, not two findings. Non-dict items in
    either list are tolerated: raw AI output is untrusted.
    """
    from difflib import SequenceMatcher

    def _lines_close(line_a, line_b) -> bool:
        if line_a is None and line_b is None:
            return True
        if line_a is None or line_b is None:
            return False
        try:
            return abs(int(line_a) - int(line_b)) <= line_window
        except (TypeError, ValueError):
            return False

    def _titles_similar(title_a: str, title_b: str) -> bool:
        if title_a == title_b:
            return True
        return SequenceMatcher(None, title_a, title_b).ratio() > title_similarity_threshold

    existing = [item for item in existing_raw if isinstance(item, dict)]
    unique: list = []
    for candidate in synthesis_raw:
        if not isinstance(candidate, dict):
            unique.append(candidate)
            continue
        candidate_title = str(candidate.get("title", "")).lower()
        is_duplicate = any(
            candidate.get("path") == item.get("path")
            and _lines_close(candidate.get("line"), item.get("line"))
            and _titles_similar(candidate_title, str(item.get("title", "")).lower())
            for item in existing
        )
        if not is_duplicate:
            unique.append(candidate)
    return unique


def summarize_findings_prompt_parts(parts: dict[str, str]) -> dict[str, Any]:
    """Return character counts for each prompt block."""
    return {
        "pr_context_chars": len(parts["pr_context"]),
        "comment_context_chars": len(parts["comments"]),
        "review_axes_chars": len(parts["review_axes"]),
        "files_context_chars": len(parts["files_context"]),
        "related_context_chars": len(parts["related_context"]),
        "instructions_chars": len(parts["instructions"]),
        "schema_chars": len(parts["schema"]),
    }


def _short_title(title: str, limit: int = 90) -> str:
    return title if len(title) <= limit else title[: limit - 3] + "..."
