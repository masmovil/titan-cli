# plugins/titan-plugin-github/titan_plugin_github/exceptions.py
class GitHubError(Exception):
    """Base exception for all GitHub related errors."""
    pass

class GitHubAuthenticationError(GitHubError):
    """Raised when GitHub authentication fails (e.g., gh CLI not authenticated)."""
    pass

class GitHubAPIError(GitHubError):
    """Raised when a GitHub API call or gh CLI command fails."""
    pass

class PRNotFoundError(GitHubAPIError):
    """Raised when a specified Pull Request is not found."""
    pass

class ReviewNotFoundError(GitHubAPIError):
    """Raised when a specified Review is not found."""
    pass

class GitHubPermissionError(GitHubAPIError):
    """Raised when the authenticated user does not have sufficient permissions."""
    pass

class GitHubConfigurationError(GitHubError):
    """Raised when the GitHub plugin is misconfigured."""
    pass
