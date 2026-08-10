"""
Comment Body Utilities

Pure parsing and rendering of comment body text (markdown, code blocks, suggestions).

This module is responsible ONLY for:
  - Parsing comment body markdown (TextElement, CodeBlockElement, SuggestionElement)
  - Rendering parsed elements as Textual widgets
  - Extracting code lines for suggestion display

This module is NOT responsible for:
  - Diff parsing or interpretation (use DiffContextManager)
  - Determining outdated status (use ResolvedCommentContext)
  - Resolving line numbers or positions (use DiffContextManager)

Keep this separation strict to avoid logic creep back into the UI layer.
"""

import re
from dataclasses import dataclass
from typing import List, Union, Optional

from ..managers.diff_context_manager import build_focused_diff_from_hunk, extract_lines_from_hunk


@dataclass
class TextElement:
    """Plain text content from comment body."""
    content: str


@dataclass
class SuggestionElement:
    """Code suggestion block from comment body."""
    code: str
    original_lines: Optional[str] = None  # Can be multiple lines (multiline suggestions)
    start_line: Optional[int] = None  # Starting line number for the suggestion


@dataclass
class CodeBlockElement:
    """Code block from comment body."""
    code: str
    language: str


CommentElement = Union[TextElement, SuggestionElement, CodeBlockElement]

_HUNK_HEADER_RE = re.compile(r'@@ -\d+,?\d* \+(\d+),?\d* @@')


# The tag name must follow `<` immediately and be closed like a real tag: prose such as
# "check that x < a and y > b" must NOT be mistaken for markup, or the tag-stripping
# below would delete everything between the two comparison operators.
_HTML_BLOCK_HINT = re.compile(
    r"</?(table|tbody|thead|tr|td|th|div|p|span|a|img|picture|source|details|summary|br|ul|ol|li|code)"
    r"(\s[^<>]*)?/?>",
    re.I,
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Only well-formed tags: `<name>`, `</name>`, `<name attr="…">`, `<name/>`.
_HTML_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9-]*(\s[^<>]*)?/?>")
_BLANK_RUN = re.compile(r"\n{3,}")

_LINE_BREAK_TAGS = re.compile(r"<\s*/?\s*(br|/tr|/p|/div|/li|/h[1-6])\b[^>]*>", re.I)
_CELL_END = re.compile(r"<\s*/\s*(td|th)\s*>", re.I)
_CODE_SPAN = re.compile(r"<\s*code\s*[^>]*>(.*?)<\s*/\s*code\s*>", re.DOTALL | re.I)

_EMOJI_SHORTCODES = {
    ":warning:": "⚠️",
    ":x:": "❌",
    ":no_entry_sign:": "🚫",
    ":heavy_check_mark:": "✅",
    ":white_check_mark:": "✅",
    ":bangbang:": "‼️",
    ":information_source:": "ℹ️",
    ":bulb:": "💡",
    ":memo:": "📝",
}


def html_body_to_text(body: str) -> str:
    """Flatten an HTML comment body into readable text.

    Linter and CI bots (github-actions, Danger, Wiz…) post their findings as HTML
    tables. Textual's Markdown widget has no `html_block`/`html_inline` handling, so
    such a body renders as NOTHING and the comment looks empty — the reader can see
    the thread but not what it says. Converting to text keeps the message readable;
    the exact HTML layout is irrelevant in a terminal.
    """
    text = _HTML_COMMENT.sub("", body)
    text = _CODE_SPAN.sub(lambda m: f"`{m.group(1).strip()}`", text)
    text = _LINE_BREAK_TAGS.sub("\n", text)
    # Cells on one source line would otherwise be glued together ("⚠️Unit tests…").
    text = _CELL_END.sub(" ", text)
    text = _HTML_TAG.sub("", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )
    for shortcode, emoji in _EMOJI_SHORTCODES.items():
        text = text.replace(shortcode, emoji)
    lines = [line.strip() for line in text.splitlines()]
    # A severity marker alone on its line (bots put it in its own table cell) reads
    # better attached to the message it qualifies.
    merged: List[str] = []
    for line in lines:
        if merged and merged[-1] in _EMOJI_SHORTCODES.values() and line:
            merged[-1] = f"{merged[-1]} {line}"
        else:
            merged.append(line)
    return _BLANK_RUN.sub("\n\n", "\n".join(merged)).strip()


