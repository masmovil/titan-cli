# plugins/titan-plugin-github/titan_plugin_github/models/network/rest/pull_request.py
"""
REST API Pull Request Model

Faithful representation of GitHub PR from REST API (gh CLI).
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .user import NetworkUser
from .review import NetworkReview
from ...pr_enums import PRMergeableState, PRReviewDecision, PRState


def _coerce_enum(value: Any, enum_cls, default):
    """Coerce a raw API value into a StrEnum member safely."""
    try:
        return enum_cls(value)
    except Exception:
        return default


@dataclass
class NetworkPullRequest:
    """
    GitHub Pull Request from REST API.

    Faithful to `gh pr view --json` output.
    Field names match gh CLI JSON response exactly (camelCase preserved).

    No transformations or computed fields - just raw API data.

    Attributes:
        number: PR number
        title: PR title
        body: PR description
        state: PR state (OPEN, CLOSED, MERGED)
        author: PR author
        baseRefName: Base branch name (camelCase as in API)
        headRefName: Head branch name (camelCase as in API)
        additions: Lines added
        deletions: Lines deleted
        changedFiles: Number of files changed (camelCase as in API)
        mergeable: Mergeable status string (MERGEABLE, CONFLICTING, UNKNOWN)
        isDraft: Draft status (camelCase as in API)
        createdAt: Creation timestamp (ISO 8601, camelCase as in API)
        updatedAt: Last update timestamp (ISO 8601, camelCase as in API)
        mergedAt: Merge timestamp if merged (ISO 8601, camelCase as in API)
        reviews: List of reviews
        labels: List of label objects with 'name' field
        requestedReviewers: List of users requested to review the PR
    """
    number: int
    title: str
    body: str
    state: PRState
    author: NetworkUser
    baseRefName: str  # Keep camelCase from API
    headRefName: str  # Keep camelCase from API
    additions: int = 0
    deletions: int = 0
    changedFiles: int = 0  # Keep camelCase from API
    mergeable: PRMergeableState = PRMergeableState.UNKNOWN
    isDraft: bool = False  # Keep camelCase from API
    createdAt: Optional[str] = None  # Keep camelCase from API
    updatedAt: Optional[str] = None  # Keep camelCase from API
    mergedAt: Optional[str] = None  # Keep camelCase from API
    reviews: List[NetworkReview] = field(default_factory=list)
    labels: List[Dict[str, Any]] = field(default_factory=list)  # Raw label objects
    statusCheckRollup: List[Dict[str, Any]] = field(default_factory=list)
    reviewDecision: Optional[PRReviewDecision] = None
    isCrossRepository: bool = False
    headRepositoryOwnerLogin: Optional[str] = None
    headRepositoryName: Optional[str] = None
    requestedReviewers: List[NetworkUser] = field(default_factory=list)  # Users requested to review

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'NetworkPullRequest':
        """
        Create NetworkPullRequest from gh CLI JSON response.

        Direct 1:1 mapping from API response, no transformations.

        Args:
            data: PR data from `gh pr view --json`

        Returns:
            NetworkPullRequest instance

        Examples:
            >>> data = json.loads(subprocess.run(["gh", "pr", "view", "123", "--json", "..."]))
            >>> pr = NetworkPullRequest.from_json(data)
        """
        # Parse author
        author_data = data.get("author", {})
        author = NetworkUser.from_json(author_data)

        # Parse reviews
        reviews_data = data.get("reviews", [])
        reviews = [NetworkReview.from_json(r) for r in reviews_data]

        # Parse requested reviewers (gh CLI JSON field is "reviewRequests")
        requested_reviewers_data = data.get("reviewRequests", [])
        requested_reviewers = [NetworkUser.from_json(r) for r in requested_reviewers_data]

        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            state=_coerce_enum(data.get("state", PRState.OPEN), PRState, PRState.OPEN),
            author=author,
            baseRefName=data.get("baseRefName", ""),
            headRefName=data.get("headRefName", ""),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changedFiles=data.get("changedFiles", 0),
            mergeable=_coerce_enum(
                data.get("mergeable", PRMergeableState.UNKNOWN),
                PRMergeableState,
                PRMergeableState.UNKNOWN,
            ),
            isDraft=data.get("isDraft", False),
            createdAt=data.get("createdAt"),
            updatedAt=data.get("updatedAt"),
            mergedAt=data.get("mergedAt"),
            reviews=reviews,
            labels=data.get("labels", []),  # Keep raw label objects
            statusCheckRollup=data.get("statusCheckRollup", []),
            reviewDecision=(
                _coerce_enum(data.get("reviewDecision"), PRReviewDecision, None)
                if data.get("reviewDecision") is not None
                else None
            ),
            isCrossRepository=data.get("isCrossRepository", False),
            headRepositoryOwnerLogin=(data.get("headRepositoryOwner") or {}).get("login"),
            headRepositoryName=(data.get("headRepository") or {}).get("name"),
            requestedReviewers=requested_reviewers,
        )


@dataclass
class NetworkPRSearchResult:
    """
    Result of searching pull requests via REST API.

    Attributes:
        prs: List of pull requests
        total: Total count
    """
    prs: List[NetworkPullRequest]
    total: int

    @classmethod
    def from_json_list(cls, data: List[Dict[str, Any]]) -> 'NetworkPRSearchResult':
        """
        Create NetworkPRSearchResult from list of PR JSON objects.

        Args:
            data: List of PR dictionaries from gh CLI

        Returns:
            NetworkPRSearchResult instance
        """
        prs = [NetworkPullRequest.from_json(pr_data) for pr_data in data]
        return cls(prs=prs, total=len(prs))


@dataclass
class NetworkPRFile:
    """
    Changed file in a PR from REST API.

    Faithful to /repos/{owner}/{repo}/pulls/{pr_number}/files response.
    """
    filename: str
    status: str  # "added", "removed", "modified", "renamed", "copied", "changed"
    additions: int
    deletions: int
    changes: int
    patch: Optional[str] = None  # Missing for binary files or files exceeding size limit

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'NetworkPRFile':
        return cls(
            filename=data.get("filename", ""),
            status=data.get("status", "modified"),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changes=data.get("changes", 0),
            patch=data.get("patch"),
        )


@dataclass
class NetworkPRCreated:
    """
    Result of creating a PR via REST API.

    Attributes:
        number: PR number
        url: Full PR URL
        state: "open" or "draft"
    """
    number: int
    url: str
    state: str


@dataclass
class NetworkPRMergeResult:
    """
    Result of merging a pull request via REST API.

    Attributes:
        merged: Whether the PR was successfully merged
        sha: Commit SHA of the merge (if successful)
        message: Success or error message
    """
    merged: bool
    sha: Optional[str] = None
    message: str = ""
