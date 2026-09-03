"""
GitHub Network Models

Network models represent data exactly as it comes from GitHub APIs:
- rest/: Models from REST API (gh CLI JSON responses)
- graphql/: Models from GraphQL API

These models are faithful to API responses with no transformations.
Use mappers to convert to view models for UI rendering.
"""

# Re-export for convenience
from .rest import (
    NetworkUser,
    NetworkReview,
    NetworkPullRequest,
    NetworkPRSearchResult,
    NetworkPRMergeResult,
    NetworkIssue,
)

from .graphql import (
    GraphQLUser,
    GraphQLPullRequestReviewComment,
    GraphQLPullRequestReviewThread,
    GraphQLIssueComment,
    GraphQLPullRequestMergeQueueState,
)

__all__ = [
    # REST models
    "NetworkUser",
    "NetworkReview",
    "NetworkPullRequest",
    "NetworkPRSearchResult",
    "NetworkPRMergeResult",
    "NetworkIssue",
    # GraphQL models
    "GraphQLUser",
    "GraphQLPullRequestReviewComment",
    "GraphQLPullRequestReviewThread",
    "GraphQLIssueComment",
    "GraphQLPullRequestMergeQueueState",
]
