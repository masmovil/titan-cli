"""
Jira Client Facade

Public API for Jira plugin.
Delegates to internal services.
"""

from typing import List, Optional

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError

from .network import JiraNetwork
from .services import (
    IssueService,
    ProjectService,
    CommentService,
    TransitionService,
    MetadataService,
    LinkService,
)
from ..models import (
    UIJiraIssue,
    UIJiraProject,
    UIJiraComment,
    UIJiraTransition,
    UIJiraIssueType,
    UIJiraStatus,
    UIJiraUser,
    UIJiraVersion,
    UIPriority
)


class JiraClient:
    """
    Jira Client Facade.

    Public API for the Jira plugin.
    Delegates all work to internal services.

    All methods return ClientResult[T] for type-safe error handling.
    Use pattern matching to handle success and error cases.
    """

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: Optional[str] = None,
        timeout: int = 30,
        enable_cache: bool = False,
        cache_ttl: int = 300
    ):
        """
        Initialize Jira client.

        Args:
            base_url: Jira instance URL
            email: User email for authentication
            api_token: Jira API token (Personal Access Token)
            project_key: Default project key (optional)
            timeout: Request timeout in seconds
            enable_cache: Enable response caching (optional, not implemented yet)
            cache_ttl: Cache time-to-live in seconds (optional, not implemented yet)
        """
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl

        # Internal dependencies (private)
        self._network = JiraNetwork(base_url, email, api_token, timeout)
        self._metadata_service = MetadataService(self._network)
        self._issue_service = IssueService(self._network, self._metadata_service)
        self._project_service = ProjectService(self._network)
        self._comment_service = CommentService(self._network)
        self._transition_service = TransitionService(self._network)
        self._link_service = LinkService(self._network)

    # ==================== ISSUE OPERATIONS ====================

    def get_issue(
        self,
        key: str,
        expand: Optional[List[str]] = None
    ) -> ClientResult[UIJiraIssue]:
        """
        Get issue by key.

        Args:
            key: Issue key (e.g., "PROJ-123")
            expand: Optional fields to expand

        Returns:
            ClientResult[UIJiraIssue] - Success contains the issue data, Error contains error details
        """
        return self._issue_service.get_issue(key, expand)

    def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        fields: Optional[List[str]] = None
    ) -> ClientResult[List[UIJiraIssue]]:
        """
        Search issues using JQL.

        Args:
            jql: JQL query string
            max_results: Maximum number of results
            fields: List of fields to return

        Returns:
            ClientResult[List[UIJiraIssue]] - Success contains list of issues matching the query
        """
        return self._issue_service.search_issues(jql, max_results, fields)

    # ==================== PROJECT OPERATIONS ====================

    def get_project(self, key: Optional[str] = None) -> ClientResult[UIJiraProject]:
        """
        Get project by key.

        Args:
            key: Project key (uses default if not provided)

        Returns:
            ClientResult[UIJiraProject]
        """
        project_key = key or self.project_key
        if not project_key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        return self._project_service.get_project(project_key)

    def list_projects(self) -> ClientResult[List[UIJiraProject]]:
        """
        List all accessible projects.

        Returns:
            ClientResult[List[UIJiraProject]]
        """
        return self._project_service.list_projects()

    # ==================== COMMENT OPERATIONS ====================

    def get_comments(self, issue_key: str) -> ClientResult[List[UIJiraComment]]:
        """
        Get all comments for an issue.

        Args:
            issue_key: Issue key

        Returns:
            ClientResult[List[UIJiraComment]]
        """
        return self._comment_service.get_comments(issue_key)

    def add_comment(self, issue_key: str, body: str) -> ClientResult[UIJiraComment]:
        """
        Add comment to issue.

        Args:
            issue_key: Issue key
            body: Comment text

        Returns:
            ClientResult[UIJiraComment]
        """
        return self._comment_service.add_comment(issue_key, body)

    # ==================== TRANSITION OPERATIONS ====================

    def get_transitions(self, issue_key: str) -> ClientResult[List[UIJiraTransition]]:
        """
        Get available transitions for an issue.

        Args:
            issue_key: Issue key

        Returns:
            ClientResult[List[UIJiraTransition]]
        """
        return self._transition_service.get_transitions(issue_key)

    def transition_issue(
        self,
        issue_key: str,
        new_status: str,
        comment: Optional[str] = None,
        fields: Optional[dict] = None,
        update: Optional[dict] = None,
    ) -> ClientResult[None]:
        """
        Transition issue to new status.

        Args:
            issue_key: Issue key
            new_status: Target status name
            comment: Optional comment
            fields: Optional Jira fields payload to send with the transition
            update: Optional Jira update payload to merge into the transition

        Returns:
            ClientResult[None]
        """
        return self._transition_service.transition_issue(
            issue_key,
            new_status,
            comment=comment,
            fields=fields,
            update=update,
        )

    # ==================== CREATION OPERATIONS ====================

    def create_issue(
        self,
        issue_type: str,
        summary: str,
        description: Optional[str] = None,
        project: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[str] = None,
        fields: Optional[dict] = None
    ) -> ClientResult[UIJiraIssue]:
        """
        Create new issue.

        Args:
            issue_type: Issue type name (Bug, Story, Task, etc.)
            summary: Issue summary/title
            description: Issue description
            project: Project key (uses default if not provided)
            assignee: Assignee username or email
            labels: List of labels
            priority: Priority name
            fields: Additional Jira fields to merge into payload["fields"]

        Returns:
            ClientResult[UIJiraIssue]
        """
        project_key = project or self.project_key
        if not project_key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        # Delegate to service (handles type search and Epic name logic)
        return self._issue_service.create_issue_with_type_search(
            project_key=project_key,
            issue_type_name=issue_type,
            summary=summary,
            description=description,
            assignee=assignee,
            labels=labels,
            priority=priority,
            fields=fields
        )

    def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: Optional[str] = None
    ) -> ClientResult[UIJiraIssue]:
        """
        Create subtask under parent issue.

        Args:
            parent_key: Parent issue key
            summary: Subtask summary
            description: Subtask description

        Returns:
            ClientResult[UIJiraIssue]
        """
        if not self.project_key:
            return ClientError(
                error_message="No default project configured",
                error_code="MISSING_PROJECT_KEY"
            )

        # Find subtask issue type (delegated to service)
        subtask_type_result = self._metadata_service.find_subtask_issue_type(self.project_key)

        match subtask_type_result:
            case ClientSuccess(data=subtask_type):
                return self._issue_service.create_subtask(
                    parent_key=parent_key,
                    project_key=self.project_key,
                    subtask_type_id=subtask_type.id,
                    summary=summary,
                    description=description
                )
            case ClientError() as error:
                return error

    # ==================== METADATA OPERATIONS ====================

    def get_issue_types(self, project_key: Optional[str] = None) -> ClientResult[List[UIJiraIssueType]]:
        """
        Get issue types for a project.

        Args:
            project_key: Project key (uses default if not provided)

        Returns:
            ClientResult[List[UIJiraIssueType]]
        """
        key = project_key or self.project_key
        if not key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        return self._metadata_service.get_issue_types(key)

    def list_statuses(self, project_key: Optional[str] = None) -> ClientResult[List[UIJiraStatus]]:
        """
        List all available statuses for a project.

        Args:
            project_key: Project key (uses default if not provided)

        Returns:
            ClientResult[List[UIJiraStatus]]
        """
        key = project_key or self.project_key
        if not key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        return self._metadata_service.list_statuses(key)

    def get_current_user(self) -> ClientResult[UIJiraUser]:
        """
        Get current authenticated user info.

        Returns:
            ClientResult[UIJiraUser]
        """
        return self._metadata_service.get_current_user()

    def list_project_versions(self, project_key: Optional[str] = None) -> ClientResult[List[UIJiraVersion]]:
        """
        List all versions for a project.

        Args:
            project_key: Project key (uses default if not provided)

        Returns:
            ClientResult[List[UIJiraVersion]]
        """
        key = project_key or self.project_key
        if not key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        return self._metadata_service.list_project_versions(key)

    def create_version(
        self,
        name: str,
        project_key: Optional[str] = None,
        description: Optional[str] = None,
        release_date: Optional[str] = None,
    ) -> ClientResult[UIJiraVersion]:
        """Create a version in the provided or default Jira project."""
        key = project_key or self.project_key
        if not key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        return self._metadata_service.create_version(
            project_key=key,
            name=name,
            description=description,
            release_date=release_date,
        )

    def ensure_version_exists(
        self,
        name: str,
        project_key: Optional[str] = None,
        description: Optional[str] = None,
        release_date: Optional[str] = None,
    ) -> ClientResult[UIJiraVersion]:
        """Return an existing version by name or create it if missing."""
        key = project_key or self.project_key
        if not key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        return self._metadata_service.ensure_version_exists(
            project_key=key,
            name=name,
            description=description,
            release_date=release_date,
        )

    def assign_fix_version(
        self,
        issue_key: str,
        version_id: Optional[str] = None,
        version_name: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> ClientResult[None]:
        """Assign a fixVersion to an issue by version ID or version name."""
        return self._issue_service.assign_fix_version_reference(
            issue_key=issue_key,
            project_key=project_key or self.project_key,
            version_id=version_id,
            version_name=version_name,
        )

    def assign_issue(self, issue_key: str, account_id: str) -> ClientResult[None]:
        """Assign an existing issue to a user by account ID."""
        return self._issue_service.assign_issue(issue_key=issue_key, account_id=account_id)

    def get_priorities(self) -> ClientResult[List[UIPriority]]:
        """
        Get all available priorities in Jira.

        Returns:
            ClientResult[List[UIPriority]]
        """
        return self._metadata_service.get_priorities()

    # ==================== LINK OPERATIONS ====================

    def link_issue(
        self,
        inward_issue: str,
        outward_issue: str,
        link_type: str = "Relates"
    ) -> ClientResult[None]:
        """
        Create link between two issues.

        Args:
            inward_issue: Source issue key
            outward_issue: Target issue key
            link_type: Link type name

        Returns:
            ClientResult[None]
        """
        return self._link_service.link_issues(inward_issue, outward_issue, link_type)

    def add_remote_link(
        self,
        issue_key: str,
        url: str,
        title: str,
        relationship: str = "relates to"
    ) -> ClientResult[str]:
        """
        Add remote link (e.g., GitHub PR) to issue.

        Args:
            issue_key: Issue key
            url: URL to link
            title: Link title
            relationship: Relationship description

        Returns:
            ClientResult[str] with link ID
        """
        return self._link_service.add_remote_link(issue_key, url, title, relationship)


__all__ = ["JiraClient"]
