# plugins/titan-plugin-github/titan_plugin_github/clients/github_client.py
"""
GitHub Client

Python client for GitHub operations using gh CLI.
"""

import json
import subprocess
import re
from typing import List, Optional, Dict, Any

from titan_cli.core.secrets import SecretManager
from titan_cli.core.plugins.models import GitHubPluginConfig
from titan_plugin_git.clients.git_client import GitClient

from ..models import (
    PullRequest,
    Review,
    PRSearchResult,
    PRMergeResult,
    PRComment as GitHubPRComment,
)
from ..exceptions import (
    GitHubError,
    GitHubAuthenticationError,
    PRNotFoundError,
    GitHubAPIError,
)
from ..messages import msg


class GitHubClient:
    """
    GitHub client using gh CLI

    This client wraps gh CLI commands and provides a Pythonic interface
    for GitHub operations.

    Examples:
        >>> config = GitHubPluginConfig()
        >>> client = GitHubClient(config)
        >>> pr = client.get_pull_request(123)
        >>> print(pr.title)
    """

    def __init__(
        self,
        config: GitHubPluginConfig,
        secrets: SecretManager,
        git_client: GitClient,
        repo_owner: str,
        repo_name: str
    ):
        """
        Initialize GitHub client

        Args:
            config: GitHub configuration
            secrets: SecretManager instance
            git_client: Initialized GitClient instance
            repo_owner: GitHub repository owner.
            repo_name: GitHub repository name.

        Raises:
            GitHubAuthenticationError: If gh CLI is not authenticated
        """
        self.config = config
        self.secrets = secrets
        self.git_client = git_client
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self._check_auth()

    def _check_auth(self) -> None:
        """
        Check if gh CLI is authenticated

        Raises:
            GitHubAuthenticationError: If not authenticated
        """
        try:
            subprocess.run(["gh", "auth", "status"], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            raise GitHubAuthenticationError(msg.GitHub.NOT_AUTHENTICATED)

    def _run_gh_command(
        self, args: List[str], stdin_input: Optional[str] = None
    ) -> str:
        """
        Run gh CLI command and return stdout

        Args:
            args: Command arguments (without 'gh' prefix)
            stdin_input: Optional input to pass via stdin (for multiline text)

        Returns:
            Command stdout as string

        Raises:
            GitHubAPIError: If command fails
        """
        try:
            result = subprocess.run(
                ["gh"] + args,
                input=stdin_input,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            raise GitHubAPIError(msg.GitHub.API_ERROR.format(error_msg=error_msg))
        except FileNotFoundError:
            raise GitHubError(msg.GitHub.CLI_NOT_FOUND)
        except Exception as e:
            raise GitHubError(msg.GitHub.UNEXPECTED_ERROR.format(error=e))

    def _get_repo_arg(self) -> List[str]:
        """Get --repo argument for gh commands"""
        if self.repo_owner and self.repo_name:
            return ["--repo", f"{self.repo_owner}/{self.repo_name}"]
        return []

    def _get_repo_string(self) -> str:
        """Get repo string in format 'owner/repo'"""
        return f"{self.repo_owner}/{self.repo_name}"

    def get_pull_request(self, pr_number: int) -> PullRequest:
        """
        Get pull request by number

        Args:
            pr_number: PR number

        Returns:
            PullRequest instance

        Raises:
            PRNotFoundError: If PR doesn't exist
            GitHubAPIError: If API call fails

        Examples:
            >>> pr = client.get_pull_request(123)
            >>> print(pr.title, pr.state)
        """
        try:
            # Get PR with all relevant fields
            fields = [
                "number",
                "title",
                "body",
                "state",
                "author",
                "baseRefName",
                "headRefName",
                "additions",
                "deletions",
                "changedFiles",
                "mergeable",
                "isDraft",
                "createdAt",
                "updatedAt",
                "mergedAt",
                "reviews",
                "labels",
            ]

            args = [
                "pr",
                "view",
                str(pr_number),
                "--json",
                ",".join(fields),
            ] + self._get_repo_arg()

            output = self._run_gh_command(args)
            data = json.loads(output)

            return PullRequest.from_dict(data)

        except json.JSONDecodeError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to parse PR data: {e}"
                )
            )
        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                raise PRNotFoundError(
                    msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number)
                )
            raise

    def get_default_branch(self) -> str:
        """
        Get the default branch (base branch) for the repository

        Checks in order:
        1. Project config (.titan/config.toml -> github.default_branch)
        2. GitHub repository default branch (via API)
        3. Fallback to "develop"

        Returns:
            Default branch name (e.g., "main", "develop", "master")

        Examples:
            >>> # If config has github.default_branch = "develop"
            >>> client = GitHubClient(config)
            >>> branch = client.get_default_branch()
            >>> print(branch)  # "develop" (from config)

            >>> # If no config, consults GitHub API
            >>> client = GitHubClient(config)
            >>> branch = client.get_default_branch()
            >>> print(branch)  # "main" (from GitHub API)
        """
        # Try to get from project config first
        if self.config.default_branch:
            return self.config.default_branch

        # Fallback to GitHub API
        try:
            # Get repository info including default branch
            args = ["repo", "view", "--json", "defaultBranchRef"] + self._get_repo_arg()

            output = self._run_gh_command(args)
            data = json.loads(output)

            # Extract default branch name
            default_branch_ref = data.get("defaultBranchRef", {})
            branch_name = default_branch_ref.get("name")

            if branch_name:
                return branch_name

        except Exception as e:
            # Log this, but don't re-raise immediately, try final fallback
            pass

        # Final fallback: use git plugin's main_branch
        return self.git_client.main_branch

    def list_pending_review_prs(
        self, max_results: int = 50, include_team_reviews: bool = False
    ) -> PRSearchResult:
        """
        List PRs pending your review in the current repository

        Args:
            max_results: Maximum number of results
            include_team_reviews: If True, includes PRs where only your team is requested
                                 If False, only PRs where YOU are individually requested

        Returns:
            PRSearchResult with pending PRs

        Examples:
            >>> # Only PRs where you're individually assigned
            >>> result = client.list_pending_review_prs()
            >>> # PRs where you OR your team are assigned
            >>> result = client.list_pending_review_prs(include_team_reviews=True)
        """
        try:
            # Use 'gh pr list' instead of 'gh search prs' because:
            # - 'gh search prs' ignores --repo flag and searches across all repos
            # - 'gh pr list' respects current repo context

            # Get all PRs with review-requested: @me
            args = [
                "pr",
                "list",
                "--search",
                "review-requested: @me",
                "--state",
                "open",
                "--limit",
                str(max_results),
                "--json",
                "number,title,author,updatedAt,labels,isDraft,reviewRequests",
            ] + self._get_repo_arg()

            output = self._run_gh_command(args)
            all_prs = json.loads(output)

            if include_team_reviews:
                # Return all PRs (you individually OR your team)
                return PRSearchResult.from_list(all_prs)
            else:
                # Filter to only PRs where current user is explicitly in reviewRequests
                # Get current user to filter review requests
                user_output = self._run_gh_command(["api", "user", "--jq", ".login"])
                current_user = user_output.strip()

                filtered_prs = []
                for pr in all_prs:
                    review_requests = pr.get("reviewRequests", [])
                    # Check if current user is in the review requests
                    if any(
                        req and req.get("login") == current_user
                        for req in review_requests
                    ):
                        filtered_prs.append(pr)

                return PRSearchResult.from_list(filtered_prs)

        except json.JSONDecodeError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to parse search results: {e}"
                )
            )

    def list_my_prs(self, state: str = "open", max_results: int = 50) -> PRSearchResult:
        """
        List your PRs

        Args:
            state: PR state (open, closed, merged, all)
            max_results: Maximum number of results

        Returns:
            PRSearchResult with your PRs

        Examples:
            >>> result = client.list_my_prs(state="open")
            >>> print(f"You have {result.total} open PRs")
        """
        try:
            args = [
                "pr",
                "list",
                "--author",
                " @me",
                "--state",
                state,
                "--limit",
                str(max_results),
                "--json",
                "number,title,author,updatedAt,labels,isDraft,state",
            ] + self._get_repo_arg()

            output = self._run_gh_command(args)
            data = json.loads(output)

            return PRSearchResult.from_list(data)

        except json.JSONDecodeError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to parse PR list: {e}"
                )
            )

    def list_all_prs(
        self, state: str = "open", max_results: int = 50
    ) -> PRSearchResult:
        """
        List all PRs in the repository

        Args:
            state: PR state (open, closed, merged, all)
            max_results: Maximum number of results

        Returns:
            PRSearchResult with all PRs

        Examples:
            >>> result = client.list_all_prs(state="open")
            >>> print(f"Repository has {result.total} open PRs")
        """
        try:
            args = [
                "pr",
                "list",
                "--state",
                state,
                "--limit",
                str(max_results),
                "--json",
                "number,title,author,updatedAt,labels,isDraft,state,reviewRequests",
            ] + self._get_repo_arg()

            output = self._run_gh_command(args)
            data = json.loads(output)

            return PRSearchResult.from_list(data)

        except json.JSONDecodeError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to parse PR list: {e}"
                )
            )

    def get_pr_diff(self, pr_number: int, file_path: Optional[str] = None) -> str:
        """
        Get diff for a PR

        Args:
            pr_number: PR number
            file_path: Optional specific file to get diff for

        Returns:
            Diff as string

        Raises:
            PRNotFoundError: If PR doesn't exist

        Examples:
            >>> diff = client.get_pr_diff(123)
            >>> print(diff)
        """
        try:
            args = ["pr", "diff", str(pr_number)] + self._get_repo_arg()

            if file_path:
                args.append("--")
                args.append(file_path)

            return self._run_gh_command(args)

        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                raise PRNotFoundError(
                    msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number)
                )
            raise

    def get_pr_files(self, pr_number: int) -> List[str]:
        """
        Get list of changed files in PR

        Args:
            pr_number: PR number

        Returns:
            List of file paths

        Examples:
            >>> files = client.get_pr_files(123)
            >>> print(f"Changed {len(files)} files")
        """
        try:
            args = [
                "pr",
                "view",
                str(pr_number),
                "--json",
                "files",
            ] + self._get_repo_arg()

            output = self._run_gh_command(args)
            data = json.loads(output)

            return [f["path"] for f in data.get("files", [])]

        except json.JSONDecodeError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to parse files: {e}"
                )
            )

    def checkout_pr(self, pr_number: int) -> str:
        """
        Checkout a PR locally

        Args:
            pr_number: PR number

        Returns:
            Branch name that was checked out

        Raises:
            PRNotFoundError: If PR doesn't exist

        Examples:
            >>> branch = client.checkout_pr(123)
            >>> print(f"Checked out {branch}")
        """
        try:
            # Get PR branch name first
            pr = self.get_pull_request(pr_number)

            # Checkout the PR using gh CLI
            args = ["pr", "checkout", str(pr_number)] + self._get_repo_arg()
            self._run_gh_command(args)

            return pr.head_ref

        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                raise PRNotFoundError(
                    msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number)
                )
            raise

    def add_comment(self, pr_number: int, body: str) -> None:
        """
        Add comment to a PR

        Args:
            pr_number: PR number
            body: Comment text

        Raises:
            PRNotFoundError: If PR doesn't exist

        Examples:
            >>> client.add_comment(123, "LGTM!")
        """
        try:
            args = [
                "pr",
                "comment",
                str(pr_number),
                "--body",
                body,
            ] + self._get_repo_arg()

            self._run_gh_command(args)

        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                raise PRNotFoundError(
                    msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number)
                )
            raise

    def get_pr_commit_sha(self, pr_number: int) -> str:
        """
        Get the latest commit SHA for a PR

        Args:
            pr_number: PR number

        Returns:
            Latest commit SHA

        Examples:
            >>> sha = client.get_pr_commit_sha(123)
        """
        try:
            args = [
                "pr",
                "view",
                str(pr_number),
                "--json",
                "commits",
            ] + self._get_repo_arg()

            output = self._run_gh_command(args)
            data = json.loads(output)
            commits = data.get("commits", [])

            if not commits:
                raise GitHubAPIError(
                    msg.GitHub.API_ERROR.format(
                        error_msg=f"No commits found for PR #{pr_number}"
                    )
                )

            return commits[-1]["oid"]

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to get commit SHA: {e}"
                )
            )

    def get_pr_reviews(self, pr_number: int) -> List["Review"]:
        """
        Get all reviews for a PR

        Args:
            pr_number: PR number

        Returns:
            List of Review objects

        Examples:
            >>> reviews = client.get_pr_reviews(123)
            >>> approved = sum(1 for r in reviews if r.state == "APPROVED")
        """
        try:
            repo = self._get_repo_string()
            result = self._run_gh_command(
                ["api", f"/repos/{repo}/pulls/{pr_number}/reviews", "--jq", "."]
            )

            reviews_data = json.loads(result)
            return [Review.from_dict(r) for r in reviews_data]

        except (json.JSONDecodeError, KeyError) as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to get PR reviews: {e}"
                )
            )

    def create_draft_review(self, pr_number: int, payload: Dict[str, Any]) -> int:
        """
        Create a draft review on a PR

        Args:
            pr_number: PR number
            payload: Review payload with commit_id, body, event, comments

        Returns:
            Review ID

        Examples:
            >>> payload = {
            ...     "commit_id": "abc123",
            ...     "body": "",
            ...     "event": "PENDING",
            ...     "comments": [{"path": "file.kt", "line": 10, "body": "Nice"}]
            ... }
            >>> review_id = client.create_draft_review(123, payload)
        """
        try:
            repo = self._get_repo_string()
            args = [
                "api",
                f"/repos/{repo}/pulls/{pr_number}/reviews",
                "--method",
                "POST",
                "--input",
                "-",
            ]

            # Run gh command with JSON payload via stdin
            import subprocess

            result = subprocess.run(
                ["gh"] + args,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                check=True,
            )

            response = json.loads(result.stdout)
            return response["id"]

        except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError) as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to create draft review: {e}"
                )
            )

    def submit_review(
        self, pr_number: int, review_id: int, event: str, body: str = ""
    ) -> None:
        """
        Submit a review

        Args:
            pr_number: PR number
            review_id: Review ID
            event: Review event (APPROVE, REQUEST_CHANGES, COMMENT)
            body: Optional review body text

        Examples:
            >>> client.submit_review(123, 456, "APPROVE", "")
        """
        try:
            repo = self._get_repo_string()
            args = [
                "api",
                f"/repos/{repo}/pulls/{pr_number}/reviews/{review_id}/events",
                "--method",
                "POST",
                "-f",
                f"event={event}",
            ]

            if body:
                args.extend(["-f", f"body={body}"])

            self._run_gh_command(args)

        except GitHubAPIError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to submit review: {e}"
                )
            )

    def delete_review(self, pr_number: int, review_id: int) -> None:
        """
        Delete a draft review

        Args:
            pr_number: PR number
            review_id: Review ID

        Examples:
            >>> client.delete_review(123, 456)
        """
        try:
            repo = self._get_repo_string()
            args = [
                "api",
                f"/repos/{repo}/pulls/{pr_number}/reviews/{review_id}",
                "--method",
                "DELETE",
            ]

            self._run_gh_command(args)

        except GitHubAPIError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to delete review: {e}"
                )
            )

    def merge_pr(
        self,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> PRMergeResult:
        """
        Merge a pull request

        Args:
            pr_number: PR number
            merge_method: Merge method (squash, merge, rebase)
            commit_title: Optional commit title
            commit_message: Optional commit message

        Returns:
            PRMergeResult with merge status and SHA

        Examples:
            >>> result = client.merge_pr(123, merge_method="squash")
            >>> if result.merged:
            ...     print(f"Merged: {result.sha}")
        """
        try:
            # Validate merge method
            valid_methods = ["squash", "merge", "rebase"]
            if merge_method not in valid_methods:
                return PRMergeResult(
                    merged=False,
                    message=msg.GitHub.INVALID_MERGE_METHOD.format(
                        method=merge_method, valid_methods=", ".join(valid_methods)
                    ),
                )

            # Build command
            args = ["pr", "merge", str(pr_number), f"--{merge_method}"]

            if commit_title:
                args.extend(["--subject", commit_title])

            if commit_message:
                args.extend(["--body", commit_message])

            # Execute merge
            result = self._run_gh_command(args)

            # Parse result to get SHA
            # gh pr merge returns: "✓ Merged pull request #123 (SHA)"
            # Extract SHA from output
            sha = None
            if result:
                import re

                sha_match = re.search(r"\(([a-f0-9]{40})\)", result)
                if sha_match:
                    sha = sha_match.group(1)
                else:
                    # Try short SHA (7 chars)
                    sha_match = re.search(r"\(([a-f0-9]{7,})\)", result)
                    if sha_match:
                        sha = sha_match.group(1)

            return PRMergeResult(merged=True, sha=sha, message="Successfully merged")

        except GitHubAPIError as e:
            return PRMergeResult(merged=False, message=str(e))
        except Exception as e:
            return PRMergeResult(
                merged=False, message=msg.GitHub.UNEXPECTED_ERROR.format(error=e)
            )

    def get_current_user(self) -> str:
        """
        Get current authenticated user

        Returns:
            GitHub username

        Examples:
            >>> username = client.get_current_user()
            >>> print(f"Authenticated as {username}")
        """
        try:
            output = self._run_gh_command(["api", "user", "--jq", ".login"])
            return output.strip()
        except GitHubAPIError:
            return "unknown"

    def get_pr_comments(self, pr_number: int) -> List[GitHubPRComment]:
        """
        Get all comments for a PR (review comments + issue comments)

        Args:
            pr_number: PR number

        Returns:
            List of PRComment objects

        Examples:
            >>> comments = client.get_pr_comments(123)
            >>> for c in comments:
            ...     print(f"{c.user.login}: {c.body}")
        """
        try:
            repo = self._get_repo_string()

            # Get review comments (inline in files)
            args = ["api", f"/repos/{repo}/pulls/{pr_number}/comments", "--paginate"]
            output = self._run_gh_command(args)
            review_comments_data = json.loads(output) if output else []

            # Get issue comments (general comments)
            args = ["api", f"/repos/{repo}/issues/{pr_number}/comments", "--paginate"]
            output = self._run_gh_command(args)
            issue_comments_data = json.loads(output) if output else []

            # Convert to PRComment objects
            comments = []

            for data in review_comments_data:
                comments.append(GitHubPRComment.from_dict(data, is_review=True))

            for data in issue_comments_data:
                comments.append(GitHubPRComment.from_dict(data, is_review=False))

            return comments

        except (json.JSONDecodeError, GitHubAPIError) as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to get PR comments: {e}"
                )
            )

    def get_pending_comments(
        self, pr_number: int, author: Optional[str] = None
    ) -> List[GitHubPRComment]:
        """
        Get comments pending response from PR author

        Filters out comments already responded to by the author.

        Args:
            pr_number: PR number
            author: PR author username (if None, uses current user)

        Returns:
            List of PRComment objects that don't have author's response

        Examples:
            >>> pending = client.get_pending_comments(123)
            >>> print(f"{len(pending)} comments pending")
        """
        if author is None:
            author = self.get_current_user()

        all_comments = self.get_pr_comments(pr_number)

        # Build set of comment IDs that have author's response
        responded_ids = set()
        for comment in all_comments:
            if comment.in_reply_to_id and comment.user.login == author:
                responded_ids.add(comment.in_reply_to_id)

        # Filter to main comments (not replies) without author's response
        pending = []
        for comment in all_comments:
            is_main_comment = comment.in_reply_to_id is None
            not_from_author = comment.user.login != author
            not_responded = comment.id not in responded_ids

            if is_main_comment and not_from_author and not_responded:
                pending.append(comment)

        return pending

    def reply_to_comment(self, pr_number: int, comment_id: int, body: str) -> None:
        """
        Reply to a PR comment

        Args:
            pr_number: PR number
            comment_id: Comment ID to reply to
            body: Reply text

        Examples:
            >>> client.reply_to_comment(123, 456789, "Fixed in abc123")
        """
        try:
            repo = self._get_repo_string()
            # Use -F body= @docs/guides/creating-visual-components.md to read body from stdin
            # This properly handles multiline text, special characters, and code blocks
            args = [
                "api",
                "-X",
                "POST",
                f"/repos/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
                "-F",
                "body= @-",
            ]

            self._run_gh_command(args, stdin_input=body)

        except GitHubAPIError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to reply to comment: {e}"
                )
            )

    def add_issue_comment(self, pr_number: int, body: str) -> None:
        """
        Add a general comment to PR (issue comment)

        Args:
            pr_number: PR number
            body: Comment text

        Examples:
            >>> client.add_issue_comment(123, "Thanks for the review!")
        """
        try:
            repo = self._get_repo_string()
            # Use -F body= @docs/guides/creating-visual-components.md to read body from stdin
            # This properly handles multiline text, special characters, and code blocks
            args = [
                "api",
                "-X",
                "POST",
                f"/repos/{repo}/issues/{pr_number}/comments",
                "-F",
                "body= @-",
            ]

            self._run_gh_command(args, stdin_input=body)

        except GitHubAPIError as e:
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(
                    error_msg=f"Failed to add comment: {e}"
                )
            )

    def create_pull_request(
        self, title: str, body: str, base: str, head: str, draft: bool = False
    ) -> Dict[str, Any]:
        """
        Create a pull request

        Args:
            title: PR title
            body: PR description/body
            base: Base branch (e.g., "develop", "main")
            head: Head branch (feature branch)
            draft: Whether to create as draft PR

        Returns:
            Dict with PR information including:
            - number: PR number
            - url: PR URL
            - state: PR state

        Raises:
            GitHubAPIError: If PR creation fails

        Examples:
            >>> pr = client.create_pull_request(
            ...     title="feat: Add new feature",
            ...     body="Description of changes",
            ...     base="develop",
            ...     head="feat/new-feature"
            ... )
            >>> print(f"Created PR #{pr['number']}: {pr['url']}")
        """
        try:
            args = [
                "pr",
                "create",
                "--base",
                base,
                "--head",
                head,
                "--title",
                title,
                "--body",
                body,
            ]

            if draft:
                args.append("--draft")

            args.extend(self._get_repo_arg())

            # Run command and get PR URL
            output = self._run_gh_command(args)
            pr_url = output.strip()

            # Extract PR number from URL
            # URL format: https://github.com/owner/repo/pull/123
            pr_number = int(pr_url.split("/")[-1])

            return {
                "number": pr_number,
                "url": pr_url,
                "state": "draft" if draft else "open",
            }

        except ValueError as e:
            raise GitHubAPIError(
                msg.GitHub.FAILED_TO_PARSE_PR_NUMBER.format(url=pr_url)
            )
        except GitHubAPIError as e:
            raise GitHubAPIError(msg.GitHub.PR_CREATION_FAILED.format(error=e))
