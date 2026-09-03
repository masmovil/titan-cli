# plugins/titan-plugin-github/titan_plugin_github/models/network/graphql/pull_request.py
"""
GraphQL Pull Request Models

Faithful representations of GitHub PullRequest fields that are only available
through the GraphQL API (the gh CLI's `pr view --json` does not expose them).
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class GraphQLPullRequestMergeQueueState:
    """
    Merge queue state of a pull request from the GraphQL API.

    See: https://docs.github.com/en/graphql/reference/objects#pullrequest

    Field names match the GraphQL schema exactly (camelCase preserved).

    Attributes:
        number: Pull request number
        state: Pull request state ("OPEN", "CLOSED", "MERGED")
        isMergeQueueEnabled: Whether the base branch requires a merge queue
        isInMergeQueue: Whether this pull request is currently in the merge queue
        mergeQueueEntryPosition: Position in the queue, when queued
        mergeQueueEntryState: Queue entry state (e.g. "QUEUED", "AWAITING_CHECKS",
            "MERGEABLE", "UNMERGEABLE"), when queued
    """
    number: int
    state: str
    isMergeQueueEnabled: bool
    isInMergeQueue: bool
    mergeQueueEntryPosition: Optional[int] = None
    mergeQueueEntryState: Optional[str] = None

    @classmethod
    def from_graphql(cls, data: Dict[str, Any]) -> 'GraphQLPullRequestMergeQueueState':
        """
        Create GraphQLPullRequestMergeQueueState from a GraphQL pullRequest node.

        Args:
            data: pullRequest node from the GraphQL response

        Returns:
            GraphQLPullRequestMergeQueueState instance
        """
        entry = data.get("mergeQueueEntry") or {}

        return cls(
            number=data.get("number", 0),
            state=data.get("state", ""),
            isMergeQueueEnabled=bool(data.get("isMergeQueueEnabled", False)),
            isInMergeQueue=bool(data.get("isInMergeQueue", False)),
            mergeQueueEntryPosition=entry.get("position"),
            mergeQueueEntryState=entry.get("state"),
        )
