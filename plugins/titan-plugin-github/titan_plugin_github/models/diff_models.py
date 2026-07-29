"""
Diff Models

Intermediate models for structured diff parsing.
Used by DiffContextManager to represent parsed diff data
without coupling to raw strings or API-specific formats.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedHunk:
    """
    A single diff hunk with pre-computed line metadata.

    Attributes:
        header: The @@ header line including any trailing context (e.g. function name)
        content: Full hunk text including header
        path: File path this hunk belongs to
        old_line_start: First line number in the old file
        old_line_count: Number of old-file lines in this hunk
        new_line_start: First line number in the new file
        new_line_count: Number of new-file lines in this hunk
        valid_review_lines: New-file line numbers valid for inline comments
                            (added '+' and context ' ' lines only, not deleted '-')
        added_lines: New-file line numbers of added ('+') lines only. Added lines
                     exist identically in any diff of the same change regardless of
                     context width, so they are always safe inline targets for GitHub.
    """
    header: str
    content: str
    path: str
    old_line_start: int
    old_line_count: int
    new_line_start: int
    new_line_count: int
    valid_review_lines: frozenset = field(default_factory=frozenset)
    added_lines: frozenset = field(default_factory=frozenset)

    @property
    def new_line_end(self) -> int:
        """Last new-file line number covered by this hunk."""
        return self.new_line_start + max(self.new_line_count - 1, 0)

    @property
    def old_line_end(self) -> int:
        """Last old-file line number covered by this hunk."""
        return self.old_line_start + max(self.old_line_count - 1, 0)

    def contains_new_line(self, line: int) -> bool:
        """Return True if `line` falls within this hunk's new-file range."""
        return self.new_line_start <= line <= self.new_line_end

    def contains_old_line(self, line: int) -> bool:
        """Return True if `line` falls within this hunk's old-file range."""
        return self.old_line_start <= line <= self.old_line_end


@dataclass
class ParsedFileDiff:
    """
    All diff hunks for a single file.

    Attributes:
        path: File path as it appears in the diff (b/ side)
        hunks: Ordered list of parsed hunks for this file
    """
    path: str
    hunks: list[ParsedHunk]

    @property
    def valid_review_lines(self) -> frozenset:
        """Union of valid review lines across all hunks."""
        result: set[int] = set()
        for hunk in self.hunks:
            result.update(hunk.valid_review_lines)
        return frozenset(result)

    @property
    def added_lines(self) -> frozenset:
        """Union of added-line numbers across all hunks."""
        result: set[int] = set()
        for hunk in self.hunks:
            result.update(hunk.added_lines)
        return frozenset(result)


@dataclass
class ParsedDiff:
    """
    Fully parsed unified diff.

    Attributes:
        files: Mapping from file path → ParsedFileDiff
        raw: Original unparsed diff string
    """
    files: dict[str, ParsedFileDiff]
    raw: str


@dataclass
class ResolvedCommentContext:
    """
    Unified context for rendering a comment in the UI.

    Produced by DiffContextManager and consumed by widgets.
    Widgets receive this instead of raw diff strings.

    Attributes:
        comment_id: Database ID of the comment
        is_outdated: Whether the comment is on stale code
        path: File path (None for PR-level comments)
        line: Effective line number (new_line for current, original_line for outdated)
        position: GitHub diff position for inline API calls (None if outdated)
        focused_diff: Trimmed diff fragment for UI display (7 before + target + 3 after)
        full_hunk: Complete hunk text when available
        original_lines: Original code lines for suggestion rendering
        body: Comment body text (for complete context reconstruction)
        author_name: Author display name (for complete context reconstruction)
        formatted_date: Pre-formatted date (for complete context reconstruction)
    """
    comment_id: int
    is_outdated: bool
    path: Optional[str]
    line: Optional[int]
    position: Optional[int]
    focused_diff: str
    full_hunk: Optional[str] = None
    original_lines: Optional[str] = None
    body: str = ""
    author_name: str = ""
    formatted_date: str = ""


__all__ = [
    "ParsedHunk",
    "ParsedFileDiff",
    "ParsedDiff",
    "ResolvedCommentContext",
]
