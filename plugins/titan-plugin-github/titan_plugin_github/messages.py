# plugins/titan-plugin-github/titan_plugin_github/messages.py
class Messages:
    class GitHub:
        cli_not_found = "GitHub CLI ('gh') not found. Please install it and ensure it's in your PATH."
        not_authenticated = "GitHub CLI is not authenticated. Run: gh auth login"
        config_repo_missing = "GitHub repository owner and name must be configured in [plugins.github.config]."
        pr_not_found = "Pull Request #{pr_number} not found."
        review_not_found = "Review ID #{review_id} for Pull Request #{pr_number} not found."
        api_error = "GitHub API error: {error_msg}"
        permission_error = "Permission denied for GitHub operation: {error_msg}"
        unexpected_error = "An unexpected GitHub error occurred: {error}"
        invalid_merge_method = "Invalid merge method: {method}. Must be one of: {valid_methods}"
        pr_creation_failed = "Failed to create pull request: {error}"
        failed_to_parse_pr_number = "Failed to parse PR number from URL: {url}"

        # Additional messages for general GitHub operations (moved from core messages.py)
        # Pull Requests
        PR_CREATING = "Creating pull request..."
        PR_CREATED = "PR #{number} created: {url}"
        PR_UPDATED = "PR #{number} updated"
        PR_MERGED = "PR #{number} merged"
        PR_CLOSED = "PR #{number} closed"
        PR_FAILED = "Failed to create PR: {error}"
        # PR_NOT_FOUND (already defined above)

        # Reviews
        REVIEW_CREATING = "Creating review..."
        REVIEW_CREATED = "Review submitted"
        REVIEW_FAILED = "Failed to submit review: {error}"

        # Comments
        COMMENT_CREATING = "Adding comment..."
        COMMENT_CREATED = "Comment added"
        COMMENT_FAILED = "Failed to add comment: {error}"

        # Repository
        REPO_NOT_FOUND = "Repository not found"
        REPO_ACCESS_DENIED = "Access denied to repository"

        # Authentication
        AUTH_MISSING = "GitHub token not found. Set GITHUB_TOKEN environment variable."
        AUTH_INVALID = "Invalid GitHub token"

msg = Messages()
