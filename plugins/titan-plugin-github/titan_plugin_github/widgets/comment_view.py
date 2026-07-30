"""
CommentView Widget

Unified widget for displaying a single comment with code context.

Handles three comment types seamlessly:
  - Inline review comments (has path + line + diff_hunk)
  - General PR comments (no code context → shows a "General PR comment" badge)
  - AI review suggestions (has severity badge, file path, diff context)

Does NOT include action buttons — that is the caller's responsibility.
"""

from typing import Any, List, Optional
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget

from titan_cli.ui.tui.widgets import BoldText, DimText, ItalicText, Text, DimItalicText

from ..managers.diff_context_manager import DiffContextManager
from ..models.diff_models import ResolvedCommentContext
from ..models.review_enums import FindingSeverity, ReviewActionType, ThreadSeverity
from .code_block import CodeBlock
from .comment_utils import render_comment_elements


class CommentView(Widget):
    """
    Displays a single comment with its code context.

    Responsible for showing: author/date metadata, file location context,
    diff hunk, and the comment body (markdown, code blocks, suggestions).

    Action buttons are NOT part of this widget — mount them separately.
    """

    DEFAULT_CSS = """
    CommentView {
        width: 100%;
        height: auto;
    }

    CommentView Horizontal {
        width: 100%;
        height: auto;
    }

    CommentView .outdated-badge {
        border: round $warning;
        padding: 0 2;
        width: auto;
        height: auto;
        margin-bottom: 1;
    }

    CommentView .general-comment-badge {
        padding: 0 2;
        width: auto;
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }

    CommentView .severity-badge {
        width: auto;
        height: auto;
        margin-bottom: 1;
    }

    CommentView .severity-badge.blocking {
        border: round $error;
        padding: 0 2;
    }

    CommentView .severity-badge.important {
        border: round $warning;
        padding: 0 2;
    }

    CommentView .severity-badge.nit {
        border: round $accent;
        padding: 0 2;
    }
    """

    def __init__(
        self,
        body: str,
        author_name: str = "",
        formatted_date: str = "",
        file_path: Optional[str] = None,
        line: Optional[int] = None,
        diff_hunk: Optional[str] = None,
        focused_diff: Optional[str] = None,
        severity: Optional[FindingSeverity | ThreadSeverity] = None,
        is_outdated: bool = False,
        line_label: Optional[str] = None,
        file_excerpt: Optional[str] = None,
        file_excerpt_line: Optional[int] = None,
        **kwargs,
    ):
        """
        Initialize the comment view.

        Args:
            body: Comment text body.
            author_name: Display name of the comment author.
            formatted_date: Pre-formatted date string (e.g. "27/03/2026 14:30").
            file_path: Path to the file this comment references (None for general comments).
            line: Line number in the file (None for general comments).
            diff_hunk: Full diff context snippet (deprecated, use focused_diff instead).
            focused_diff: Pre-trimmed diff for display (7 before + target + 3 after).
            severity: Severity level for AI suggestions or thread follow-ups.
            is_outdated: Whether the comment references outdated code.
            line_label: Pre-built location label, overriding the default "Line N".
            file_excerpt: Numbered plain-file excerpt, for findings about code this PR
                          did not change (no diff hunk exists for them).
            file_excerpt_line: Line the excerpt is centred on, shown in its caption.
        """
        super().__init__(**kwargs)
        self.body = body
        self.author_name = author_name
        self.formatted_date = formatted_date
        self.file_path = file_path
        self.line = line
        self.diff_hunk = diff_hunk
        self.focused_diff = focused_diff
        self.severity = severity
        self.is_outdated = is_outdated
        self.line_label = line_label
        self.file_excerpt = file_excerpt
        self.file_excerpt_line = file_excerpt_line

    @classmethod
    def from_resolved_context(cls, ctx: ResolvedCommentContext) -> "CommentView":
        """
        Build a CommentView from a pre-resolved diff context.

        Use this when you have already built a ResolvedCommentContext (e.g. from
        DiffContextManager.build_comment_context). The diff is already trimmed
        and ready for display, and outdated status is correctly inferred.

        Args:
            ctx: ResolvedCommentContext with pre-computed fields.

        Returns:
            CommentView with resolved diff and correct line semantics.
        """
        return cls(
            body=ctx.body,
            author_name=ctx.author_name,
            formatted_date=ctx.formatted_date,
            file_path=ctx.path,
            line=ctx.line,
            diff_hunk=ctx.full_hunk,
            focused_diff=ctx.focused_diff,
            is_outdated=ctx.is_outdated,
        )

    @classmethod
    def from_ui_comment(
        cls,
        comment: Any,
        is_outdated: bool = False,
        diff: Optional[str] = None,
    ) -> "CommentView":
        """
        Build a CommentView from a UIComment model.

        If ``diff`` is provided, uses DiffContextManager to build the focused diff.
        Otherwise falls back to the raw diff_hunk on the comment.

        Args:
            comment: UIComment instance from the view layer.
            is_outdated: Override for is_outdated (deprecated, use diff to auto-detect).
            diff: Full PR diff to resolve focused context (optional).

        Returns:
            CommentView configured for the given comment type.
        """
        focused_diff = None
        if diff:
            ctx = DiffContextManager.from_diff(diff).build_comment_context(comment)
            focused_diff = ctx.focused_diff
            is_outdated = ctx.is_outdated
            line = ctx.line
        else:
            line = comment.line

        return cls(
            body=comment.body,
            author_name=comment.author_name,
            formatted_date=comment.formatted_date,
            file_path=comment.path,
            line=line,
            diff_hunk=comment.diff_hunk,
            focused_diff=focused_diff,
            is_outdated=is_outdated,
        )

    @classmethod
    def from_suggestion(cls, suggestion: Any) -> "CommentView":
        """
        Build a CommentView from a UIReviewSuggestion model.

        Args:
            suggestion: UIReviewSuggestion instance from the AI review layer.

        Returns:
            CommentView configured to display the AI suggestion.
        """
        return cls(
            body=suggestion.body,
            file_path=suggestion.file_path,
            line=suggestion.line,
            diff_hunk=suggestion.diff_context,
            severity=suggestion.severity,
        )

    @classmethod
    def from_action(
        cls,
        action: Any,
        diff_hunk: Optional[str] = None,
        file_excerpt: Optional[str] = None,
    ) -> "CommentView":
        """
        Build a CommentView from a ReviewActionProposal model.

        Args:
            action: ReviewActionProposal instance from the new review pipeline.
            diff_hunk: Pre-extracted diff hunk for the action's file/line (optional).
            file_excerpt: Plain-file code excerpt for an action the diff cannot anchor
                          (optional) — see extract_file_excerpt_for_action.

        Returns:
            CommentView configured to display the review action.
        """
        # A reply to an existing thread inherits that thread's position, which GitHub
        # already accepted — its line needs no anchoring. Only a brand-new comment has to
        # be anchored into this PR's diff, so only it can be left unanchored.
        is_new_comment = _is_new_comment_action(action)

        return cls(
            body=action.body,
            file_path=action.path,
            # For a new comment, only the resolved line is a real position in this PR's
            # diff. Falling back to the raw AI line would render a code block around a
            # line nothing verified — extract_diff_hunk_for_action already returns no hunk
            # in that case, so the block would be empty or, worse, from elsewhere.
            line=action.resolved_line if is_new_comment else (action.resolved_line or action.line),
            diff_hunk=diff_hunk,
            severity=action.severity,
            line_label=_build_action_line_label(action),
            file_excerpt=file_excerpt,
            file_excerpt_line=action.line,
        )

    def compose(self) -> ComposeResult:
        """Compose the comment view: severity badge, metadata, location, code, body."""
        # 1. Severity badge (AI suggestions only)
        if self.severity:
            yield self._severity_badge()

        # 2. Author + date (omitted for AI suggestions that have no human author)
        if self.author_name:
            yield self._metadata_container()
            yield Text("")

        # 3. File/location context
        if self.file_path:
            # Inline review comment (has line) or file-level comment (no line)
            yield self._file_info_container()
            if self.is_outdated:
                yield self._outdated_badge()
        else:
            # No file path — this is a general PR comment (no file reference)
            yield self._general_comment_badge()

        # 4. Code context (only when diff context is available AND there's a specific line)
        # File-level comments (path but no line) don't show diff — too verbose
        # Use focused_diff if available (from ResolvedCommentContext), fallback to full diff_hunk
        has_diff = self.focused_diff or self.diff_hunk
        if has_diff and self.line:
            yield self._code_context_widget()
        elif self.file_excerpt:
            # No diff to show: the finding is about code this PR did not change, read
            # straight from the file. Captioned so it is never mistaken for the diff.
            yield from self._file_excerpt_widgets()

        # 5. Comment body
        if self.body and self.body.strip():
            for widget in self._parse_and_render_body():
                yield widget
        else:
            yield DimItalicText("(empty comment)")

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _severity_badge(self) -> Text:
        """Create severity badge widget for AI suggestions."""
        badge_labels = {
            FindingSeverity.BLOCKING: "🔴 BLOCKING",
            FindingSeverity.IMPORTANT: "🟡 IMPORTANT",
            FindingSeverity.NIT: "🔵 NIT",
            ThreadSeverity.IMPORTANT: "🟡 IMPORTANT",
            ThreadSeverity.NIT: "🔵 NIT",
        }
        badge_text = badge_labels[self.severity]
        badge = Text(badge_text)
        badge.add_class("severity-badge")
        badge.add_class(self.severity.value)
        return badge

    def _metadata_container(self) -> Horizontal:
        """Create author + date row."""
        author_widget = BoldText(self.author_name)
        author_widget.styles.width = "auto"

        date_widget = DimText(f" • {self.formatted_date}")
        date_widget.styles.width = "auto"

        container = Horizontal(author_widget, date_widget)
        container.styles.height = "auto"
        return container

    def _file_info_container(self) -> Horizontal:
        """Create file path + line number row (inline review comments)."""
        file_widget = ItalicText(self.file_path)
        file_widget.styles.width = "auto"
        file_widget.styles.margin = (0, 1, 0, 0)

        if self.line_label:
            line_info = self.line_label
        elif self.line:
            line_info = f"Line {self.line}"
        elif self.severity:
            # AI suggestion with file but no resolved line yet
            line_info = "General file comment"
        else:
            line_info = "General file comment"

        line_widget = DimText(line_info)
        line_widget.styles.width = "auto"

        container = Horizontal(file_widget, line_widget)
        container.styles.height = "auto"
        container.styles.margin = (0, 0, 1, 0)
        return container

    def _outdated_badge(self) -> Text:
        """Create outdated indicator for threads on stale code."""
        badge = Text("Outdated")
        badge.add_class("outdated-badge")
        return badge

    def _general_comment_badge(self) -> Text:
        """Create badge indicating this is a PR-level comment with no file reference."""
        badge = Text("💬 General PR comment")
        badge.add_class("general-comment-badge")
        return badge

    def _code_context_widget(self) -> CodeBlock:
        """Create syntax-highlighted diff block around the commented line."""
        # Use pre-computed focused diff if available (from ResolvedCommentContext)
        if self.focused_diff:
            context_code = self.focused_diff
        else:
            # Fallback: trim the raw diff_hunk locally
            from .comment_utils import extract_diff_context
            context_code = extract_diff_context(
                diff_hunk=self.diff_hunk,
                target_line=self.line,
                is_outdated=self.is_outdated,
            )
        return CodeBlock(
            code=context_code,
            language="diff",
            theme="native",
            line_numbers=True,
        )

    def _file_excerpt_widgets(self):
        """Yield the caption + plain code block for a pre-existing-code excerpt."""
        caption = (
            f"pre-existing code around line {self.file_excerpt_line} "
            "(unchanged by this PR)"
            if self.file_excerpt_line
            else "pre-existing code (unchanged by this PR)"
        )
        yield DimItalicText(caption)
        yield CodeBlock(
            code=self.file_excerpt,
            # Plain file text, not a diff: these lines have no +/- prefix, and
            # highlighting them as a diff would render every line as unchanged context.
            language="text",
            theme="native",
            line_numbers=False,
        )

    def _parse_and_render_body(self) -> List[Any]:
        """Parse comment body and return Textual widgets for rendering."""
        return render_comment_elements(
            body=self.body,
            diff_hunk=self.diff_hunk,
            line=self.line,
        )


