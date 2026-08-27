"""
Fitting a unified diff into a prompt.

Any prompt built from a diff has a size limit, and the obvious way to respect it - keep the
first N characters - is a trap: git emits files in its own order, so the budget goes to
whichever files happen to come first and the rest of the change becomes invisible. What
comes back is a confident description of a fraction of the work.

These helpers keep the breadth instead. Every file is accounted for in a summary that is
cheap enough to always include in full, and the diff body itself is shared out so each file
contributes something. Both are bounded, so a prompt built this way costs about the same for
a three-file change as for a three-thousand-file one.
"""

import re
from typing import List, Tuple

MIN_CHARS_PER_FILE = 400
MAX_FILES_IN_SUMMARY = 60


def split_diff_by_file(diff_text: str) -> List[Tuple[str, str]]:
    """
    Split a unified diff into `(path, chunk)` pairs, one per file.

    Returns a single `("", diff_text)` pair when the text carries no `diff --git` headers,
    so callers can treat any input uniformly.
    """
    if not diff_text:
        return []

    chunks = [c for c in re.split(r"(?m)^(?=diff --git )", diff_text) if c.strip()]

    if not chunks or not chunks[0].startswith("diff --git "):
        return [("", diff_text)]

    result = []
    for chunk in chunks:
        match = re.match(r"diff --git a/(\S+)", chunk)
        result.append((match.group(1) if match else "", chunk))
    return result


def summarize_diff_files(diff_text: str) -> List[Tuple[str, int, int]]:
    """Count added and removed lines per file, for every file in the diff."""
    summary = []
    for path, chunk in split_diff_by_file(diff_text):
        added = len(re.findall(r"(?m)^\+(?!\+\+ )", chunk))
        removed = len(re.findall(r"(?m)^-(?!-- )", chunk))
        summary.append((path, added, removed))
    return summary


def format_file_summary(diff_text: str, max_files: int = MAX_FILES_IN_SUMMARY) -> str:
    """
    Render the per-file line counts as prompt text, or `""` if the diff has no file headers.

    Capped, because this is the one part that would otherwise grow with the size of the
    commit; past the cap the count of remaining files still says how much is not shown.
    """
    stats = [s for s in summarize_diff_files(diff_text) if s[0]]
    if not stats:
        return ""

    shown = stats[:max_files]
    lines = [f"  {path}: +{added} -{removed}" for path, added, removed in shown]
    if len(stats) > len(shown):
        lines.append(f"  [... and {len(stats) - len(shown)} more changed files ...]")
    return "\n".join(lines)


def budget_diff_across_files(diff_text: str, max_chars: int) -> str:
    """
    Fit a diff into a character budget by sharing it between files.

    Each file gets a slice and says so when its slice runs out. The per-file floor keeps a
    slice large enough to be worth reading; the running total keeps that floor from turning
    a fixed cost into one that grows with the number of files.
    """
    chunks = split_diff_by_file(diff_text)
    if not chunks or len(diff_text) <= max_chars:
        return diff_text

    per_file = max(max_chars // len(chunks), MIN_CHARS_PER_FILE)

    parts = []
    used = 0
    for index, (_path, chunk) in enumerate(chunks):
        if used >= max_chars:
            parts.append(
                f"[... {len(chunks) - index} more changed files not shown here; "
                f"they are listed with their line counts above ...]"
            )
            break
        if len(chunk) <= per_file:
            parts.append(chunk.rstrip("\n"))
            used += len(chunk)
        else:
            parts.append(
                chunk[:per_file].rstrip("\n") + "\n[... rest of this file's diff omitted ...]"
            )
            used += per_file
    return "\n".join(parts)


SAMPLED_DIFF_NOTE = (
    "The diff below is sampled: each file contributes part of its changes, and the per-file "
    "summary above is the complete picture. Weigh the whole change, not only the files whose "
    "diff you can read in full."
)


__all__ = [
    "MIN_CHARS_PER_FILE",
    "MAX_FILES_IN_SUMMARY",
    "SAMPLED_DIFF_NOTE",
    "split_diff_by_file",
    "summarize_diff_files",
    "format_file_summary",
    "budget_diff_across_files",
]
