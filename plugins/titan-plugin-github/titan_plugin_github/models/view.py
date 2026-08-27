"""
GitHub UI/View Models

View models optimized for rendering GitHub data in Textual TUI widgets.
Decoupled from network/API models to keep widgets stable when API changes.

All formatting, computed fields, and presentation logic lives here.
Network models contain raw API data; view models contain UI-ready data.

These models are GitHub-specific and live in the GitHub plugin, not in the core.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional

from .pr_enums import PRState
from .review_enums import FileChangeStatus, FindingSeverity


@dataclass
class UIComment:
    """
    UI model for displaying a single comment.

    Optimized for rendering - contains only what widgets need, with pre-formatted data.
    """
    id: int
    body: str
    author_login: str  # Login/username (needed for bot detection, commit messages)
    author_name: str
    formatted_date: str  # Pre-formatted as "DD/MM/YYYY HH:MM:SS"
    path: Optional[str] = None
    line: Optional[int] = None
    diff_hunk: Optional[str] = None
    position: Optional[int] = None        # GitHub diff position (None when comment is outdated)
    original_line: Optional[int] = None   # originalLine from GitHub (line in old file version)

    @classmethod
    def from_review_comment(cls, comment: 'Any', is_outdated: bool = False) -> 'UIComment':
        """
        Convert a GraphQLPullRequestReviewComment (network model) to UIComment (view model).

        Delegates to mapper for conversion logic.

        Args:
            comment: GraphQLPullRequestReviewComment instance from GraphQL
            is_outdated: Whether this comment is on outdated code

        Returns:
            UIComment instance optimized for rendering
        """
        from .mappers import from_graphql_review_comment
        return from_graphql_review_comment(comment, is_outdated)

    @classmethod
    def from_issue_comment(cls, comment: 'Any') -> 'UIComment':
        """
        Convert a GraphQLIssueComment (network model) to UIComment (view model).

        Delegates to mapper for conversion logic.

        Args:
            comment: GraphQLIssueComment instance from GraphQL

        Returns:
            UIComment instance optimized for rendering
        """
        from .mappers import from_graphql_issue_comment
        return from_graphql_issue_comment(comment)


@dataclass
class UICommentThread:
    """
    UI model for displaying a comment thread.

    Contains a main comment, its replies, and thread metadata.
    Optimized for rendering in the TUI.
    """
    thread_id: str  # GraphQL node ID (for resolving/actions)
    main_comment: UIComment
    replies: List[UIComment]
    is_resolved: bool
    is_outdated: bool

    @classmethod
    def from_review_thread(cls, thread: 'Any') -> 'UICommentThread':
        """
        Convert a GraphQLPullRequestReviewThread (network model) to UICommentThread (view model).

        Delegates to mapper for conversion logic.

        Args:
            thread: GraphQLPullRequestReviewThread instance from GraphQL

        Returns:
            UICommentThread instance optimized for rendering
        """
        from .mappers import from_graphql_review_thread
        return from_graphql_review_thread(thread)

    @classmethod
    def from_issue_comment(cls, comment: 'Any') -> 'UICommentThread':
        """
        Wrap a GraphQLIssueComment as a pseudo-thread for uniform rendering.

        General PR comments have no thread concept, so they are wrapped in a
        UICommentThread with a synthetic thread_id ("general_{id}") that
        downstream code uses to distinguish them from review threads.

        Args:
            comment: GraphQLIssueComment instance from GraphQL

        Returns:
            UICommentThread with thread_id="general_{id}", no replies, not resolved
        """
        from .mappers import from_graphql_issue_comment
        ui_comment = from_graphql_issue_comment(comment)
        return cls(
            thread_id=f"general_{comment.databaseId}",
            main_comment=ui_comment,
            replies=[],
            is_resolved=False,
            is_outdated=False
        )

    @property
    def is_general_comment(self) -> bool:
        """True if this thread wraps a general PR comment (not an inline review thread)."""
        return self.thread_id.startswith("general_")


@dataclass
class UIPullRequest:
    """
    UI model for displaying a pull request.

    All fields are pre-formatted and ready for widget rendering.
    Computed/derived fields are calculated once during construction.

    Fields:
        requested_reviewers: All GitHub logins of users requested to review
        pending_reviewers: Logins of reviewers who haven't submitted a review yet
    """
    number: int
    title: str
    body: str
    status_icon: str  # "🟢" "🔴" "🟣" "📝" etc.
    state: PRState
    author_name: str  # Just the username
    head_ref: str  # Head branch name (for operations)
    base_ref: str  # Base branch name (for operations)
    branch_info: str  # "feat/xyz → develop" (pre-formatted for display)
    stats: str  # "+123 -45" (pre-formatted)
    files_changed: int
    is_mergeable: bool  # Boolean for logic
    is_draft: bool
    review_summary: str  # "✅ 2 approved", "❌ 1 changes requested", etc.
    labels: List[str]  # Just label names
    formatted_created_at: str  # "DD/MM/YYYY HH:MM:SS"
    formatted_updated_at: str  # "DD/MM/YYYY HH:MM:SS"
    checks_summary: str = ""
    review_status_summary: str = ""
    is_cross_repository: bool = False
    head_repository_owner: Optional[str] = None
    head_repository_name: Optional[str] = None
    requested_reviewers: List[str] = field(default_factory=list)  # All requested reviewer logins
    pending_reviewers: List[str] = field(default_factory=list)  # Reviewers who haven't reviewed yet


@dataclass
class UIIssue:
    """
    UI model for displaying an issue.

    All fields are pre-formatted and ready for widget rendering.
    """
    number: int
    title: str
    body: str
    status_icon: str  # "🟢" for open, "🔴" for closed
    state: str  # "OPEN", "CLOSED"
    author_name: str
    labels: List[str]  # Just label names
    formatted_created_at: str  # "DD/MM/YYYY HH:MM:SS"
    formatted_updated_at: str  # "DD/MM/YYYY HH:MM:SS"


@dataclass
class UIReview:
    """
    UI model for displaying a PR review.

    All fields are pre-formatted and ready for widget rendering.
    """
    id: int
    author_name: str
    body: str
    state_icon: str  # "🟢" APPROVED, "🔴" CHANGES_REQUESTED, "💬" COMMENTED, "⏳" PENDING
    state: str  # "APPROVED", "CHANGES_REQUESTED", "COMMENTED", "PENDING"
    formatted_submitted_at: str  # "DD/MM/YYYY HH:MM:SS"
    commit_id_short: str  # First 7 characters of SHA


@dataclass
class UIPRMergeResult:
    """
    UI model for displaying PR merge result.

    All fields are pre-formatted and ready for widget rendering.
    """
    merged: bool
    status_icon: str  # "✅" if merged, "❌" if not
    sha_short: str  # First 7 characters of merge commit SHA (or empty)
    message: str


@dataclass
class UIFileChange:
    """
    UI model for a changed file in a PR.

    Pre-formatted fields ready for display in lists and AI prompts.
    """
    path: str
    additions: int
    deletions: int
    status: FileChangeStatus
    status_icon: str  # "+", "−", "~", "→", etc.


@dataclass
class UIPRCreated:
    """
    UI model for a newly created pull request.

    Returned after create_pull_request — contains identifiers needed
    to display the result or navigate to the PR.
    """
    number: int
    url: str
    state: str  # "open" or "draft"


@dataclass
class UIRelease:
    """
    UI model for a GitHub release.

    Returned by create_release, list_releases, and get_release — contains
    the identifiers and notes body needed to display or summarize a release.
    """
    tag_name: str
    title: str
    url: str
    is_prerelease: bool
    body: str = ""
    published_at: str = ""
    is_draft: bool = False


@dataclass
class UIReviewSuggestion:
    """AI-generated review comment for a PR."""
    file_path: str
    line: Optional[int]
    body: str
    severity: FindingSeverity
    diff_context: Optional[str] = None  # Extracted diff hunk around the line
    snippet: Optional[str] = None  # Exact code line reported by AI for line lookup
    reply_to_comment_id: Optional[int] = None  # If set, this is a reply to an existing thread


__all__ = [
    "UIComment",
    "UICommentThread",
    "UIPullRequest",
    "UIIssue",
    "UIReview",
    "UIPRMergeResult",
    "UIFileChange",
    "UIPRCreated",
    "UIRelease",
    "UIReviewSuggestion",
]
