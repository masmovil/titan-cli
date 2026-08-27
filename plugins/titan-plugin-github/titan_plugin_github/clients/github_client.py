# plugins/titan-plugin-github/titan_plugin_github/clients/github_client.py
"""
GitHub Client Facade

High-level facade for GitHub operations.
Delegates to specialized services (PRs, reviews, issues, teams).
"""
from typing import List, Optional, Dict, Any
import json

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.plugins.models import GitHubPluginConfig
from titan_plugin_git.clients.git_client import GitClient

from .network import GHNetwork, GraphQLNetwork
from .services import PRService, ReviewService, IssueService, TeamService, ReleaseService, ContentsService
from ..models.review_models import ReferencedCommitContext
from ..models.view import UIPullRequest, UICommentThread, UIIssue, UIPRMergeResult, UIReview, UIFileChange, UIPRCreated, UIRelease


class GitHubClient:
    """
    GitHub client facade.

    Provides a unified interface for all GitHub operations.
    Internally delegates to specialized services.

    This is the public API for the GitHub plugin.

    Examples:
        >>> config = GitHubPluginConfig()
        >>> client = GitHubClient(config, git_client, "owner", "repo")
        >>> result = client.get_pull_request(123)
        >>> match result:
        ...     case ClientSuccess(data=pr):
        ...         print(pr.title, pr.status_icon)
    """

    def __init__(
        self,
        config: GitHubPluginConfig,
        git_client: GitClient,
        repo_owner: str,
        repo_name: str,
        pr_template: Optional[str] = None
    ):
        """
        Initialize GitHub client.

        Args:
            config: GitHub configuration
            git_client: Initialized GitClient instance
            repo_owner: GitHub repository owner
            repo_name: GitHub repository name
            pr_template: Optional PR template content (loaded from config)

        Raises:
            GitHubAuthenticationError: If gh CLI is not authenticated
        """
        self.config = config
        self.git_client = git_client
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.pr_template = pr_template

        # Initialize network layers
        self._gh_network = GHNetwork(repo_owner, repo_name)
        self._graphql_network = GraphQLNetwork(self._gh_network)

        # Initialize services
        self._pr_service = PRService(self._gh_network)
        self._review_service = ReviewService(self._gh_network, self._graphql_network)
        self._issue_service = IssueService(self._gh_network)
        self._team_service = TeamService(self._gh_network)
        self._release_service = ReleaseService(self._gh_network)
        self._contents_service = ContentsService(self._gh_network)

    def get_pr_template(self) -> Optional[str]:
        """Get the PR template if available."""
        return self.pr_template

    # ============================================================================
    # Pull Request Operations
    # ============================================================================

    def get_pull_request(self, pr_number: int) -> ClientResult[UIPullRequest]:
        """Get a pull request by number."""
        return self._pr_service.get_pull_request(pr_number)

    def list_pending_review_prs(
        self, max_results: int = 50, include_team_reviews: bool = False
    ) -> ClientResult[List[UIPullRequest]]:
        """List PRs pending your review."""
        return self._pr_service.list_pending_review_prs(max_results, include_team_reviews)

    def list_my_prs(
        self, state: str = "open", max_results: int = 50
    ) -> ClientResult[List[UIPullRequest]]:
        """List your PRs."""
        return self._pr_service.list_my_prs(state, max_results)

    def list_all_prs(
        self, state: str = "open", max_results: int = 50
    ) -> ClientResult[List[UIPullRequest]]:
        """List all PRs in the repository."""
        return self._pr_service.list_all_prs(state, max_results)

    def get_pr_diff(self, pr_number: int, context_lines: int = 3) -> ClientResult[str]:
        """Get diff for a PR."""
        return self._pr_service.get_pr_diff(pr_number, context_lines)

    def get_pr_file_patches(
        self, pr_number: int, file_paths: List[str]
    ) -> ClientResult[str]:
        """Get patches for specific files in a PR (fallback for too-large diffs)."""
        return self._pr_service.get_pr_file_patches(pr_number, file_paths)

    def get_pr_files(self, pr_number: int) -> ClientResult[List[str]]:
        """Get list of changed files in PR."""
        return self._pr_service.get_pr_files(pr_number)

    def get_pr_files_with_stats(self, pr_number: int) -> ClientResult[List[UIFileChange]]:
        """Get all changed files with stats (path, additions, deletions, status)."""
        return self._pr_service.get_pr_files_with_stats(pr_number)

    def checkout_pr(self, pr_number: int) -> ClientResult[str]:
        """Checkout a PR locally."""
        return self._pr_service.checkout_pr(pr_number)

    def create_pull_request(
        self,
        title: str,
        body: str,
        base: str,
        head: str,
        draft: bool = False,
        assignees: Optional[List[str]] = None,
        reviewers: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
        excluded_reviewers: Optional[List[str]] = None
    ) -> ClientResult[UIPRCreated]:
        """
        Create a pull request.

        Note: excluded_reviewers is handled by expanding team reviewers and filtering.
        """
        # Handle team expansion and exclusions
        final_reviewers = []
        if reviewers:
            for reviewer in reviewers:
                # Check if it's a team (format: "org/team")
                if '/' in reviewer:
                    # Expand team to individual members
                    team_result = self._team_service.list_team_members(reviewer)

                    match team_result:
                        case ClientSuccess(data=team_members):
                            # Filter out excluded reviewers
                            if excluded_reviewers:
                                team_members = [m for m in team_members if m not in excluded_reviewers]
                            final_reviewers.extend(team_members)
                        case ClientError() as err:
                            # If team expansion fails, return error
                            return err
                else:
                    # It's a username, add directly if not excluded
                    if not excluded_reviewers or reviewer not in excluded_reviewers:
                        final_reviewers.append(reviewer)

        return self._pr_service.create_pull_request(
            title, body, base, head, draft, assignees, final_reviewers, labels
        )

    def merge_pr(
        self,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> ClientResult[UIPRMergeResult]:
        """Merge a pull request."""
        return self._pr_service.merge_pr(pr_number, merge_method, commit_title, commit_message)

    def add_comment(self, pr_number: int, body: str) -> ClientResult[None]:
        """Add a comment to a PR."""
        return self._pr_service.add_comment(pr_number, body)

    def get_pr_commit_sha(self, pr_number: int) -> ClientResult[str]:
        """Get the latest commit SHA for a PR."""
        return self._pr_service.get_pr_commit_sha(pr_number)

    def get_commit_review_context(
        self,
        commit_ref: str,
        *,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        max_files: int = 3,
        max_patch_chars: int = 4000,
    ) -> ClientResult[ReferencedCommitContext]:
        """Get a compact remote context for a referenced commit."""
        return self._pr_service.get_commit_review_context(
            commit_ref,
            repo_owner=repo_owner,
            repo_name=repo_name,
            max_files=max_files,
            max_patch_chars=max_patch_chars,
        )

    # ============================================================================
    # Review Operations
    # ============================================================================

    def get_pr_review_threads(
        self, pr_number: int, include_resolved: bool = True
    ) -> ClientResult[List[UICommentThread]]:
        """Get all review threads for a PR."""
        return self._review_service.get_pr_review_threads(pr_number, include_resolved)

    def resolve_review_thread(self, thread_node_id: str) -> ClientResult[None]:
        """Resolve a review thread."""
        return self._review_service.resolve_review_thread(thread_node_id)

    def get_pr_reviews(self, pr_number: int) -> ClientResult[List[UIReview]]:
        """Get all reviews for a PR."""
        return self._review_service.get_pr_reviews(pr_number)

    def create_draft_review(
        self, pr_number: int, payload: Dict[str, Any]
    ) -> ClientResult[int]:
        """Create a draft review on a PR."""
        return self._review_service.create_draft_review(pr_number, payload)

    def submit_review(
        self, pr_number: int, review_id: int | None, event: str, body: str = ""
    ) -> ClientResult[None]:
        """Submit a review. If review_id is None, creates directly with event."""
        return self._review_service.submit_review(pr_number, review_id, event, body)

    def delete_review(self, pr_number: int, review_id: int) -> ClientResult[None]:
        """Delete a draft review."""
        return self._review_service.delete_review(pr_number, review_id)

    def reply_to_comment(
        self, pr_number: int, comment_id: int, body: str
    ) -> ClientResult[None]:
        """Reply to a PR comment."""
        return self._review_service.reply_to_comment(pr_number, comment_id, body)

    def get_pr_general_comments(self, pr_number: int) -> ClientResult[List[UICommentThread]]:
        """Get general PR comments (not attached to code lines)."""
        return self._review_service.get_pr_general_comments(pr_number)

    def add_issue_comment(self, pr_number: int, body: str) -> ClientResult[None]:
        """Add a general comment to PR (issue comment)."""
        return self._review_service.add_issue_comment(pr_number, body)

    def request_pr_review(
        self, pr_number: int, reviewers: Optional[List[str]] = None
    ) -> ClientResult[None]:
        """Request review (or re-request) on a PR."""
        return self._review_service.request_pr_review(pr_number, reviewers)

    # ============================================================================
    # Issue Operations
    # ============================================================================

    def create_issue(
        self,
        title: str,
        body: str,
        assignees: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
    ) -> ClientResult[UIIssue]:
        """Create a new GitHub issue."""
        return self._issue_service.create_issue(title, body, assignees, labels)

    def list_labels(self) -> ClientResult[List[str]]:
        """List all labels in the repository."""
        return self._issue_service.list_labels()

    # ============================================================================
    # Release Operations
    # ============================================================================

    def create_release(
        self,
        tag_name: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        generate_notes: bool = False,
        verify_tag: bool = True,
        prerelease: bool = False,
    ) -> ClientResult[UIRelease]:
        """Create a GitHub release."""
        return self._release_service.create_release(
            tag_name=tag_name,
            title=title,
            notes=notes,
            generate_notes=generate_notes,
            verify_tag=verify_tag,
            prerelease=prerelease,
        )

    def list_releases(
        self, limit: int = 15, exclude_drafts: bool = True
    ) -> ClientResult[List[UIRelease]]:
        """List published GitHub releases for the repository."""
        return self._release_service.list_releases(limit=limit, exclude_drafts=exclude_drafts)

    def get_release(self, tag_name: str) -> ClientResult[UIRelease]:
        """Get a single GitHub release, including its full notes body."""
        return self._release_service.get_release(tag_name)

    # ============================================================================
    # Contents Operations
    # ============================================================================

    def list_repository_directory(
        self,
        path: str,
        ref: Optional[str] = None,
        *,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> ClientResult[List[Dict[str, Any]]]:
        """
        List the entries of a directory in a repository.

        Defaults to this client's own repo; pass repo_owner/repo_name to read
        from a different repository without instantiating a new client.
        """
        return self._contents_service.list_directory(
            path, ref, repo_owner=repo_owner, repo_name=repo_name
        )

    def path_exists(
        self,
        path: str,
        ref: Optional[str] = None,
        *,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> ClientResult[bool]:
        """
        Check whether a path exists in a repository.

        Defaults to this client's own repo; pass repo_owner/repo_name to check
        against a different repository without instantiating a new client.
        """
        return self._contents_service.path_exists(
            path, ref, repo_owner=repo_owner, repo_name=repo_name
        )

    # ============================================================================
    # Team Operations
    # ============================================================================

    def list_team_members(self, team_slug: str) -> ClientResult[List[str]]:
        """List all members of a GitHub team."""
        return self._team_service.list_team_members(team_slug)

    # ============================================================================
    # Utility Methods
    # ============================================================================

    def get_current_user(self) -> ClientResult[str]:
        """
        Get the currently authenticated GitHub username.

        Returns:
            ClientResult[str] with GitHub username
        """
        try:
            output = self._gh_network.run_command(["api", "user", "-q", ".login"])
            username = output.strip()
            return ClientSuccess(data=username, message="Current user retrieved")
        except Exception as e:
            return ClientError(
                error_message=f"Failed to get current user: {e}",
                error_code="API_ERROR"
            )

    def get_user_display_name(self, login: str) -> ClientResult[str]:
        """
        Get the display name of any GitHub user by login.

        Returns the full name if configured, falls back to the login.

        Args:
            login: GitHub username (login)

        Returns:
            ClientResult[str] with display name (e.g. "Alex García" or "finxo")
        """
        try:
            output = self._gh_network.run_command(["api", f"users/{login}", "-q", ".name // .login"])
            name = output.strip()
            return ClientSuccess(data=name, message="User display name retrieved")
        except Exception as e:
            return ClientError(
                error_message=f"Failed to get display name for {login}: {e}",
                error_code="API_ERROR"
            )

    def get_current_user_display_name(self) -> ClientResult[str]:
        """
        Get the display name of the authenticated GitHub user.

        Returns the full name if configured, falls back to the username login.

        Returns:
            ClientResult[str] with display name (e.g. "Alex García" or "finxo")
        """
        try:
            output = self._gh_network.run_command(["api", "user", "-q", ".name // .login"])
            name = output.strip()
            return ClientSuccess(data=name, message="Current user display name retrieved")
        except Exception as e:
            return ClientError(
                error_message=f"Failed to get current user display name: {e}",
                error_code="API_ERROR"
            )

    def get_default_branch(self) -> ClientResult[str]:
        """
        Get the default branch for the repository.

        Checks in order:
        1. Project config (.titan/config.toml -> github.default_branch)
        2. GitHub repository default branch (via API)
        3. Fallback to git client's main_branch

        Returns:
            ClientResult[str] with default branch name (e.g., "main", "develop", "master")
        """
        # Try to get from project config first
        if self.config.default_branch:
            return ClientSuccess(
                data=self.config.default_branch,
                message=f"Default branch from config: {self.config.default_branch}"
            )

        # Fallback to GitHub API
        try:
            args = ["repo", "view", "--json", "defaultBranchRef"] + self._gh_network.get_repo_arg()
            output = self._gh_network.run_command(args)
            data = json.loads(output)

            default_branch_ref = data.get("defaultBranchRef", {})
            branch_name = default_branch_ref.get("name")

            if branch_name:
                return ClientSuccess(
                    data=branch_name,
                    message=f"Default branch from GitHub API: {branch_name}"
                )
        except Exception:
            pass

        # Final fallback: use git plugin's main_branch
        fallback_branch = self.git_client.main_branch
        return ClientSuccess(
            data=fallback_branch,
            message=f"Default branch from git client: {fallback_branch}"
        )
