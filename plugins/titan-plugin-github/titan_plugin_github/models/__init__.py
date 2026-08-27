"""
GitHub Plugin Models

This package contains all data models for the GitHub plugin:

- network/: Network models (REST and GraphQL) - faithful to API responses
- view/: View models - optimized for UI rendering
- mappers/: Conversion functions from network to view models
- formatting.py: Shared formatting utilities
"""

# Network models (REST)
from .network.rest import (
    NetworkUser,
    NetworkReview,
    NetworkPullRequest,
    NetworkPRSearchResult,
    NetworkPRMergeResult,
    NetworkIssue,
)

# Network models (GraphQL)
from .network.graphql import (
    GraphQLUser,
    GraphQLPullRequestReviewComment,
    GraphQLPullRequestReviewThread,
    GraphQLIssueComment,
)

# View models
from .view import (
    UIComment,
    UICommentThread,
    UIPullRequest,
    UIIssue,
    UIRelease,
    UIReviewSuggestion,
)

from .pr_enums import PRMergeableState, PRReviewDecision, PRState

# Mappers
from .mappers import (
    from_rest_pr,
    from_rest_issue,
    from_graphql_review_comment,
    from_graphql_issue_comment,
    from_graphql_review_thread,
)

# Formatting utilities
from . import formatting


__all__ = [
    # Network models (REST)
    "NetworkUser",
    "NetworkReview",
    "NetworkPullRequest",
    "NetworkPRSearchResult",
    "NetworkPRMergeResult",
    "NetworkIssue",
    # Network models (GraphQL)
    "GraphQLUser",
    "GraphQLPullRequestReviewComment",
    "GraphQLPullRequestReviewThread",
    "GraphQLIssueComment",
    # View models
    "UIComment",
    "UICommentThread",
    "UIPullRequest",
    "UIIssue",
    "UIRelease",
    "UIReviewSuggestion",
    "PRState",
    "PRMergeableState",
    "PRReviewDecision",
    # Mappers
    "from_rest_pr",
    "from_rest_issue",
    "from_graphql_review_comment",
    "from_graphql_issue_comment",
    "from_graphql_review_thread",
    # Formatting
    "formatting",
]