def _is_new_comment_action(action: Any) -> bool:
    """Return True for a brand-new comment (not a reply to, or resolution of, a thread)."""
    action_type = getattr(action, "action_type", None)
    value = getattr(action_type, "value", action_type)
    return value == ReviewActionType.NEW_COMMENT.value


def _build_action_line_label(action: Any) -> Optional[str]:
    """
    Build a user-facing line label for review action preview.

    For a new comment whose anchor could not be resolved, the label says so instead of
    showing the AI's raw line number: that number was never validated against the diff,
    and a finding about pre-existing code outside this PR carries no valid line at all.
    Presenting it like a resolved one would claim a precision nothing backs, and hide why
    the comment cannot be published inline. Thread replies keep their line as-is — it
    comes from the existing thread, not from anchoring.
    """
    resolved_line = getattr(action, "resolved_line", None)
    original_line = getattr(action, "original_line", None) or getattr(action, "line", None)
    resolution_source = getattr(action, "resolution_source", None)

    if resolved_line and original_line and resolved_line != original_line:
        suffix = f" via {resolution_source}" if resolution_source else ""
        return f"Line {resolved_line} (AI {original_line}{suffix})"
    if resolved_line:
        return f"Line {resolved_line}"

    if not _is_new_comment_action(action):
        return f"Line {original_line}" if original_line else None

    if original_line:
        return f"⚠ outside this PR's diff (AI said {original_line})"
    return "⚠ outside this PR's diff"


__all__ = ["CommentView"]