def _flatten_html_if_needed(text: str) -> str:
    """Flatten HTML in a PROSE segment only.

    Called per text segment, never on the whole body: fenced code blocks must keep
    their content verbatim (`List<String>` in a Kotlin snippet is not a tag, and a
    mangled ```suggestion block would be applied to the code as-is).
    """
    if _HTML_BLOCK_HINT.search(text) or text.lstrip().startswith("<!--"):
        return html_body_to_text(text)
    return text


def parse_comment_body(
    body: str,
    diff_hunk: Optional[str] = None,
    line: Optional[int] = None
) -> List[CommentElement]:
    """
    Parse comment body into structured elements.

    Args:
        body: Comment body text (may contain markdown, code blocks, suggestions)
        diff_hunk: Diff context (used to extract original lines for suggestions)
        line: Line number being commented on

    Returns:
        List of parsed elements (TextElement, SuggestionElement, CodeBlockElement)
    """
    if not body or not body.strip():
        return []

    body = body.replace("\r\n", "\n")
    elements: List[CommentElement] = []

    code_block_pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    matches = list(code_block_pattern.finditer(body))

    if not matches:
        flattened = _flatten_html_if_needed(body).strip()
        return [TextElement(content=flattened)] if flattened else []

    last_end = 0
    for match in matches:
        text_before = _flatten_html_if_needed(body[last_end : match.start()]).strip()
        if text_before:
            elements.append(TextElement(content=text_before))

        language = match.group(1) or "text"
        code = match.group(2).strip()

        if language == "suggestion":
            original_lines = None
            target_line = line

            if not target_line and diff_hunk:
                header_match = _HUNK_HEADER_RE.match(diff_hunk.split('\n')[0])
                if header_match:
                    target_line = int(header_match.group(1))

            if diff_hunk and target_line:
                num_lines = len(code.split('\n'))
                original_lines = extract_lines_from_hunk(diff_hunk, target_line, num_lines)

            elements.append(SuggestionElement(
                code=code,
                original_lines=original_lines,
                start_line=target_line
            ))
        else:
            elements.append(CodeBlockElement(code=code, language=language))

        last_end = match.end()

    text_after = _flatten_html_if_needed(body[last_end:]).strip()
    if text_after:
        elements.append(TextElement(content=text_after))

    return elements


def render_comment_elements(body: str, diff_hunk: Optional[str] = None, line: Optional[int] = None):
    """
    Parse and render comment body into Textual widgets.

    Args:
        body: Comment body text
        diff_hunk: Diff context (for suggestions)
        line: Line number (for suggestions)

    Returns:
        List of Textual widgets ready to be yielded
    """
    from textual.widgets import Markdown
    from .code_block import CodeBlock

    if not body or not body.strip():
        return []

    elements = parse_comment_body(body=body, diff_hunk=diff_hunk, line=line)

    widgets = []
    for element in elements:
        if isinstance(element, TextElement):
            markdown_widget = Markdown(element.content)
            markdown_widget.styles.width = "100%"
            markdown_widget.styles.height = "auto"
            markdown_widget.styles.padding = (1, 1, 0, 1)
            widgets.append(markdown_widget)

        elif isinstance(element, SuggestionElement):
            code_widget = CodeBlock(
                code=element.code,
                language="suggestion",
                original_lines=element.original_lines,
                start_line=element.start_line or 1,
                theme="native",
                line_numbers=True,
            )
            widgets.append(code_widget)

        elif isinstance(element, CodeBlockElement):
            code_widget = CodeBlock(
                code=element.code,
                language=element.language,
                theme="native",
                line_numbers=True,
            )
            widgets.append(code_widget)

    return widgets


def extract_diff_context(
    diff_hunk: str,
    target_line: Optional[int],
    is_outdated: bool = False
) -> str:
    """
    Extract relevant diff lines around the comment.

    Delegates to DiffContextManager's internal helper. Kept here for
    backwards compatibility with comment_view and other callers.

    Args:
        diff_hunk: Diff hunk from GitHub API
        target_line: Line number being commented on
        is_outdated: Whether this is an outdated comment

    Returns:
        Trimmed diff with context (7 before + target + 3 after)
    """
    return build_focused_diff_from_hunk(diff_hunk, target_line, is_outdated)


__all__ = [
    "TextElement",
    "SuggestionElement",
    "CodeBlockElement",
    "CommentElement",
    "parse_comment_body",
    "render_comment_elements",
    "extract_diff_context",
]
