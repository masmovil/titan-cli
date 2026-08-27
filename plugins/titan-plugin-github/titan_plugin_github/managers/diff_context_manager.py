"""
Diff Context Manager

Central hub for all diff parsing, line resolution, and context extraction.
Replaces the scattered diff logic previously spread across comment_utils,
code_review_operations, context_resolution_operations, and thread_resolution_operations.

Usage:
    manager = DiffContextManager.from_diff(pr_diff)
    hunk = manager.get_hunk_for_line("src/foo.py", 42)
    ctx  = manager.build_comment_context(ui_comment)
"""

from __future__ import annotations

import hashlib
import re
from typing import Callable, Optional

from titan_cli.core.logging import get_logger
from ..models.diff_models import (
    ParsedDiff,
    ParsedFileDiff,
    ParsedHunk,
    ResolvedCommentContext,
)
from ..models.view import UIComment

logger = get_logger(__name__)

_HUNK_HEADER_RE = re.compile(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@(.*)")
# Git quotes both paths when they contain spaces/special chars:
#   diff --git "a/my file.py" "b/my file.py"
# The trailing \r? tolerates CRLF diffs (otherwise the captured path keeps the \r
# and every subsequent lookup by path silently misses).
_FILE_HEADER_RE = re.compile(
    r'^diff --git (?:a/.+ b/(?P<path>.+?)|"a/.+" "b/(?P<quoted_path>.+?)")\r?$'
)
_COMMENT_PREFIXES = ("//", "#", "/*", "*/", "*")


class DiffContextManager:
    """
    Parses a unified diff once and exposes high-level query methods.

    All parsing happens at construction time and results are cached internally.
    Use ``from_diff`` to create instances.
    """

    def __init__(self, parsed: ParsedDiff) -> None:
        self._parsed = parsed
        # GitHub's own diff (3 context lines), when attached. The context diff above may be
        # generated with extended context (-U20) for AI quality; GitHub validates inline
        # comment lines against ITS diff only, so publishable lines must come from here.
        self._github_parsed: Optional[ParsedDiff] = None
        # Optional source of whole-file content, for code the diff does not contain at all.
        self._content_provider: Optional[Callable[[str], Optional[str]]] = None
        self._content_cache: dict[str, Optional[str]] = {}

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_diff(cls, diff: str) -> DiffContextManager:
        """
        Parse a unified diff string and return a ready-to-use manager.

        Args:
            diff: Full unified diff (e.g. from ``gh pr diff``)

        Returns:
            DiffContextManager with all hunks indexed
        """
        logger.debug(f"Parsing diff: {len(diff)} bytes")
        parsed = _parse_diff(diff)
        logger.debug(f"Parsed diff: {len(parsed.files)} files, {sum(len(f.hunks) for f in parsed.files.values())} hunks")
        return cls(parsed)

    @classmethod
    def from_file_diff(cls, file_diff: str, path: str) -> DiffContextManager:
        """
        Parse a single-file diff section (with or without ``diff --git`` header).

        Use when only a per-file slice is available (e.g. from ``extract_diff_for_file``).
        The ``path`` argument is the key used to look up results via ``get_hunks(path)``.

        Args:
            file_diff: Diff section for a single file
            path: Logical path key for this diff (used in subsequent lookups)

        Returns:
            DiffContextManager with hunks indexed under ``path``
        """
        logger.debug(f"Parsing file diff: path={path}, size={len(file_diff)} bytes")
        parsed_file = _parse_file_diff_section(path, file_diff)
        hunks_count = len(parsed_file.hunks) if parsed_file else 0
        logger.debug(f"Parsed file diff: {hunks_count} hunks")
        files = {path: parsed_file} if parsed_file else {}
        return cls(ParsedDiff(files=files, raw=file_diff))

    # ------------------------------------------------------------------
    # File / hunk lookups
    # ------------------------------------------------------------------

    def get_file(self, path: str) -> Optional[ParsedFileDiff]:
        """Return parsed file diff for ``path``, or None if not in diff."""
        result = self._parsed.files.get(path)
        logger.debug(f"get_file: path={path}, found={result is not None}")
        return result

    def get_hunks(self, path: str) -> list[ParsedHunk]:
        """Return all hunks for ``path``, empty list if file not in diff."""
        file_diff = self._parsed.files.get(path)
        hunks = file_diff.hunks if file_diff else []
        logger.debug(f"get_hunks: path={path}, count={len(hunks)}")
        return hunks

    def get_hunk_texts(self, path: str) -> list[str]:
        """Return raw hunk text blocks for ``path``."""
        return [hunk.content for hunk in self.get_hunks(path)]

    def build_expanded_hunks(
        self,
        path: str,
        file_content: str,
        extra_lines: int = 10,
    ) -> list[str]:
        """
        Return diff hunks enriched with surrounding file context.

        Uses already-parsed hunk coordinates instead of reparsing @@ headers.

        The "# --- diff hunk ---" marker below is parsed by
        `findings_operations._annotate_diff_hunk`, which only applies diff-style line
        annotation after it (the surrounding-context block above it is raw file content,
        not diff-prefixed). Keep both in sync if this format changes.
        """
        hunks = self.get_hunks(path)
        if not hunks:
            return []

        file_lines = file_content.split("\n")
        expanded: list[str] = []

        for hunk in hunks:
            expand_start = max(0, hunk.new_line_start - extra_lines - 1)
            expand_end = min(len(file_lines), hunk.new_line_end + extra_lines)
            surrounding = "\n".join(file_lines[expand_start:expand_end])
            expanded.append(
                f"{hunk.header}\n"
                f"# --- surrounding context (lines {expand_start + 1}-{expand_end}) ---\n"
                f"{surrounding}\n"
                f"# --- diff hunk ---\n"
                + "\n".join(hunk.content.split("\n")[1:])
            )

        logger.debug(
            "build_expanded_hunks: path=%s, count=%s, extra_lines=%s",
            path,
            len(expanded),
            extra_lines,
        )
        return expanded

    def get_hunk_for_line(self, path: str, line: int, allow_fallback: bool = True) -> Optional[ParsedHunk]:
        """
        Return the hunk containing new-file ``line`` for ``path``.

        Falls back to the first hunk only when ``allow_fallback`` is True.
        """
        hunks = self.get_hunks(path)
        if not hunks:
            logger.debug(f"get_hunk_for_line: path={path}, line={line} → no hunks")
            return None
        for hunk in hunks:
            if hunk.contains_new_line(line):
                logger.debug(f"get_hunk_for_line: path={path}, line={line} → exact match ({hunk.new_line_start}-{hunk.new_line_end})")
                return hunk
        if allow_fallback:
            logger.debug(f"get_hunk_for_line: path={path}, line={line} → fallback to first hunk ({hunks[0].new_line_start}-{hunks[0].new_line_end})")
            return hunks[0]
        logger.debug(f"get_hunk_for_line: path={path}, line={line} → no exact match")
        return None

    def get_hunk_for_old_line(self, path: str, line: int) -> Optional[ParsedHunk]:
        """
        Return the hunk containing old-file ``line`` for ``path``.

        Used for outdated comments where only ``originalLine`` is available.
        Falls back to the last hunk.
        """
        hunks = self.get_hunks(path)
        if not hunks:
            logger.debug(f"get_hunk_for_old_line: path={path}, old_line={line} → no hunks")
            return None
        for hunk in hunks:
            if hunk.contains_old_line(line):
                logger.debug(f"get_hunk_for_old_line: path={path}, old_line={line} → exact match ({hunk.old_line_start}-{hunk.old_line_end})")
                return hunk
        logger.debug(f"get_hunk_for_old_line: path={path}, old_line={line} → fallback to last hunk ({hunks[-1].old_line_start}-{hunks[-1].old_line_end})")
        return hunks[-1]

    # ------------------------------------------------------------------
    # GitHub diff attachment (publishable-lines source)
    # ------------------------------------------------------------------

    def attach_github_diff(self, diff: str) -> None:
        """
        Attach GitHub's own PR diff (from ``gh pr diff`` or files-API ``patch`` sections).

        Once attached, ``get_publishable_lines`` validates inline placement against
        GitHub's hunks instead of the (possibly wider-context) local diff. Attaching an
        empty diff is a no-op — the added-lines-only fallback stays in effect.
        """
        if not diff or not diff.strip():
            logger.debug("attach_github_diff: empty diff ignored")
            return
        self._github_parsed = _parse_diff(diff)
        logger.debug(
            "attach_github_diff: %s files, %s hunks",
            len(self._github_parsed.files),
            sum(len(f.hunks) for f in self._github_parsed.files.values()),
        )

    @property
    def has_github_diff(self) -> bool:
        """Return True when GitHub's own diff has been attached."""
        return self._github_parsed is not None

    def get_publishable_lines(self, path: str) -> frozenset:
        """
        Return new-file line numbers GitHub will accept for inline comments on ``path``.

        Source precedence (never fails, only narrows):
        1. GitHub's own diff when attached — added + context lines of ITS hunks.
        2. Added ('+') lines from the context diff — these exist identically in any
           diff of the same change, so GitHub always accepts them.

        Files whose context-diff hunks failed the @@ line-count self-check
        return an empty set: every resolved line for them may be shifted, so they
        degrade to general-body placement. A self-check failure in the GitHub diff —
        or a path missing from it — only drops that source, falling back to the
        added-lines floor.
        """
        context_file = self._parsed.files.get(path)
        if context_file is not None and not context_file.hunks_consistent:
            # Anchors are resolved against the context diff — if its parse desynced,
            # any line we'd publish may be shifted. Force general-body degradation.
            logger.warning(
                "get_publishable_lines: path=%s context diff failed line-count self-check "
                "→ no inline placement",
                path,
            )
            return frozenset()

        if self._github_parsed is not None:
            file_diff = self._github_parsed.files.get(path)
            if file_diff is None:
                # The attached diff may be assembled from files-API `patch` sections,
                # which GitHub omits for large files — a missing entry doesn't mean
                # the file is un-commentable, so drop the source, keep the floor.
                logger.warning(
                    "get_publishable_lines: path=%s missing from GitHub diff "
                    "→ falling back to added lines",
                    path,
                )
            elif not file_diff.hunks_consistent:
                logger.warning(
                    "get_publishable_lines: path=%s GitHub diff failed line-count self-check "
                    "→ falling back to added lines",
                    path,
                )
            else:
                lines = file_diff.valid_review_lines
                logger.debug(
                    "get_publishable_lines: path=%s source=github_diff count=%s", path, len(lines)
                )
                return lines

        lines = context_file.added_lines if context_file else frozenset()
        logger.debug(
            "get_publishable_lines: path=%s source=added_lines_fallback count=%s", path, len(lines)
        )
        return lines

    def has_github_hunks_for(self, path: str) -> bool:
        """True when this path's publishable lines come from GitHub-quality hunks.

        ``get_publishable_lines`` decides its source per path: a path missing from
        the attached GitHub diff (or failing its self-check) silently narrows to the
        added-lines floor even though a GitHub diff is attached manager-wide. Callers
        that need hunk-shaped publishable sets (e.g. anchor snapping) must gate per
        path, not on the manager-wide attachment.
        """
        if self._github_parsed is None:
            return False
        file_diff = self._github_parsed.files.get(path)
        return file_diff is not None and file_diff.hunks_consistent

    def get_all_publishable_lines(self) -> dict[str, frozenset]:
        """Return ``{path: frozenset[line]}`` of publishable lines for every file."""
        paths = set(self._parsed.files)
        if self._github_parsed is not None:
            paths |= set(self._github_parsed.files)
        return {path: self.get_publishable_lines(path) for path in paths}

    # ------------------------------------------------------------------
    # File content (code the diff does not contain)
    # ------------------------------------------------------------------

    def attach_content_provider(self, provider: Callable[[str], Optional[str]]) -> None:
        """
        Attach a source of whole-file content, keyed by repo-relative path.

        Every other method here reads from the parsed diff, so it can only describe lines
        the diff contains. A finding about pre-existing code the PR never touched has no
        such lines — without a provider there is nothing to show for it at all. The
        provider is expected to return content for the PR's head revision (or None), and
        results are cached per path.
        """
        self._content_provider = provider
        self._content_cache = {}
        logger.debug("attach_content_provider: provider attached")

    @property
    def has_content_provider(self) -> bool:
        """Return True when a file-content provider has been attached."""
        return self._content_provider is not None

    def get_file_content(self, path: str) -> Optional[str]:
        """Return whole-file content for ``path`` via the attached provider, or None."""
        if self._content_provider is None:
            return None
        if path in self._content_cache:
            return self._content_cache[path]

        try:
            content = self._content_provider(path)
            # Only cache successful lookups or legitimate None returns
            self._content_cache[path] = content
            logger.debug(
                "get_file_content: path=%s found=%s", path, content is not None
            )
            return content
        except Exception as e:
            # Provider reads from worktree or network — transient failures shouldn't
            # permanently disable excerpts for this path. Log at warning and don't cache.
            logger.warning("get_file_content: provider failed for %s: %s", path, e)
            return None

    def build_file_excerpt(
        self,
        path: str,
        line: int,
        before: int = 6,
        after: int = 4,
    ) -> Optional[str]:
        """
        Return a numbered excerpt of ``path`` centred on ``line``, from file content.

        Plain file text, not diff format: these lines are unchanged by the PR, so
        there is no +/- to show. The target line is marked so it is identifiable at a
        glance. Returns None when no content is available or ``line`` is out of range.
        """
        content = self.get_file_content(path)
        if not content or line < 1:
            return None

        lines = content.split("\n")
        if line > len(lines):
            logger.debug(
                "build_file_excerpt: path=%s line=%s beyond file length %s",
                path,
                line,
                len(lines),
            )
            return None

        start = max(1, line - before)
        end = min(len(lines), line + after)
        width = len(str(end))

        excerpt = []
        for number in range(start, end + 1):
            marker = " ◄" if number == line else ""
            excerpt.append(f"{str(number).rjust(width)} | {lines[number - 1]}{marker}")

        logger.debug(
            "build_file_excerpt: path=%s line=%s window=%s-%s", path, line, start, end
        )
        return "\n".join(excerpt)

    # ------------------------------------------------------------------
    # Valid review lines
    # ------------------------------------------------------------------

    def get_valid_review_lines(self, path: str) -> frozenset:
        """
        Return new-file line numbers valid for inline comments in ``path``.

        Only added ('+') and context (' ') lines are valid targets.
        """
        file_diff = self._parsed.files.get(path)
        valid = file_diff.valid_review_lines if file_diff else frozenset()
        logger.debug(f"get_valid_review_lines: path={path}, count={len(valid)}, lines={sorted(list(valid))[:10]}...")
        return valid

    def get_all_valid_lines(self) -> dict[str, frozenset]:
        """
        Return ``{path: frozenset[line]}`` for every file in the diff.

        Replaces ``extract_valid_diff_lines`` from code_review_operations.
        """
        result = {path: fd.valid_review_lines for path, fd in self._parsed.files.items()}
        logger.debug(f"get_all_valid_lines: {len(result)} files, total_valid_lines={sum(len(v) for v in result.values())}")
        return result

    # ------------------------------------------------------------------
    # Snippet search
    # ------------------------------------------------------------------

    def find_lines_by_snippet(self, path: str, snippet: str) -> list[int]:
        """
        Find ALL new-file line numbers of added/context lines containing
        ``snippet`` in ``path``, in hunk order.

        The snippet is sanitized first (prompt-annotation prefixes like
        ``NN | ``, ``NN [ADDED]`` and leading diff markers are stripped —
        models copy them from the annotated prompt code).
        """
        snippet_stripped = _sanitize_snippet(snippet)
        if not snippet_stripped:
            logger.debug(f"find_lines_by_snippet: path={path}, snippet=<empty> → skipped")
            return []
        logger.debug(f"find_lines_by_snippet: path={path}, snippet='{snippet_stripped[:50]}...'")
        matches: list[int] = []
        for hunk in self.get_hunks(path):
            lines = hunk.content.split("\n")
            current = hunk.new_line_start
            for line in lines[1:]:  # skip @@ header
                # Inside a hunk body "+++" can only be an added line whose content
                # starts with "++" (file headers precede the first @@) — a
                # not-startswith("+++") guard here desyncs the counter on such lines.
                if line.startswith("+"):
                    if snippet_stripped in line[1:].strip():
                        matches.append(current)
                    current += 1
                elif line.startswith(" ") or line in ("", "\r"):
                    # "" — empty context line whose leading space was stripped in
                    # transport; must advance the counter to stay in sync
                    if snippet_stripped in line[1:].strip():
                        matches.append(current)
                    current += 1
        logger.debug(f"find_lines_by_snippet: path={path} → {len(matches)} match(es): {matches[:10]}")
        return matches

    def find_line_by_snippet(self, path: str, snippet: str) -> Optional[int]:
        """
        Find the new-file line number of the first added/context line containing
        ``snippet`` in ``path``.

        Returns None if the snippet is not found. Prefer ``resolve_line_anchor``
        for anchoring decisions — first-occurrence alone is ambiguous when the
        snippet repeats across hunks (D-002/D-005).
        """
        matches = self.find_lines_by_snippet(path, snippet)
        return matches[0] if matches else None

    def resolve_line_anchor(
        self,
        path: str,
        line: Optional[int] = None,
        snippet: Optional[str] = None,
        evidence: Optional[str] = None,
    ) -> Optional[int]:
        """
        Resolve the best inline comment line for a finding.

        Scoring per candidate source (snippet first, then an anchor extracted
        from evidence), designed against the reproduced D-002/D-005 false
        positive (duplicate snippet across hunks relocating a correct comment):

        - unique match → trust it (may legitimately correct a slightly-off AI line)
        - ambiguous match containing the AI line → the AI line
        - ambiguous match, AI line valid elsewhere → the AI line wins over a guess
        - ambiguous match, no usable AI line → prefer publishable lines, then
          nearest to the AI line, then first occurrence
        - no source matched → the AI line if valid, else None
        """
        for candidate in (snippet, _extract_best_anchor_from_text(evidence)):
            matches = self.find_lines_by_snippet(path, candidate or "")
            if not matches:
                continue

            if len(matches) == 1:
                logger.debug(
                    "resolve_line_anchor: path=%s unique snippet match line=%s", path, matches[0]
                )
                return matches[0]

            if line is not None and line in matches:
                logger.debug(
                    "resolve_line_anchor: path=%s ambiguous snippet, AI line %s among matches",
                    path,
                    line,
                )
                return line
            if line is not None and line in self.get_valid_review_lines(path):
                logger.debug(
                    "resolve_line_anchor: path=%s ambiguous snippet %s, valid AI line %s wins",
                    path,
                    matches,
                    line,
                )
                return line

            publishable = self.get_publishable_lines(path)
            best = min(
                matches,
                key=lambda m: (
                    m not in publishable,
                    abs(m - line) if line is not None else 0,
                    m,
                ),
            )
            logger.debug(
                "resolve_line_anchor: path=%s ambiguous snippet %s, no usable AI line → %s",
                path,
                matches,
                best,
            )
            return best

        if line is not None and line in self.get_valid_review_lines(path):
            logger.debug("resolve_line_anchor: path=%s using validated line=%s", path, line)
            return line

        logger.debug("resolve_line_anchor: path=%s could not resolve line", path)
        return None

    # ------------------------------------------------------------------
    # Context extraction for UI
    # ------------------------------------------------------------------

    def build_focused_diff(
        self,
        path: str,
        line: int,
        is_outdated: bool = False,
        before: int = 7,
        after: int = 3,
    ) -> str:
        """
        Return a trimmed diff fragment centred on ``line``.

        For outdated comments falls back to the last ``before + after`` lines.
        Replaces ``extract_diff_context`` + ``_rebuild_diff`` from comment_utils.
        """
        if is_outdated:
            hunk = self.get_hunk_for_old_line(path, line)
        else:
            hunk = self.get_hunk_for_line(path, line)

        if not hunk:
            logger.debug(f"build_focused_diff: path={path}, line={line}, is_outdated={is_outdated} → no hunk found")
            return ""

        result = _build_focused_diff_from_hunk(
            hunk.content, line, is_outdated, before=before, after=after
        )
        logger.debug(f"build_focused_diff: path={path}, line={line}, is_outdated={is_outdated}, result_size={len(result)} bytes")
        return result

    def extract_original_lines_for_suggestion(
        self,
        path: str,
        line: int,
        count: int = 1,
    ) -> Optional[str]:
        """
        Extract ``count`` consecutive lines starting at new-file ``line``
        from the diff for ``path``.

        Replaces ``_extract_lines_from_diff`` from comment_utils.
        """
        hunk = self.get_hunk_for_line(path, line)
        if not hunk:
            logger.debug(f"extract_original_lines_for_suggestion: path={path}, line={line}, count={count} → no hunk")
            return None
        result = _extract_lines_from_hunk(hunk.content, line, count)
        logger.debug(f"extract_original_lines_for_suggestion: path={path}, line={line}, count={count} → {len(result.split(chr(10))) if result else 0} lines extracted")
        return result

    def build_comment_context(self, comment: UIComment) -> ResolvedCommentContext:
        """
        Build a ``ResolvedCommentContext`` for a UIComment.

        Resolves the focused diff and full hunk. ``is_outdated`` is True only when
        the comment has an ``original_line`` (from old file) but no ``position``
        (GitHub's marker for outdated comments).
        Falls back to the diffHunk stored on the comment itself when the file
        is not present in the diff.
        """
        is_outdated = comment.position is None and comment.original_line is not None
        effective_line = comment.original_line if is_outdated else comment.line

        logger.debug(
            f"build_comment_context: comment_id={comment.id}, path={comment.path}, "
            f"line={comment.line}, original_line={comment.original_line}, "
            f"position={comment.position}, is_outdated={is_outdated}"
        )

        focused = ""
        full_hunk: Optional[str] = None

        if comment.path and effective_line:
            focused = self.build_focused_diff(
                comment.path, effective_line, is_outdated=is_outdated
            )
            hunk = (
                self.get_hunk_for_old_line(comment.path, effective_line)
                if is_outdated
                else self.get_hunk_for_line(comment.path, effective_line)
            )
            full_hunk = hunk.content if hunk else None
            logger.debug(f"build_comment_context: resolved from diff, focused_diff_len={len(focused)}, full_hunk_len={len(full_hunk) if full_hunk else 0}")

        if not focused and comment.diff_hunk:
            # Fallback: use the diffHunk stored on the comment itself
            focused = _build_focused_diff_from_hunk(
                comment.diff_hunk, effective_line, is_outdated
            )
            full_hunk = full_hunk or comment.diff_hunk
            logger.debug(f"build_comment_context: fallback to comment.diff_hunk, focused_diff_len={len(focused)}")

        return ResolvedCommentContext(
            comment_id=comment.id,
            is_outdated=is_outdated,
            path=comment.path,
            line=effective_line,
            position=comment.position,
            focused_diff=focused,
            full_hunk=full_hunk,
            body=comment.body,
            author_name=comment.author_name,
            formatted_date=comment.formatted_date,
        )


# ------------------------------------------------------------------
# Internal parsing helpers
# ------------------------------------------------------------------

def _parse_file_diff_section(path: str, file_section: str) -> Optional[ParsedFileDiff]:
    """
    Parse a per-file diff section into a ``ParsedFileDiff``.

    Handles sections that may or may not include a ``diff --git`` header —
    only ``@@`` hunk lines are required.
    """
    hunks: list[ParsedHunk] = []
    current_hunk_lines: list[str] = []

    for line in file_section.split("\n"):
        if line.startswith("@@"):
            if current_hunk_lines:
                hunk = _parse_hunk(path, "\n".join(current_hunk_lines))
                if hunk:
                    hunks.append(hunk)
            current_hunk_lines = [line]
        elif current_hunk_lines:
            current_hunk_lines.append(line)

    if current_hunk_lines:
        hunk = _parse_hunk(path, "\n".join(current_hunk_lines))
        if hunk:
            hunks.append(hunk)

    return ParsedFileDiff(path=path, hunks=hunks) if hunks else None


def _parse_diff(raw: str) -> ParsedDiff:
    """Parse a full unified diff into structured ``ParsedDiff``."""
    logger.debug(f"_parse_diff: parsing {len(raw)} bytes")
    files: dict[str, ParsedFileDiff] = {}
    current_path: Optional[str] = None
    current_hunk_lines: list[str] = []

    def _flush_hunk() -> None:
        if current_path and current_hunk_lines:
            hunk = _parse_hunk(current_path, "\n".join(current_hunk_lines))
            if hunk:
                files[current_path].hunks.append(hunk)

    for raw_line in raw.split("\n"):
        file_match = _FILE_HEADER_RE.match(raw_line)
        if file_match:
            _flush_hunk()
            current_hunk_lines = []
            current_path = file_match.group("path") or file_match.group("quoted_path")
            if current_path not in files:
                logger.debug(f"_parse_diff: found file: {current_path}")
                files[current_path] = ParsedFileDiff(path=current_path, hunks=[])
            continue

        if raw_line.startswith("@@") and current_path:
            _flush_hunk()
            current_hunk_lines = [raw_line]
            continue

        if current_hunk_lines:
            current_hunk_lines.append(raw_line)

    _flush_hunk()
    logger.debug(f"_parse_diff: completed → {len(files)} files, {sum(len(f.hunks) for f in files.values())} hunks")
    return ParsedDiff(files=files, raw=raw)


def _parse_hunk(path: str, content: str) -> Optional[ParsedHunk]:
    """
    Parse a single hunk string into a ``ParsedHunk``. Returns None on malformed header.

    Empty lines (``""``/``"\\r"``) inside the body are counted as context lines: git
    always emits the leading space, so a bare empty line means it was stripped in
    transport — not counting it would silently shift every subsequent line.
    After parsing, the counted new-file lines are checked against the @@ header's
    declared count; a mismatch marks the hunk ``header_consistent=False`` so the
    file degrades to general-body placement instead of publishing shifted lines.
    """
    lines = content.split("\n")
    if not lines:
        return None

    header_match = _HUNK_HEADER_RE.match(lines[0])
    if not header_match:
        return None

    # Trailing empty lines are join/transport artifacts, not hunk content — a real
    # empty context line inside the hunk is " " (or "" if space-stripped, handled below).
    while len(lines) > 1 and lines[-1] in ("", "\r"):
        lines.pop()
    content = "\n".join(lines)

    old_start = int(header_match.group(1))
    old_count = int(header_match.group(2)) if header_match.group(2) else 1
    new_start = int(header_match.group(3))
    new_count = int(header_match.group(4)) if header_match.group(4) else 1

    valid_lines: set[int] = set()
    added_lines: set[int] = set()
    current = new_start

    for line in lines[1:]:
        # Inside a hunk body "+++" can only be an added line whose content starts
        # with "++" (file headers precede the first @@) — guarding against it here
        # would desync the counter on files that embed diff text.
        if line.startswith("+"):
            valid_lines.add(current)
            added_lines.add(current)
            current += 1
        elif line.startswith(" ") or line in ("", "\r"):
            valid_lines.add(current)
            current += 1
        # '-' lines: do not advance new-file counter
        # '\ No newline at end of file' markers: not file lines, do not count

    counted_new = current - new_start
    header_consistent = counted_new == new_count
    if not header_consistent:
        logger.warning(
            "hunk_header_desync: path=%s header=%r declares %s new-file lines, parsed %s "
            "— file will be excluded from inline placement",
            path,
            lines[0],
            new_count,
            counted_new,
        )

    return ParsedHunk(
        header=lines[0],
        content=content,
        path=path,
        old_line_start=old_start,
        old_line_count=old_count,
        new_line_start=new_start,
        new_line_count=new_count,
        valid_review_lines=frozenset(valid_lines),
        added_lines=frozenset(added_lines),
        header_consistent=header_consistent,
    )


def _build_focused_diff_from_hunk(
    hunk_content: str,
    target_line: Optional[int],
    is_outdated: bool = False,
    before: int = 7,
    after: int = 3,
) -> str:
    """Trim a hunk to a window of ``before`` + target + ``after`` lines."""
    if not hunk_content:
        return ""

    lines = hunk_content.split("\n")
    header_match = _HUNK_HEADER_RE.match(lines[0])
    if not header_match:
        return hunk_content

    # Trailing empty lines are join artifacts, not hunk content
    while len(lines) > 1 and lines[-1] in ("", "\r"):
        lines.pop()

    old_start = int(header_match.group(1))
    new_start = int(header_match.group(3))
    header_suffix = header_match.group(5)

    old_line = old_start
    new_line = new_start

    parsed: list[tuple] = []  # (old_num, new_num, raw_line, idx)
    for idx, raw in enumerate(lines[1:], start=1):
        # No "+++"/"---" guards: file headers precede the first @@, so inside a
        # hunk body those prefixes are real added/deleted lines (e.g. embedded
        # diff text) and skipping them would desync both counters.
        if raw.startswith("+"):
            parsed.append((None, new_line, raw, idx))
            new_line += 1
        elif raw.startswith("-"):
            parsed.append((old_line, None, raw, idx))
            old_line += 1
        elif raw.startswith(" ") or raw in ("", "\r"):
            # "" — space-stripped empty context line; must advance both counters
            parsed.append((old_line, new_line, raw, idx))
            old_line += 1
            new_line += 1
        else:
            parsed.append((None, None, raw, idx))

    target_idx: Optional[int] = None
    if not is_outdated and target_line:
        for _, new_num, _, idx in parsed:
            if new_num == target_line:
                target_idx = idx
                break

    if target_idx is not None:
        min_idx = max(0, target_idx - before - 1)
        max_idx = min(len(parsed) - 1, target_idx + after - 1)
        extracted = parsed[min_idx : max_idx + 1]
    elif len(parsed) > before + after:
        extracted = parsed[-(before + after):]
    else:
        return hunk_content

    # In the outdated path target_line is an old-file number, but _rebuild_diff's
    # ◄ marker compares against new-file numbers — a coincidental match would point
    # the reader at the wrong line, so no marker is better than a lying one.
    return _rebuild_diff(
        extracted,
        old_start,
        new_start,
        header_suffix,
        None if is_outdated else target_line,
    )


def _rebuild_diff(
    extracted: list[tuple],
    old_start: int,
    new_start: int,
    header_suffix: str,
    target_line: Optional[int] = None,
) -> str:
    """Reconstruct a valid diff header + lines from extracted parsed lines."""
    extracted_new_start: Optional[int] = None
    extracted_old_start: Optional[int] = None

    for old_num, new_num, _, _ in extracted:
        if extracted_new_start is None and new_num is not None:
            extracted_new_start = new_num
        if extracted_old_start is None and old_num is not None:
            extracted_old_start = old_num
        if extracted_new_start is not None and extracted_old_start is not None:
            break

    if extracted_new_start is None:
        extracted_new_start = new_start
    if extracted_old_start is None:
        extracted_old_start = old_start

    old_count = sum(
        1 for _, _, raw, _ in extracted
        if raw.startswith(("-", " ")) or raw in ("", "\r")
    )
    new_count = sum(
        1 for _, _, raw, _ in extracted
        if raw.startswith(("+", " ")) or raw in ("", "\r")
    )

    header = (
        f"@@ -{extracted_old_start},{old_count}"
        f" +{extracted_new_start},{new_count} @@{header_suffix}"
    )

    result_lines = []
    for _, new_num, raw, _ in extracted:
        if target_line and new_num == target_line:
            result_lines.append(raw + "  ◄")
        else:
            result_lines.append(raw)

    return header + "\n" + "\n".join(result_lines)


def _extract_lines_from_hunk(
    hunk_content: str,
    target_line: int,
    count: int = 1,
) -> Optional[str]:
    """
    Extract ``count`` consecutive new-file lines starting at ``target_line``.

    Replaces ``_extract_lines_from_diff`` from comment_utils.
    """
    lines = hunk_content.split("\n")
    header_match = _HUNK_HEADER_RE.match(lines[0])
    if not header_match:
        return None

    current = int(header_match.group(3))
    extracted: list[str] = []

    for line in lines[1:]:
        # "+++" here is an added line starting with "++", not a file header —
        # see _parse_hunk.
        if line.startswith("+"):
            if current >= target_line and len(extracted) < count:
                extracted.append(line[1:])
            current += 1
        elif line.startswith(" ") or line in ("", "\r"):
            # "" — space-stripped empty context line; counts toward the new file
            if current >= target_line and len(extracted) < count:
                extracted.append(line[1:])
            current += 1
        if len(extracted) >= count:
            break

    return "\n".join(extracted) if extracted else None


def extract_lines_from_hunk(hunk_content: str, target_line: int, count: int = 1) -> Optional[str]:
    """
    Extract ``count`` consecutive new-file lines starting at ``target_line`` from a hunk string.

    Convenience wrapper for callers that only have a single hunk string (e.g. comment_utils),
    not a full diff. Delegates to the internal helper.
    """
    return _extract_lines_from_hunk(hunk_content, target_line, count)


def build_focused_diff_from_hunk(
    hunk_content: str,
    target_line: Optional[int],
    is_outdated: bool = False,
    before: int = 7,
    after: int = 3,
) -> str:
    """
    Trim a hunk string to a focused window around ``target_line``.

    Convenience wrapper for callers that only have a single hunk string (e.g. comment_utils
    and comment_view), not a full diff. Delegates to the internal helper.
    """
    return _build_focused_diff_from_hunk(hunk_content, target_line, is_outdated, before, after)


_SNIPPET_ANNOTATION_RE = re.compile(
    r"^\s*(?:\d+\s*)?(?:\|\s?|\[(?:ADDED|CONTEXT)\]\s?)"
)
"""Prompt-annotation prefixes models copy into `snippet`: the findings prompt renders
code as ``NN | code`` (full_content) or ``NN [ADDED] code`` / ``NN [CONTEXT] code``
(annotated hunks) — see findings_operations._add_line_numbers/_annotate_diff_hunk."""


def _sanitize_snippet(snippet: Optional[str]) -> str:
    """Strip prompt-annotation prefixes, diff markers, and CR chars from a snippet."""
    if not snippet:
        return ""
    text = snippet.replace("\r", "").strip()
    cleaned = _SNIPPET_ANNOTATION_RE.sub("", text)
    if cleaned != text:
        text = cleaned.strip()
    elif text.startswith(("+", "-")) and not text.startswith(("++", "--")):
        # A single leading diff marker (e.g. "+return None") — strip it; real code
        # lines starting with +/- followed by code are rare, and the substring
        # match still works either way for most of them.
        text = text[1:].strip()
    return text


def _extract_best_anchor_from_text(text: Optional[str]) -> Optional[str]:
    """Extract a short single-line anchor from evidence text."""
    if not text:
        return None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```") or line.startswith(_COMMENT_PREFIXES):
            continue
        if line.startswith(("+", "-", "*")):
            line = line[1:].strip()
        if len(line) < 6:
            continue
        return line[:160]
    return None


__all__ = ["DiffContextManager", "extract_lines_from_hunk", "build_focused_diff_from_hunk"]


def get_or_create_diff_manager(
    diff: str,
    cache: Optional[dict] = None,
    cache_key: str = "review_diff_manager",
) -> DiffContextManager:
    """
    Return a cached diff manager when available, otherwise parse once and store it.

    The cached manager is only reused when it was built from this exact diff. Without
    that check, re-fetching the diff (after a push, or on a retry) would silently keep
    serving line numbers parsed from the previous one, and every anchor resolved against
    it would be off. The hash is kept next to the manager rather than folded into
    ``cache_key`` so callers keep passing the same key they always did.
    """
    diff_hash = hashlib.sha256(diff.encode("utf-8", errors="replace")).hexdigest()
    hash_key = f"{cache_key}__diff_hash"

    if cache is not None:
        existing = cache.get(cache_key)
        if existing is not None:
            if cache.get(hash_key) == diff_hash:
                logger.debug("get_or_create_diff_manager: reusing cached manager")
                return existing
            logger.debug(
                "get_or_create_diff_manager: cached manager was built from a different "
                "diff — reparsing"
            )

    manager = DiffContextManager.from_diff(diff)
    if cache is not None:
        cache[cache_key] = manager
        cache[hash_key] = diff_hash
    return manager
