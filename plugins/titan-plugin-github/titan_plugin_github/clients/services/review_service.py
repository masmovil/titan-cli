# plugins/titan-plugin-github/titan_plugin_github/clients/services/review_service.py
"""
Review Service

Business logic for PR review operations.
Uses GraphQL for complex operations (threads, comments, resolve).
"""
import json
from typing import List, Optional, Dict, Any

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation
from ..network import GHNetwork, GraphQLNetwork, graphql_queries
from ...models.network.rest import NetworkReview
from ...models.network.graphql import GraphQLPullRequestReviewThread, GraphQLIssueComment
from ...models.view import UICommentThread, UIReview
from ...models.mappers import from_graphql_review_thread, from_network_review
from ...exceptions import GitHubAPIError
from ...messages import msg


class ReviewService:
    """
    Service for PR review operations.

    Handles threads, comments, reviews, and resolutions.
    Uses GraphQL for complex nested data.
    """

    def __init__(self, gh_network: GHNetwork, graphql_network: GraphQLNetwork):
        """
        Initialize review service.

        Args:
            gh_network: GHNetwork instance for REST operations
            graphql_network: GraphQLNetwork instance for GraphQL operations
        """
        self.gh = gh_network
        self.graphql = graphql_network

    @log_client_operation()
    def get_pr_review_threads(
        self, pr_number: int, include_resolved: bool = True
    ) -> ClientResult[List[UICommentThread]]:
        """
        Get all review threads for a PR.

        Uses GraphQL to fetch structured threads with comments.

        Args:
            pr_number: PR number
            include_resolved: If False, exclude resolved threads

        Returns:
            ClientResult[List[UICommentThread]]
        """
        try:
            # Parse owner/repo
            repo_string = self.gh.get_repo_string()
            owner, repo = repo_string.split('/')

            # Execute GraphQL query
            variables = {
                "owner": owner,
                "repo": repo,
                "prNumber": pr_number
            }

            response = self.graphql.run_query(
                graphql_queries.GET_PR_REVIEW_THREADS,
                variables
            )

            # Extract threads from response
            threads_data = (
                response.get("data", {})
                .get("repository", {})
                .get("pullRequest", {})
                .get("reviewThreads", {})
                .get("nodes", [])
            )

            # Parse to network models
            graphql_threads = []
            for thread_data in threads_data:
                # Skip resolved if requested
                if not include_resolved and thread_data.get("isResolved", False):
                    continue

                thread = GraphQLPullRequestReviewThread.from_graphql(thread_data)
                graphql_threads.append(thread)

            # Map to view models
            ui_threads = [from_graphql_review_thread(t) for t in graphql_threads]

            return ClientSuccess(
                data=ui_threads,
                message=f"Found {len(ui_threads)} review threads"
            )

        except (KeyError, ValueError) as e:
            return ClientError(
                error_message=f"Failed to parse review threads: {e}",
                error_code="PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def get_pr_general_comments(
        self, pr_number: int
    ) -> ClientResult[List[UICommentThread]]:
        """
        Get general PR comments (not attached to code lines).

        Uses GraphQL to fetch top-level PR comments AND submitted review bodies
        (the summary text of a review — where findings without an inline anchor
        end up), wrapping each one as a pseudo-thread (thread_id = "general_{id}")
        for uniform rendering. Pending reviews and empty review bodies (plain
        approvals) are skipped.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[List[UICommentThread]]
        """
        try:
            repo_string = self.gh.get_repo_string()
            owner, repo = repo_string.split('/')

            variables = {
                "owner": owner,
                "repo": repo,
                "prNumber": pr_number
            }

            response = self.graphql.run_query(
                graphql_queries.GET_PR_ISSUE_COMMENTS,
                variables
            )

            pull_request = (
                response.get("data", {})
                .get("repository", {})
                .get("pullRequest", {})
            )
            comments_data = pull_request.get("comments", {}).get("nodes", [])
            # The query aliases submittedAt as createdAt/updatedAt, so review
            # nodes parse with the same network model as issue comments.
            reviews_data = [
                r for r in pull_request.get("reviews", {}).get("nodes", [])
                if (r.get("body") or "").strip() and r.get("state") != "PENDING"
            ]

            network_comments = [
                GraphQLIssueComment.from_graphql(c)
                for c in comments_data + reviews_data
            ]

            ui_threads = [
                UICommentThread.from_issue_comment(c) for c in network_comments
            ]

            return ClientSuccess(
                data=ui_threads,
                message=f"Found {len(ui_threads)} general comments"
            )

        except (KeyError, ValueError) as e:
            return ClientError(
                error_message=f"Failed to parse general comments: {e}",
                error_code="PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def resolve_review_thread(self, thread_node_id: str) -> ClientResult[None]:
        """
        Resolve a review thread.

        Args:
            thread_node_id: GraphQL node ID of the thread

        Returns:
            ClientResult[None]
        """
        try:
            variables = {"threadId": thread_node_id}
            self.graphql.run_mutation(
                graphql_queries.RESOLVE_REVIEW_THREAD,
                variables
            )

            return ClientSuccess(data=None, message="Review thread resolved")

        except GitHubAPIError as e:
            return ClientError(
                error_message=f"Failed to resolve review thread: {e}",
                error_code="API_ERROR"
            )


    @log_client_operation()
    def get_pr_reviews(self, pr_number: int) -> ClientResult[List[UIReview]]:
        """
        Get all reviews for a PR.

        Args:
            pr_number: PR number

        Returns:
            ClientResult[List[UIReview]]
        """
        try:
            repo = self.gh.get_repo_string()
            result = self.gh.run_command(
                ["api", f"/repos/{repo}/pulls/{pr_number}/reviews", "--jq", "."]
            )

            reviews_data = json.loads(result)
            network_reviews = [NetworkReview.from_json(r) for r in reviews_data]

            # Map to UI models
            ui_reviews = [from_network_review(r) for r in network_reviews]

            return ClientSuccess(
                data=ui_reviews,
                message=f"Found {len(ui_reviews)} reviews"
            )

        except (json.JSONDecodeError, KeyError) as e:
            return ClientError(
                error_message=f"Failed to get PR reviews: {e}",
                error_code="PARSE_ERROR"
            )
        except GitHubAPIError as e:
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def create_draft_review(
        self, pr_number: int, payload: Dict[str, Any]
    ) -> ClientResult[int]:
        """
        Create a draft review on a PR.

        Args:
            pr_number: PR number
            payload: Review payload with commit_id, body, event, comments

        Returns:
            ClientResult[int] with review ID
        """
        try:
            repo = self.gh.get_repo_string()
            args = [
                "api",
                f"/repos/{repo}/pulls/{pr_number}/reviews",
                "--method", "POST",
                "--input", "-",
            ]

            payload_json = json.dumps(payload)
            import logging as _logging
            _logging.getLogger(__name__).debug(f"create_draft_review payload: {payload_json}")
            result = self.gh.run_command(args, stdin_input=payload_json)

            response = json.loads(result)
            review_id = response["id"]

            return ClientSuccess(
                data=review_id,
                message=f"Draft review #{review_id} created"
            )

        except (json.JSONDecodeError, KeyError) as e:
            return ClientError(
                error_message=f"Failed to parse review response: {e}",
                error_code="PARSE_ERROR"
            )
        except GitHubAPIError as e:
            details = []
            if getattr(e, "stderr", None):
                details.append(f"stderr={e.stderr}")
            if getattr(e, "stdout", None):
                details.append(f"stdout={e.stdout}")
            suffix = f" ({'; '.join(details)})" if details else ""
            return ClientError(error_message=f"{e}{suffix}", error_code="API_ERROR")

    @log_client_operation()
    def submit_review(
        self, pr_number: int, review_id: int | None, event: str, body: str = ""
    ) -> ClientResult[None]:
        """
        Submit a review.

        If review_id is None, creates a review directly with the event.
        If review_id is provided, submits the pending review with the event.

        Args:
            pr_number: PR number
            review_id: Review ID (or None to create directly)
            event: Review event (APPROVE, REQUEST_CHANGES, COMMENT)
            body: Optional review body text

        Returns:
            ClientResult[None]
        """
        try:
            repo = self.gh.get_repo_string()

            # If no review_id, create review directly with event
            if review_id is None:
                args = [
                    "api",
                    f"/repos/{repo}/pulls/{pr_number}/reviews",
                    "--method", "POST",
                    "-f", f"event={event}",
                ]

                if body:
                    args.extend(["-f", f"body={body}"])

                self.gh.run_command(args)
                return ClientSuccess(data=None, message=f"Review submitted with event {event}")

            # Otherwise, submit pending review with event
            args = [
                "api",
                f"/repos/{repo}/pulls/{pr_number}/reviews/{review_id}/events",
                "--method", "POST",
                "-f", f"event={event}",
            ]

            if body:
                args.extend(["-f", f"body={body}"])

            self.gh.run_command(args)

            return ClientSuccess(data=None, message=f"Review #{review_id} submitted")

        except GitHubAPIError as e:
            if "User can only have one pending review per pull request" in str(e):
                return ClientError(
                    error_message=msg.GitHub.REVIEW_PENDING_EXISTS,
                    error_code="PENDING_REVIEW_EXISTS",
                    log_level="warning",
                )
            return ClientError(
                error_message=f"Failed to submit review: {e}",
                error_code="API_ERROR"
            )

    @log_client_operation()
    def delete_review(self, pr_number: int, review_id: int) -> ClientResult[None]:
        """
        Delete a draft review.

        Args:
            pr_number: PR number
            review_id: Review ID

        Returns:
            ClientResult[None]
        """
        try:
            repo = self.gh.get_repo_string()
            args = [
                "api",
                f"/repos/{repo}/pulls/{pr_number}/reviews/{review_id}",
                "--method", "DELETE",
            ]

            self.gh.run_command(args)

            return ClientSuccess(data=None, message=f"Review #{review_id} deleted")

        except GitHubAPIError as e:
            return ClientError(
                error_message=f"Failed to delete review: {e}",
                error_code="API_ERROR"
            )

    @log_client_operation()
    def reply_to_comment(
        self, pr_number: int, comment_id: int, body: str
    ) -> ClientResult[None]:
        """
        Reply to a PR comment using REST API with direct body parameter.

        Args:
            pr_number: PR number
            comment_id: Comment database ID to reply to
            body: Reply text

        Returns:
            ClientResult[None]
        """
        try:
            repo = self.gh.get_repo_string()

            # Use -f instead of -F with stdin to avoid encoding issues
            args = [
                "api", "-X", "POST",
                f"/repos/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
                "-f", f"body={body}",
            ]

            self.gh.run_command(args)

            return ClientSuccess(data=None, message="Reply posted")

        except GitHubAPIError as e:
            return ClientError(
                error_message=f"Failed to reply to comment: {e}",
                error_code="API_ERROR"
            )

    @log_client_operation()
    def add_issue_comment(self, pr_number: int, body: str) -> ClientResult[None]:
        """
        Add a general comment to PR (issue comment).

        Args:
            pr_number: PR number
            body: Comment text

        Returns:
            ClientResult[None]
        """
        try:
            repo = self.gh.get_repo_string()
            args = [
                "api", "-X", "POST",
                f"/repos/{repo}/issues/{pr_number}/comments",
                # "@-" makes gh read the field value from stdin; a bare "-" is
                # taken literally and posts a one-dash comment.
                "-F", "body=@-",
            ]

            self.gh.run_command(args, stdin_input=body)

            return ClientSuccess(data=None, message="Comment added")

        except GitHubAPIError as e:
            return ClientError(
                error_message=f"Failed to add comment: {e}",
                error_code="API_ERROR"
            )

    @log_client_operation()
    def request_pr_review(
        self, pr_number: int, reviewers: Optional[List[str]] = None
    ) -> ClientResult[None]:
        """
        Request review (or re-request) on a PR.

        If reviewers is not provided, re-requests from existing reviewers.

        Args:
            pr_number: PR number
            reviewers: List of GitHub usernames to request review from

        Returns:
            ClientResult[None]
        """
        try:
            # Parse owner/repo
            repo_string = self.gh.get_repo_string()
            owner, repo = repo_string.split('/')

            # Get PR node ID and existing reviewers if needed
            if reviewers is None:
                variables = {
                    "owner": owner,
                    "repo": repo,
                    "prNumber": pr_number
                }

                response = self.graphql.run_query(
                    graphql_queries.GET_PR_WITH_REVIEWERS,
                    variables
                )

                pr_data = (
                    response.get("data", {})
                    .get("repository", {})
                    .get("pullRequest", {})
                )

                if not pr_data:
                    return ClientError(
                        error_message=f"PR #{pr_number} not found",
                        error_code="PR_NOT_FOUND"
                    )

                pr_node_id = pr_data.get("id")

                # Collect existing reviewers
                existing_reviewers = set()
                reviews = pr_data.get("reviews", {}).get("nodes", [])
                for review in reviews:
                    author = review.get("author", {})
                    if author and author.get("login"):
                        existing_reviewers.add(author["login"])

                review_requests = pr_data.get("reviewRequests", {}).get("nodes", [])
                for request in review_requests:
                    requested = request.get("requestedReviewer", {})
                    if requested and requested.get("login"):
                        existing_reviewers.add(requested["login"])

                reviewers = list(existing_reviewers)

                if not reviewers:
                    return ClientSuccess(
                        data=None,
                        message="No existing reviewers to re-request"
                    )
            else:
                # Get PR node ID
                variables = {
                    "owner": owner,
                    "repo": repo,
                    "prNumber": pr_number
                }

                response = self.graphql.run_query(
                    graphql_queries.GET_PR_NODE_ID,
                    variables
                )

                pr_node_id = (
                    response.get("data", {})
                    .get("repository", {})
                    .get("pullRequest", {})
                    .get("id")
                )

                if not pr_node_id:
                    return ClientError(
                        error_message=f"PR #{pr_number} not found",
                        error_code="PR_NOT_FOUND"
                    )

            # Convert usernames to user IDs
            # Skip bots and invalid users that can't be resolved
            user_ids = []
            skipped_users = []

            for username in reviewers:
                try:
                    user_response = self.graphql.run_query(
                        graphql_queries.GET_USER_ID,
                        {"login": username}
                    )

                    user_id = user_response.get("data", {}).get("user", {}).get("id")
                    if user_id:
                        user_ids.append(user_id)
                    else:
                        skipped_users.append(username)
                except GitHubAPIError:
                    # Skip bots and users that can't be resolved (e.g., copilot-pull-request-reviewer)
                    skipped_users.append(username)

            if not user_ids:
                msg = "No valid user reviewers found"
                if skipped_users:
                    msg += f" (skipped bots/invalid: {', '.join(skipped_users)})"
                return ClientSuccess(data=None, message=msg)

            # Request reviews
            self.graphql.run_mutation(
                graphql_queries.REQUEST_REVIEWS,
                {"prId": pr_node_id, "userIds": user_ids}
            )

            msg = f"Review requested from {len(user_ids)} reviewer(s)"
            if skipped_users:
                msg += f" (skipped {len(skipped_users)} bot(s)/invalid)"

            return ClientSuccess(data=None, message=msg)

        except GitHubAPIError as e:
            return ClientError(
                error_message=f"Failed to request review on PR #{pr_number}: {e}",
                error_code="API_ERROR"
            )
