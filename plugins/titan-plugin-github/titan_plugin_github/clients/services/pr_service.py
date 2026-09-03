# plugins/titan-plugin-github/titan_plugin_github/clients/services/pr_service.py
"""
Pull Request Service

Business logic for PR operations.
Uses network layer to fetch data, parses to network models, maps to view models.
"""
import json
import re
from typing import List, Optional

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation
from titan_cli.core.logging.config import get_logger

from ..network import GHNetwork, GraphQLNetwork, graphql_queries
from ...models.network.rest import NetworkPullRequest, NetworkPRMergeResult, NetworkPRFile, NetworkPRCreated
from ...models.network.graphql import GraphQLPullRequestMergeQueueState
from ...models.review_models import ReferencedCommitContext
from ...models.view import UIPullRequest, UIPRMergeResult, UIMergeQueueState, UIFileChange, UIPRCreated
from ...models.mappers import (
    from_rest_pr,
    from_network_pr_merge_result,
    from_graphql_merge_queue_state,
    from_network_pr_file,
    from_network_pr_created,
)
from ...exceptions import GitHubAPIError
from ...messages import msg


class PRService:
    """
    Service for pull request operations.

    Handles fetching, creating, merging, and listing PRs.
    Returns view models ready for UI rendering.
    """

    def __init__(self, gh_network: GHNetwork, graphql_network: Optional[GraphQLNetwork] = None):
        """
        Initialize PR service.

        Args:
            gh_network: GHNetwork instance for REST operations
            graphql_network: GraphQLNetwork instance, required only for the merge
                queue fields the gh CLI does not expose. Without it, merge queue
                lookups fail and merges behave as if no queue existed.
        """
        self.gh = gh_network
        self.graphql = graphql_network
        self._logger = get_logger(__name__)

    @log_client_operation()
    def get_pull_request(self, pr_number: int) -> ClientResult[UIPullRequest]:
        """
        Get a pull request by number.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[UIPullRequest]
        """
        try:
            # Define fields to fetch
            fields = [
                "number", "title", "body", "state", "author",
                "baseRefName", "headRefName", "additions", "deletions",
                "changedFiles", "mergeable", "isDraft", "createdAt",
                "updatedAt", "mergedAt", "reviews", "labels",
                "statusCheckRollup", "reviewDecision", "reviewRequests",
                "isCrossRepository", "headRepositoryOwner", "headRepository",
            ]

            # Fetch from network
            args = [
                "pr", "view", str(pr_number),
                "--json", ",".join(fields),
            ] + self.gh.get_repo_arg()

            output = self.gh.run_command(args)
            data = json.loads(output)

            # Parse to network model
            rest_pr = NetworkPullRequest.from_json(data)

            # Map to view model
            ui_pr = from_rest_pr(rest_pr)

            return ClientSuccess(data=ui_pr, message=f"PR #{pr_number} retrieved")

        except json.JSONDecodeError as e:
            return ClientError(
                error_message=f"Failed to parse PR data: {e}",
                error_code="JSON_PARSE_ERROR"
            )
        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                return ClientError(
                    error_message=msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number),
                    error_code="PR_NOT_FOUND",
                    log_level="warning"
                )
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def list_pending_review_prs(
        self, max_results: int = 50, include_team_reviews: bool = False
    ) -> ClientResult[List[UIPullRequest]]:
        """
        List PRs pending your review.

        Args:
            max_results: Maximum number of results
            include_team_reviews: If True, includes PRs where only your team is requested

        Returns:
            ClientResult[List[UIPullRequest]]
        """
        try:
            # Get current user
            user_output = self.gh.run_command(["api", "user", "--jq", ".login"])
            current_user = user_output.strip()

            # Fetch PRs
            args = [
                "pr", "list",
                "--search", f"review-requested:{current_user}",
                "--state", "open",
                "--limit", str(max_results),
                "--json", "number,title,author,updatedAt,labels,isDraft,reviewRequests,statusCheckRollup,reviewDecision",
            ] + self.gh.get_repo_arg()

            output = self.gh.run_command(args)
            all_prs = json.loads(output)

            # Filter if needed
            if not include_team_reviews:
                filtered_prs = []
                for pr_data in all_prs:
                    review_requests = pr_data.get("reviewRequests", [])
                    if any(req and req.get("login") == current_user for req in review_requests):
                        filtered_prs.append(pr_data)
                all_prs = filtered_prs

            # Parse to network models then map to view models
            ui_prs = []
            for pr_data in all_prs:
                rest_pr = NetworkPullRequest.from_json(pr_data)
                ui_pr = from_rest_pr(rest_pr)
                ui_prs.append(ui_pr)

            return ClientSuccess(
                data=ui_prs,
                message=f"Found {len(ui_prs)} PRs pending review"
            )

        except json.JSONDecodeError as e:
            return ClientError(
                error_message=f"Failed to parse PR list: {e}",
                error_code="JSON_PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def list_my_prs(self, state: str = "open", max_results: int = 50) -> ClientResult[List[UIPullRequest]]:
        """
        List your PRs.

        Args:
            state: PR state (open, closed, merged, all)
            max_results: Maximum number of results

        Returns:
            ClientResult[List[UIPullRequest]]
        """
        try:
            # Get current user
            user_output = self.gh.run_command(["api", "user", "--jq", ".login"])
            current_user = user_output.strip()

            # Fetch PRs
            args = [
                "pr", "list",
                "--state", state,
                "--limit", str(max_results),
                "--json", "number,title,author,updatedAt,labels,isDraft,state,headRefName,baseRefName,statusCheckRollup,reviewDecision",
            ] + self.gh.get_repo_arg()

            output = self.gh.run_command(args)
            all_prs = json.loads(output)

            # Filter to current user's PRs
            my_prs = [
                pr for pr in all_prs
                if pr.get("author") and pr["author"].get("login") == current_user
            ]

            # Parse and map
            ui_prs = []
            for pr_data in my_prs:
                rest_pr = NetworkPullRequest.from_json(pr_data)
                ui_pr = from_rest_pr(rest_pr)
                ui_prs.append(ui_pr)

            return ClientSuccess(
                data=ui_prs,
                message=f"Found {len(ui_prs)} PRs"
            )

        except json.JSONDecodeError as e:
            return ClientError(
                error_message=f"Failed to parse PR list: {e}",
                error_code="JSON_PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def list_all_prs(self, state: str = "open", max_results: int = 50) -> ClientResult[List[UIPullRequest]]:
        """
        List all PRs in the repository.

        Args:
            state: PR state (open, closed, merged, all)
            max_results: Maximum number of results

        Returns:
            ClientResult[List[UIPullRequest]]
        """
        try:
            args = [
                "pr", "list",
                "--state", state,
                "--limit", str(max_results),
                "--json", "number,title,author,updatedAt,labels,isDraft,state,reviewRequests,headRefName,baseRefName,statusCheckRollup,reviewDecision",
            ] + self.gh.get_repo_arg()

            output = self.gh.run_command(args)
            all_prs = json.loads(output)

            # Parse and map
            ui_prs = []
            for pr_data in all_prs:
                rest_pr = NetworkPullRequest.from_json(pr_data)
                ui_pr = from_rest_pr(rest_pr)
                ui_prs.append(ui_pr)

            return ClientSuccess(
                data=ui_prs,
                message=f"Found {len(ui_prs)} PRs"
            )

        except json.JSONDecodeError as e:
            return ClientError(
                error_message=f"Failed to parse PR list: {e}",
                error_code="JSON_PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def get_pr_diff(self, pr_number: int, context_lines: int = 3) -> ClientResult[str]:
        """
        Get diff for a PR.

        Args:
            pr_number: PR number
            context_lines: Number of unchanged context lines (for future use with git diff)

        Returns:
            ClientResult[str] with diff content

        Note:
            Currently uses 'gh pr diff' which doesn't support custom context lines.
            The context_lines parameter is reserved for future implementation using git diff.
        """
        try:
            args = ["pr", "diff", str(pr_number)] + self.gh.get_repo_arg()
            diff = self.gh.run_command(args, strip_output=False)
            return ClientSuccess(data=diff, message=f"PR #{pr_number} diff retrieved")

        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                return ClientError(
                    error_message=msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number),
                    error_code="PR_NOT_FOUND",
                    log_level="warning"
                )
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def get_pr_files(self, pr_number: int) -> ClientResult[List[str]]:
        """
        Get list of changed files in PR.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[List[str]] with file paths
        """
        try:
            args = [
                "pr", "view", str(pr_number),
                "--json", "files",
            ] + self.gh.get_repo_arg()

            output = self.gh.run_command(args)
            data = json.loads(output)

            files = [f["path"] for f in data.get("files", [])]
            return ClientSuccess(
                data=files,
                message=f"Found {len(files)} changed files"
            )

        except json.JSONDecodeError as e:
            return ClientError(
                error_message=f"Failed to parse files: {e}",
                error_code="JSON_PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def get_pr_files_with_stats(self, pr_number: int) -> ClientResult[List[UIFileChange]]:
        """
        Get all changed files with stats for a PR.

        Fetches stats for every file without loading patch content.
        Suitable for AI-based file selection on large PRs.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[List[UIFileChange]] with path, additions, deletions, status
        """
        try:
            repo = self.gh.get_repo_string()
            all_files = []
            page = 1

            while True:
                args = [
                    "api",
                    f"/repos/{repo}/pulls/{pr_number}/files?per_page=100&page={page}",
                ]
                output = self.gh.run_command(args)
                files_data = json.loads(output)

                if not files_data:
                    break

                for f in files_data:
                    network_file = NetworkPRFile.from_json(f)
                    all_files.append(from_network_pr_file(network_file))

                if len(files_data) < 100:
                    break

                page += 1

            return ClientSuccess(
                data=all_files,
                message=f"Found {len(all_files)} changed files with stats"
            )

        except json.JSONDecodeError as e:
            return ClientError(
                error_message=f"Failed to parse files: {e}",
                error_code="JSON_PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def get_pr_file_patches(
        self, pr_number: int, file_paths: List[str]
    ) -> ClientResult[str]:
        """
        Get patches for specific files in a PR using the files REST API.

        Used as fallback when the full PR diff is too large. The files API
        returns individual file patches even for very large PRs.

        Args:
            pr_number: PR number
            file_paths: List of file paths to retrieve patches for

        Returns:
            ClientResult[str] with combined unified diff for the requested files
        """
        try:
            repo = self.gh.get_repo_string()
            target_files = set(file_paths)
            patches = []
            page = 1

            while target_files:
                args = [
                    "api",
                    f"/repos/{repo}/pulls/{pr_number}/files?per_page=100&page={page}",
                ]
                output = self.gh.run_command(args)
                files_data = json.loads(output)

                if not files_data:
                    break

                for file_data in files_data:
                    filename = file_data.get("filename", "")
                    patch = file_data.get("patch", "")
                    if filename in target_files and patch:
                        patches.append(
                            f"diff --git a/{filename} b/{filename}\n"
                            f"--- a/{filename}\n"
                            f"+++ b/{filename}\n"
                            f"{patch}"
                        )
                        target_files.discard(filename)

                page += 1

            if not patches:
                return ClientError(
                    error_message="No patches found for selected files",
                    error_code="NO_PATCHES"
                )

            return ClientSuccess(
                data="\n".join(patches),
                message=f"Got patches for {len(patches)} file(s)"
            )

        except (json.JSONDecodeError, KeyError) as e:
            return ClientError(
                error_message=f"Failed to parse file patches: {e}",
                error_code="JSON_PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def checkout_pr(self, pr_number: int) -> ClientResult[str]:
        """
        Checkout a PR locally.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[str] with branch name that was checked out
        """
        try:
            # Get PR to extract branch name
            pr_result = self.get_pull_request(pr_number)

            match pr_result:
                case ClientSuccess(data=ui_pr):
                    # Checkout using gh CLI
                    args = ["pr", "checkout", str(pr_number)] + self.gh.get_repo_arg()
                    self.gh.run_command(args)

                    # Extract head ref from branch_info (format: "head → base")
                    head_ref = ui_pr.branch_info.split(" → ")[0]
                    return ClientSuccess(
                        data=head_ref,
                        message=f"Checked out PR #{pr_number} to branch {head_ref}"
                    )
                case ClientError() as err:
                    return err

        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                return ClientError(
                    error_message=msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number),
                    error_code="PR_NOT_FOUND",
                    log_level="warning"
                )
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
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
    ) -> ClientResult[UIPRCreated]:
        """
        Create a pull request.

        Args:
            title: PR title
            body: PR description
            base: Base branch
            head: Head branch
            draft: Whether to create as draft
            assignees: List of assignees
            reviewers: List of reviewers
            labels: List of labels

        Returns:
            ClientResult[UIPRCreated] with number, url, state
        """
        try:
            args = [
                "pr", "create",
                "--base", base,
                "--head", head,
                "--title", title,
                "--body", body,
            ]

            if draft:
                args.append("--draft")

            if assignees:
                for assignee in assignees:
                    args.extend(["--assignee", assignee])

            if reviewers:
                for reviewer in reviewers:
                    args.extend(["--reviewer", reviewer])

            if labels:
                for label in labels:
                    args.extend(["--label", label])

            args.extend(self.gh.get_repo_arg())

            # Execute and get PR URL
            output = self.gh.run_command(args)
            pr_url = output.strip()

            # Extract PR number from URL
            try:
                pr_number = int(pr_url.split("/")[-1])
            except ValueError:
                return ClientError(
                    error_message=msg.GitHub.FAILED_TO_PARSE_PR_NUMBER.format(url=output),
                    error_code="PARSE_ERROR"
                )

            network_created = NetworkPRCreated(
                number=pr_number,
                url=pr_url,
                state="draft" if draft else "open",
            )
            return ClientSuccess(
                data=from_network_pr_created(network_created),
                message=f"PR #{pr_number} created"
            )

        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def merge_pr(
        self,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_queue_enabled: Optional[bool] = None,
    ) -> ClientResult[UIPRMergeResult]:
        """
        Merge a pull request, or add it to the base branch's merge queue.

        When the base branch requires a merge queue, GitHub decides the merge
        strategy and merges later: `gh pr merge` is run without a strategy flag and
        the result is reported as queued (`queued=True`, `merged=False`), never as a
        merge. Otherwise the requested merge method is used and the PR is merged now.

        Args:
            pr_number: PR number
            merge_method: Merge method (squash, merge, rebase). Ignored when the base
                branch requires a merge queue.
            commit_title: Optional commit title. Ignored for a queued merge.
            commit_message: Optional commit message. Ignored for a queued merge.
            merge_queue_enabled: Known merge queue state, to avoid a second lookup.
                When None, it is detected here; a failed detection falls back to a
                regular merge.

        Returns:
            ClientResult[UIPRMergeResult]
        """
        try:
            # Validate merge method
            valid_methods = ["squash", "merge", "rebase"]
            if merge_method not in valid_methods:
                network_result = NetworkPRMergeResult(
                    merged=False,
                    message=msg.GitHub.INVALID_MERGE_METHOD.format(
                        method=merge_method, valid_methods=", ".join(valid_methods)
                    ),
                )
                ui_result = from_network_pr_merge_result(network_result)
                return ClientSuccess(data=ui_result, message="Invalid merge method")

            if merge_queue_enabled is None:
                merge_queue_enabled = self._detect_merge_queue_enabled(pr_number)

            if merge_queue_enabled:
                return self._enqueue_pr(pr_number)

            # Build command
            args = ["pr", "merge", str(pr_number), f"--{merge_method}"]

            if commit_title:
                args.extend(["--subject", commit_title])

            if commit_message:
                args.extend(["--body", commit_message])

            args.extend(self.gh.get_repo_arg())

            # Execute merge
            result = self.gh.run_command(args)

            # Extract SHA from output
            sha = None
            if result:
                sha_match = re.search(r"\(([a-f0-9]{7,40})\)", result)
                if sha_match:
                    sha = sha_match.group(1)

            network_result = NetworkPRMergeResult(
                merged=True,
                sha=sha,
                message="Successfully merged"
            )
            ui_result = from_network_pr_merge_result(network_result)
            return ClientSuccess(data=ui_result, message=f"PR #{pr_number} merged")

        except GitHubAPIError as e:
            network_result = NetworkPRMergeResult(merged=False, message=str(e))
            ui_result = from_network_pr_merge_result(network_result)
            return ClientSuccess(data=ui_result, message="Merge failed")

    def _detect_merge_queue_enabled(self, pr_number: int) -> bool:
        """
        Check whether the PR's base branch requires a merge queue.

        A failed detection is not an error: it returns False so the caller merges the
        way it always did instead of blocking on a lookup.

        Args:
            pr_number: PR number

        Returns:
            True when the base branch requires a merge queue
        """
        match self.get_merge_queue_state(pr_number):
            case ClientSuccess(data=queue_state):
                return queue_state.is_merge_queue_enabled
            case ClientError(error_message=err):
                self._logger.warning(
                    "Merge queue detection failed for PR #%s, assuming no merge queue: %s",
                    pr_number,
                    err,
                )
                return False

    def _enqueue_pr(self, pr_number: int) -> ClientResult[UIPRMergeResult]:
        """
        Add a pull request to its base branch's merge queue.

        No strategy flag is passed: with a merge queue the strategy belongs to the
        queue configuration, and gh warns and ignores it when given one.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[UIPRMergeResult] with queued=True on success
        """
        args = ["pr", "merge", str(pr_number)] + self.gh.get_repo_arg()

        try:
            self.gh.run_command(args)
        except GitHubAPIError as e:
            network_result = NetworkPRMergeResult(merged=False, message=str(e))
            ui_result = from_network_pr_merge_result(network_result)
            return ClientSuccess(data=ui_result, message="Merge queue request failed")

        # Read back the position, when GitHub already has an entry for the PR
        queue_position = None
        match self.get_merge_queue_state(pr_number):
            case ClientSuccess(data=queue_state):
                queue_position = queue_state.queue_position
            case ClientError():
                pass

        network_result = NetworkPRMergeResult(
            merged=False,
            queued=True,
            queue_position=queue_position,
            message=f"PR #{pr_number} added to the merge queue",
        )
        ui_result = from_network_pr_merge_result(network_result)
        return ClientSuccess(data=ui_result, message=f"PR #{pr_number} added to the merge queue")

    @log_client_operation()
    def get_merge_queue_state(self, pr_number: int) -> ClientResult[UIMergeQueueState]:
        """
        Get the merge queue state of a pull request.

        The gh CLI does not expose these fields through `pr view --json`, so this
        goes through GraphQL.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[UIMergeQueueState]
        """
        if not self.graphql:
            return ClientError(
                error_message="GraphQL network is not available for merge queue lookups",
                error_code="GRAPHQL_UNAVAILABLE",
                log_level="warning",
            )

        try:
            owner, repo = self.gh.get_repo_string().split('/')

            response = self.graphql.run_query(
                graphql_queries.GET_PR_MERGE_QUEUE_STATE,
                {"owner": owner, "repo": repo, "prNumber": pr_number},
            )

            pr_data = (
                response.get("data", {})
                .get("repository", {})
                .get("pullRequest")
            )

            if not pr_data:
                return ClientError(
                    error_message=msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number),
                    error_code="PR_NOT_FOUND",
                    log_level="warning",
                )

            graphql_state = GraphQLPullRequestMergeQueueState.from_graphql(pr_data)
            ui_state = from_graphql_merge_queue_state(graphql_state)

            return ClientSuccess(
                data=ui_state,
                message=f"PR #{pr_number} merge queue state retrieved",
            )

        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def add_comment(self, pr_number: int, body: str) -> ClientResult[None]:
        """
        Add a comment to a PR.

        Args:
            pr_number: PR number
            body: Comment text

        Returns:
            ClientResult[None]
        """
        try:
            args = [
                "pr", "comment", str(pr_number),
                "--body", body,
            ] + self.gh.get_repo_arg()

            self.gh.run_command(args)
            return ClientSuccess(data=None, message=f"Comment added to PR #{pr_number}")

        except GitHubAPIError as e:
            if "not found" in str(e).lower():
                return ClientError(
                    error_message=msg.GitHub.PR_NOT_FOUND.format(pr_number=pr_number),
                    error_code="PR_NOT_FOUND",
                    log_level="warning"
                )
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def get_pr_commit_sha(self, pr_number: int) -> ClientResult[str]:
        """
        Get the head commit SHA for a PR.

        Reads `headRefOid` rather than the last entry of the `commits` list: gh caps
        that list at 100 entries, so on a PR with more commits the "last" one is the
        100th, not the head. Inline comments anchored to it are rejected with
        "Path could not be resolved" for files that did not exist yet, and the ones
        GitHub accepts are published already outdated.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[str] with the head commit SHA
        """
        try:
            args = [
                "pr", "view", str(pr_number),
                "--json", "headRefOid",
            ] + self.gh.get_repo_arg()

            output = self.gh.run_command(args)
            data = json.loads(output)
            sha = (data.get("headRefOid") or "").strip()

            if not sha:
                return ClientError(
                    error_message=f"No head commit SHA found for PR #{pr_number}",
                    error_code="NO_COMMITS"
                )

            return ClientSuccess(data=sha, message="Head commit SHA retrieved")

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            return ClientError(
                error_message=f"Failed to get commit SHA: {e}",
                error_code="PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def get_commit_review_context(
        self,
        commit_ref: str,
        *,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        max_files: int = 3,
        max_patch_chars: int = 4000,
    ) -> ClientResult[ReferencedCommitContext]:
        """Get a compact review context for a referenced commit.

        Defaults to the configured base repo. Pass `repo_owner`/`repo_name`
        (e.g. a PR's head repository) to resolve commits that only exist on
        a fork, such as SHAs mentioned in review replies on cross-repo PRs.
        """
        repo_string = (
            f"{repo_owner}/{repo_name}"
            if repo_owner and repo_name
            else self.gh.get_repo_string()
        )
        try:
            output = self.gh.run_command(
                ["api", f"repos/{repo_string}/commits/{commit_ref}"]
            )
            data = json.loads(output)

            sha = str(data["sha"])
            commit_message = self._truncate_text(
                str(data.get("commit", {}).get("message", "")).strip(),
                600,
            )
            files = data.get("files", [])
            changed_files: list[str] = []
            patch_sections: list[str] = []

            for file_data in files[:max_files]:
                filename = str(file_data.get("filename", "")).strip()
                if not filename:
                    continue

                changed_files.append(filename)

                patch = file_data.get("patch")
                if not patch:
                    continue

                status = str(file_data.get("status", "modified")).strip()
                previous_filename = str(file_data.get("previous_filename") or "").strip()

                if status == "added":
                    old_path, new_path = "/dev/null", filename
                elif status == "removed":
                    old_path, new_path = filename, "/dev/null"
                elif status == "renamed" and previous_filename:
                    old_path, new_path = previous_filename, filename
                else:
                    old_path, new_path = filename, filename

                patch_sections.append(
                    f"diff --git a/{old_path} b/{new_path}\n"
                    f"# status: {status}\n"
                    f"{patch.strip()}"
                )

            patch_excerpt = "\n\n".join(patch_sections).strip() or None
            if patch_excerpt:
                patch_excerpt = self._truncate_text(patch_excerpt, max_patch_chars)

            return ClientSuccess(
                data=ReferencedCommitContext(
                    sha=sha,
                    abbreviated_sha=sha[:7],
                    message=commit_message,
                    changed_files=changed_files,
                    patch_excerpt=patch_excerpt,
                ),
                message=f"Commit context retrieved for {sha[:7]}",
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            return ClientError(
                error_message=f"Failed to parse commit context: {e}",
                error_code="PARSE_ERROR",
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        """Trim large gh payload sections without hiding that they were truncated."""
        if len(text) <= max_chars:
            return text
        suffix = "\n... [truncated]"
        return text[: max_chars - len(suffix)].rstrip() + suffix
