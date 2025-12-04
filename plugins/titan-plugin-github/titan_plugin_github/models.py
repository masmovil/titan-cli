# plugins/titan-plugin-github/titan_plugin_github/models.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class User:
    """GitHub user representation"""
    login: str
    name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """
        Create User from API response

        Args:
            data: User data from GitHub API

        Returns:
            User instance

        Examples:
            >>> data = {"login": "john", "name": "John Doe"}
            >>> user = User.from_dict(data)
        """
        if not data:
            return cls(login="unknown")

        return cls(
            login=data.get("login", "unknown"),
            name=data.get("name"),
            email=data.get("email"),
            avatar_url=data.get("avatar_url")
        )


@dataclass
class ReviewComment:
    """GitHub PR review comment"""
    id: int
    path: str
    line: int
    body: str
    user: User
    created_at: str
    side: str = "RIGHT"  # RIGHT or LEFT

    @classmethod
    def from_dict(cls, data: dict) -> 'ReviewComment':
        """Create ReviewComment from API response"""
        return cls(
            id=data.get("id", 0),
            path=data.get("path", ""),
            line=data.get("line", 0),
            body=data.get("body", ""),
            user=User.from_dict(data.get("user", {})),
            created_at=data.get("created_at", ""),
            side=data.get("side", "RIGHT")
        )


@dataclass
class Review:
    """GitHub PR review"""
    id: int
    user: User
    body: str
    state: str  # PENDING, APPROVED, CHANGES_REQUESTED, COMMENTED
    submitted_at: Optional[str] = None
    commit_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'Review':
        """Create Review from API response"""
        return cls(
            id=data.get("id", 0),
            user=User.from_dict(data.get("user", {})),
            body=data.get("body", ""),
            state=data.get("state", "PENDING"),
            submitted_at=data.get("submitted_at"),
            commit_id=data.get("commit_id")
        )


@dataclass
class PullRequest:
    """
    GitHub Pull Request representation

    Attributes:
        number: PR number
        title: PR title
        body: PR description
        state: open, closed, merged
        author: PR author
        base_ref: Base branch (e.g., develop)
        head_ref: Head branch (e.g., feature/xyz)
        additions: Lines added
        deletions: Lines deleted
        changed_files: Number of files changed
        mergeable: Can be merged
        draft: Is draft PR
        created_at: ISO date string
        updated_at: ISO date string
        merged_at: ISO date string (if merged)
        reviews: List of reviews
        labels: List of label names
    """
    number: int
    title: str
    body: str
    state: str
    author: User
    base_ref: str
    head_ref: str
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    mergeable: bool = True
    draft: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    merged_at: Optional[str] = None
    reviews: List[Review] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> 'PullRequest':
        """
        Create PullRequest from GitHub API response

        Args:
            data: PR data from GitHub API (gh pr view --json format)

        Returns:
            PullRequest instance

        Examples:
            >>> data = gh_api_response
            >>> pr = PullRequest.from_dict(data)
        """
        # Parse author
        author_data = data.get("author", {})
        author = User.from_dict(author_data)

        # Parse reviews
        reviews_data = data.get("reviews", [])
        reviews = [Review.from_dict(r) for r in reviews_data]

        # Parse labels
        labels_data = data.get("labels", [])
        labels = [label.get("name", "") for label in labels_data]

        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            state=data.get("state", "OPEN"),
            author=author,
            base_ref=data.get("baseRefName", ""),
            head_ref=data.get("headRefName", ""),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changedFiles", 0),
            mergeable=data.get("mergeable", "MERGEABLE") == "MERGEABLE",
            draft=data.get("isDraft", False),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            merged_at=data.get("mergedAt"),
            reviews=reviews,
            labels=labels
        )

    def get_status_emoji(self) -> str:
        """Get emoji for PR state"""
        if self.state == "MERGED":
            return "🟣"
        elif self.state == "CLOSED":
            return "🔴"
        elif self.draft:
            return "📝"
        elif self.state == "OPEN":
            return "🟢"
        return "⚪"

    def get_review_status(self) -> str:
        """Get review status summary"""
        if not self.reviews:
            return "No reviews"

        approved = sum(1 for r in self.reviews if r.state == "APPROVED")
        changes = sum(1 for r in self.reviews if r.state == "CHANGES_REQUESTED")

        if approved > 0 and changes == 0:
            return f"✅ {approved} approved"
        elif changes > 0:
            return f"❌ {changes} changes requested"
        else:
            return f"💬 {len(self.reviews)} comments"


@dataclass
class PRSearchResult:
    """Result of searching pull requests"""
    prs: List[PullRequest]
    total: int

    @classmethod
    def from_list(cls, data: List[dict]) -> 'PRSearchResult':
        """
        Create PRSearchResult from list of PR data

        Args:
            data: List of PR dictionaries from GitHub API

        Returns:
            PRSearchResult instance
        """
        prs = [PullRequest.from_dict(pr_data) for pr_data in data]
        return cls(prs=prs, total=len(prs))


@dataclass
class PRComment:
    """
    Pull request comment (review comment or issue comment)

    Attributes:
        id: Comment ID
        body: Comment text
        user: User who created the comment
        created_at: Creation timestamp
        path: File path (for review comments)
        line: Line number (for review comments)
        diff_hunk: Diff context (for review comments)
        pull_request_review_id: Review ID (for review comments)
        in_reply_to_id: ID of parent comment (if it's a reply)
        is_review_comment: True if inline review comment, False if issue comment
    """
    id: int
    body: str
    user: User
    created_at: str
    path: Optional[str] = None
    line: Optional[int] = None
    diff_hunk: Optional[str] = None
    pull_request_review_id: Optional[int] = None
    in_reply_to_id: Optional[int] = None
    is_review_comment: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any], is_review: bool = True) -> 'PRComment':
        """Create from API response"""
        user_data = data.get("user", {})
        user = User(
            login=user_data.get("login", ""),
            name=user_data.get("name"),
            email=user_data.get("email"),
            avatar_url=user_data.get("avatar_url")
        )

        return cls(
            id=data.get("id", 0),
            body=data.get("body", ""),
            user=user,
            created_at=data.get("created_at", ""),
            path=data.get("path"),
            line=data.get("line"),
            diff_hunk=data.get("diff_hunk"),
            pull_request_review_id=data.get("pull_request_review_id"),
            in_reply_to_id=data.get("in_reply_to_id"),
            is_review_comment=is_review
        )


@dataclass
class PRMergeResult:
    """
    Result of merging a pull request

    Attributes:
        merged: Whether the PR was successfully merged
        sha: Commit SHA of the merge (if successful)
        message: Success or error message
    """
    merged: bool
    sha: Optional[str] = None
    message: str = ""
