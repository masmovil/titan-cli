"""Shared formatting helpers for AI review prompts."""

import json
import re

from ..models.review_models import CommentContextEntry

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_CHECKBOX_LINE_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]")
_BARE_LINK_LINE_RE = re.compile(
    r"^\s*!?\[[^\]]*\]\(https?://\S+\)\s*$|^\s*https?://\S+\s*$"
)


def extract_pr_intent(description: str, max_chars: int = 800) -> str:
    """
    Deterministically trim a PR description down to its reviewable intent.

    Strips HTML comments (template remnants), markdown images (memes/badges),
    checkbox lines, and bare-link lines; keeps prose and bullet text. Purely
    deterministic — never an AI call. Returns "" when nothing meaningful remains.
    """
    if not description:
        return ""

    text = _HTML_COMMENT_RE.sub("", description)
    text = _MD_IMAGE_RE.sub("", text)

    kept: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _CHECKBOX_LINE_RE.match(line) or _BARE_LINK_LINE_RE.match(line):
            continue
        line = line.lstrip("#").strip()
        if line:
            kept.append(line)

    result = "\n".join(kept)
    return result[:max_chars].rstrip()


_MIN_INTENT_LINE_CHARS = 30


def extract_pr_intent_line(description: str, max_chars: int = 200) -> str:
    """
    Return a single-line PR intent for per-batch prompts (~50 tokens max).

    First substantive line of the trimmed description — short lines (section
    headings like "PR's key points" survive the trim but carry no intent) are
    skipped when a longer line follows. Hard-capped. Empty string when the
    description has no reviewable prose.
    """
    intent = extract_pr_intent(description, max_chars=max_chars * 4)
    if not intent:
        return ""
    lines = intent.splitlines()
    first_substantive = next(
        (line for line in lines if len(line) >= _MIN_INTENT_LINE_CHARS), lines[0]
    )
    return first_substantive[:max_chars].rstrip()


def comment_context_to_json(comments: list[CommentContextEntry]) -> str:
    """Serialize compact comment context entries for prompt embedding."""
    return json.dumps(
        [
            {
                "kind": entry.kind,
                "path": entry.path,
                "line": entry.line,
                "category": entry.category,
                "title": entry.title,
                "summary": entry.summary,
                "is_resolved": entry.is_resolved,
            }
            for entry in comments
        ],
        indent=2,
    )
