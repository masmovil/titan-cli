"""
GitHub Model Mappers

Mappers convert network models to view models.
All presentation logic and transformations live here.

Usage:
    from titan_plugin_github.models.mappers import from_rest_pr

    rest_pr = NetworkPullRequest.from_json(data)
    ui_pr = from_rest_pr(rest_pr)
"""

from .pr_mapper import (
    from_rest_pr,
    from_network_pr_merge_result,
    from_graphql_merge_queue_state,
    from_network_pr_file,
    from_network_pr_created,
)
from .issue_mapper import from_rest_issue
from .comment_mapper import from_graphql_review_comment, from_graphql_issue_comment
from .thread_mapper import from_graphql_review_thread
from .review_mapper import from_network_review
from .release_mapper import from_network_release

__all__ = [
    "from_rest_pr",
    "from_network_pr_merge_result",
    "from_graphql_merge_queue_state",
    "from_network_pr_file",
    "from_network_pr_created",
    "from_rest_issue",
    "from_graphql_review_comment",
    "from_graphql_issue_comment",
    "from_graphql_review_thread",
    "from_network_review",
    "from_network_release",
]
