# plugins/titan-plugin-github/titan_plugin_github/messages.py
class Messages:
    class GitHub:
        """GitHub operations messages"""
        # Client errors
        CLI_NOT_FOUND: str = "GitHub CLI ('gh') not found. Please install it and ensure it's in your PATH."
        NOT_AUTHENTICATED: str = "GitHub CLI is not authenticated. Run: gh auth login"
        CONFIG_REPO_MISSING: str = "GitHub repository owner and name must be configured in [plugins.github.config]."
        API_ERROR: str = "GitHub API error: {error_msg}"
        PERMISSION_ERROR: str = "Permission denied for GitHub operation: {error_msg}"
        UNEXPECTED_ERROR: str = "An unexpected GitHub error occurred: {error}"

        # Pull Requests
        PR_NOT_FOUND: str = "Pull Request #{pr_number} not found."
        PR_CREATING: str = "Creating pull request..."
        PR_CREATED: str = "PR #{number} created: {url}"
        PR_UPDATED: str = "PR #{number} updated"
        PR_MERGED: str = "PR #{number} merged"
        PR_CLOSED: str = "PR #{number} closed"
        PR_FAILED: str = "Failed to create PR: {error}"
        PR_CREATION_FAILED: str = "Failed to create pull request: {error}"
        FAILED_TO_PARSE_PR_NUMBER: str = "Failed to parse PR number from URL: {url}"

        # Merge
        INVALID_MERGE_METHOD: str = "Invalid merge method: {method}. Must be one of: {valid_methods}"

        # Reviews
        REVIEW_NOT_FOUND: str = "Review ID #{review_id} for Pull Request #{pr_number} not found."
        REVIEW_CREATING: str = "Creating review..."
        REVIEW_CREATED: str = "Review submitted"
        REVIEW_FAILED: str = "Failed to submit review: {error}"

        # Comments
        COMMENT_CREATING: str = "Adding comment..."
        COMMENT_CREATED: str = "Comment added"
        COMMENT_FAILED: str = "Failed to add comment: {error}"

        # Repository
        REPO_NOT_FOUND: str = "Repository not found"
        REPO_ACCESS_DENIED: str = "Access denied to repository"

        # Authentication
        AUTH_MISSING: str = "GitHub token not found. Set GITHUB_TOKEN environment variable."
        AUTH_INVALID: str = "Invalid GitHub token"

msg = Messages()
