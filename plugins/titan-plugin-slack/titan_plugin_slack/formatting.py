"""Slack text formatting toolkit.

Slack messages sent through `chat.postMessage` render `mrkdwn`, not standard
Markdown: bold uses a single asterisk (`*bold*`), there is no header syntax,
and there is no native table support. `SlackFormatter` lets any step render
AI-generated or hand-written content correctly in Slack, while a second,
standard-Markdown copy of the same source can still be shown elsewhere (e.g.
the Titan TUI).

`to_mrkdwn` is the only public entry point. A caller with structured tabular
data (headers/rows) should build a plain Markdown pipe table string and pass
it through `to_mrkdwn` like any other content - there is no separate table
API to learn, and it converts everything (prose and tables) consistently.
"""

import re
from typing import List, Optional


class SlackFormatter:
    """Namespace of stateless helpers that format text for Slack's mrkdwn renderer."""

    _CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
    _TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
    _TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
    _HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
    _BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
    _HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$")
    _BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
    _STRIKETHROUGH_RE = re.compile(r"~~(.+?)~~")
    _ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)")
    _LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    _BOLD_PLACEHOLDER = "\x00BOLD{}\x00"

    @staticmethod
    def to_mrkdwn(text: str) -> str:
        """
        Convert a standard Markdown document into Slack-flavored mrkdwn.

        Handles headers, bold/italic/strikethrough, links, bullet lists, and
        pipe tables (rendered as a fixed-width grid inside a code block, since
        Slack has no native table support). Fenced code blocks are left
        untouched since Slack already renders them as-is.

        Args:
            text: Standard Markdown source text.

        Returns:
            Text formatted for Slack's mrkdwn renderer.
        """
        segments = SlackFormatter._split_on_code_fences(text)
        converted = [
            segment if is_code else SlackFormatter._convert_prose_block(segment)
            for segment, is_code in segments
        ]
        return "".join(converted)

    @staticmethod
    def _render_table(rows: List[List[str]], headers: Optional[List[str]] = None) -> str:
        """
        Render tabular data as a fixed-width Slack table inside a code block.

        Slack has no native table support, so this is the only way to get an
        actual comparable grid (e.g. checking one column across many rows) in
        a plain-text message. Used internally by `to_mrkdwn` when it detects
        a Markdown pipe table.

        Args:
            rows: Table body rows, each a list of cell values.
            headers: Optional header row.

        Returns:
            A fenced code block containing the aligned table, or an empty
            string if there is no data to render.
        """
        if not rows and not headers:
            return ""

        column_count = len(headers) if headers else max(len(row) for row in rows)
        widths = [len(headers[col]) if headers else 0 for col in range(column_count)]
        for row in rows:
            for col in range(column_count):
                cell = row[col] if col < len(row) else ""
                widths[col] = max(widths[col], len(cell))

        def render_row(cells: List[str]) -> str:
            padded = [
                (cells[col] if col < len(cells) else "").ljust(widths[col])
                for col in range(column_count)
            ]
            return " | ".join(padded).rstrip()

        lines = []
        if headers:
            lines.append(render_row(headers))
            lines.append("-+-".join("-" * width for width in widths))
        lines.extend(render_row(row) for row in rows)

        return "```\n" + "\n".join(lines) + "\n```"

    @staticmethod
    def _split_on_code_fences(text: str) -> List[tuple]:
        """Split text into (segment, is_code_fence) pairs, preserving fences verbatim."""
        segments: List[tuple] = []
        last_end = 0
        for match in SlackFormatter._CODE_FENCE_RE.finditer(text):
            if match.start() > last_end:
                segments.append((text[last_end:match.start()], False))
            segments.append((match.group(0), True))
            last_end = match.end()
        if last_end < len(text):
            segments.append((text[last_end:], False))
        return segments

    @staticmethod
    def _convert_prose_block(text: str) -> str:
        """Convert a non-code-fence block: tables as blocks, other lines individually."""
        lines = text.split("\n")
        output_lines: List[str] = []
        i = 0
        while i < len(lines):
            table_end = SlackFormatter._find_table_block_end(lines, i)
            if table_end is not None:
                header, *rows = [
                    SlackFormatter._split_table_row(line)
                    for line in (lines[i], *lines[i + 2:table_end])
                ]
                output_lines.append(SlackFormatter._render_table(rows, headers=header))
                i = table_end
                continue

            line = lines[i]
            if SlackFormatter._HR_RE.match(line):
                output_lines.append("")
            else:
                output_lines.append(SlackFormatter._convert_line(line))
            i += 1

        return "\n".join(output_lines)

    @staticmethod
    def _find_table_block_end(lines: List[str], start: int) -> Optional[int]:
        """Return the exclusive end index of a Markdown table starting at `start`, or None."""
        if start + 1 >= len(lines):
            return None
        if not SlackFormatter._TABLE_ROW_RE.match(lines[start]):
            return None
        if not SlackFormatter._TABLE_SEPARATOR_RE.match(lines[start + 1]):
            return None

        end = start + 2
        while end < len(lines) and SlackFormatter._TABLE_ROW_RE.match(lines[end]):
            end += 1
        return end

    @staticmethod
    def _split_table_row(line: str) -> List[str]:
        """Split a Markdown table row into trimmed cell values."""
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        return [cell.strip() for cell in stripped.split("|")]

    @staticmethod
    def _convert_line(line: str) -> str:
        """Convert a single non-table, non-code line to Slack mrkdwn."""
        header_match = SlackFormatter._HEADER_RE.match(line)
        if header_match:
            return f"*{SlackFormatter._convert_inline(header_match.group(2))}*"

        bullet_match = SlackFormatter._BULLET_RE.match(line)
        if bullet_match:
            indent, rest = bullet_match.groups()
            return f"{indent}• {SlackFormatter._convert_inline(rest)}"

        return SlackFormatter._convert_inline(line)

    @staticmethod
    def _convert_inline(text: str) -> str:
        """Convert inline emphasis and links to Slack mrkdwn within a single line."""
        placeholders: List[str] = []

        def stash_bold(match: "re.Match") -> str:
            content = match.group(1) or match.group(2)
            placeholders.append(content)
            return SlackFormatter._BOLD_PLACEHOLDER.format(len(placeholders) - 1)

        text = SlackFormatter._BOLD_RE.sub(stash_bold, text)
        text = SlackFormatter._STRIKETHROUGH_RE.sub(r"~\1~", text)
        text = SlackFormatter._ITALIC_RE.sub(r"_\1_", text)
        text = SlackFormatter._LINK_RE.sub(r"<\2|\1>", text)

        for index, content in enumerate(placeholders):
            text = text.replace(SlackFormatter._BOLD_PLACEHOLDER.format(index), f"*{content}*")

        return text


__all__ = ["SlackFormatter"]
