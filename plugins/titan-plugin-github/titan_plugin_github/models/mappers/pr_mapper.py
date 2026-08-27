# plugins/titan-plugin-github/titan_plugin_github/models/mappers/pr_mapper.py
"""
Pull Request Mappers

Converts network models (REST/GraphQL) to view models (UI).
All presentation logic and transformations live here.
"""
from ..review_enums import FileChangeStatus
from ..network.rest import NetworkPullRequest, NetworkPRMergeResult, NetworkPRFile, NetworkPRCreated
from ..view import UIPullRequest, UIPRMergeResult, UIFileChange, UIPRCreated
from ..formatting import (
    format_date,
    get_pr_status_icon,
    format_pr_stats,
    format_branch_info,
    calculate_review_summary,
    summarize_status_check_rollup,
    summarize_review_status,
    format_short_sha,
)


def from_rest_pr(rest_pr: NetworkPullRequest) -> UIPullRequest:
    """
    Convert REST PR to UI PR.

    Applies all transformations and pre-calculates display fields.

    Args:
        rest_pr: NetworkPullRequest from REST API

    Returns:
        UIPullRequest ready for rendering
    """
    # Extract label names from label objects
    label_names = [label.get("name", "") for label in rest_pr.labels]

    # Extract requested reviewers
    requested_reviewers = [user.login for user in rest_pr.requestedReviewers]

    # Calculate pending reviewers (requested but not yet reviewed)
    reviewed_logins = {review.user.login for review in rest_pr.reviews if review.state != "PENDING"}
    pending_reviewers = [login for login in requested_reviewers if login not in reviewed_logins]

    return UIPullRequest(
        number=rest_pr.number,
        title=rest_pr.title,
        body=rest_pr.body,
        status_icon=get_pr_status_icon(rest_pr.state, rest_pr.isDraft),
        state=rest_pr.state,
        author_name=rest_pr.author.login,
        head_ref=rest_pr.headRefName,
        base_ref=rest_pr.baseRefName,
        branch_info=format_branch_info(rest_pr.headRefName, rest_pr.baseRefName),
        stats=format_pr_stats(rest_pr.additions, rest_pr.deletions),
        files_changed=rest_pr.changedFiles,
        is_mergeable=(rest_pr.mergeable == "MERGEABLE"),
        is_draft=rest_pr.isDraft,
        review_summary=calculate_review_summary(rest_pr.reviews),
        checks_summary=summarize_status_check_rollup(rest_pr.statusCheckRollup),
        review_status_summary=summarize_review_status(rest_pr.reviewDecision, rest_pr.isDraft),
        labels=label_names,
        formatted_created_at=format_date(rest_pr.createdAt) if rest_pr.createdAt else "",
        formatted_updated_at=format_date(rest_pr.updatedAt) if rest_pr.updatedAt else "",
        is_cross_repository=rest_pr.isCrossRepository,
        head_repository_owner=rest_pr.headRepositoryOwnerLogin,
        head_repository_name=rest_pr.headRepositoryName,
        requested_reviewers=requested_reviewers,
        pending_reviewers=pending_reviewers,
    )


_STATUS_ICONS = {
    FileChangeStatus.ADDED: "+",
    FileChangeStatus.DELETED: "−",
    FileChangeStatus.MODIFIED: "~",
    FileChangeStatus.RENAMED: "→",
}


def _normalize_file_status(status: str) -> FileChangeStatus:
    """Normalize GitHub file status values into Titan review statuses."""
    mapping = {
        "added": FileChangeStatus.ADDED,
        "modified": FileChangeStatus.MODIFIED,
        "renamed": FileChangeStatus.RENAMED,
        "removed": FileChangeStatus.DELETED,
        "deleted": FileChangeStatus.DELETED,
        "changed": FileChangeStatus.MODIFIED,
        "copied": FileChangeStatus.MODIFIED,
    }
    return mapping.get(status.lower(), FileChangeStatus.MODIFIED)


def from_network_pr_file(network_file: NetworkPRFile) -> UIFileChange:
    """
    Convert Network PR File to UI File Change.

    Args:
        network_file: NetworkPRFile from REST API

    Returns:
        UIFileChange ready for display or AI prompts
    """
    status = _normalize_file_status(network_file.status)

    return UIFileChange(
        path=network_file.filename,
        additions=network_file.additions,
        deletions=network_file.deletions,
        status=status,
        status_icon=_STATUS_ICONS.get(status, "~"),
    )


def from_network_pr_created(network_created: NetworkPRCreated) -> UIPRCreated:
    """
    Convert Network PR Created to UI PR Created.

    Args:
        network_created: NetworkPRCreated from REST API

    Returns:
        UIPRCreated ready for display
    """
    return UIPRCreated(
        number=network_created.number,
        url=network_created.url,
        state=network_created.state,
    )


def from_network_pr_merge_result(network_result: NetworkPRMergeResult) -> UIPRMergeResult:
    """
    Convert Network PR Merge Result to UI PR Merge Result.

    Args:
        network_result: NetworkPRMergeResult from REST API

    Returns:
        UIPRMergeResult with all fields pre-formatted for display
    """
    # Format SHA to short format
    sha_short = format_short_sha(network_result.sha)

    # Set status icon based on merge success
    status_icon = "✅" if network_result.merged else "❌"

    return UIPRMergeResult(
        merged=network_result.merged,
        status_icon=status_icon,
        sha_short=sha_short,
        message=network_result.message,
    )
