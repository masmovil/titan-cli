"""
Issue Service

Handles issue-related operations.
Network → NetworkModel → UIModel → ClientResult
"""

from typing import List, Optional

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import JiraNetwork
from ...models import (
    NetworkJiraIssue,
    NetworkJiraFields,
    NetworkJiraUser,
    NetworkJiraStatus,
    NetworkJiraStatusCategory,
    NetworkJiraIssueType,
    NetworkJiraPriority,
    UIJiraIssue,
    from_network_issue,
)
from ...models.network.rest.issue import NetworkJiraComponent, NetworkJiraVersion
from ...exceptions import JiraAPIError


class IssueService:
    """
    Service for Jira issue operations.

    PRIVATE - only used by JiraClient.
    Handles: get, search, create, update issues.
    """

    def __init__(self, network: JiraNetwork, metadata_service=None):
        """
        Initialize issue service.

        Args:
            network: JiraNetwork instance for HTTP operations
            metadata_service: MetadataService instance (optional, for type lookup)
        """
        self.network = network
        self.metadata_service = metadata_service

    @log_client_operation()
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
            ClientResult[UIJiraIssue]
        """
        try:
            # 1. Network call
            params = {}
            if expand:
                params["expand"] = ",".join(expand)

            data = self.network.make_request("GET", f"issue/{key}", params=params)

            # 2. Parse to Network model
            network_issue = self._parse_network_issue(data)

            # 3. Map to UI model (pass raw data for custom fields access)
            ui_issue = from_network_issue(network_issue, raw=data)

            # 4. Wrap in Result
            return ClientSuccess(
                data=ui_issue,
                message=f"Issue {key} retrieved successfully"
            )

        except JiraAPIError as e:
            is_not_found = e.status_code == 404
            return ClientError(
                error_message=f"Issue {key} not found" if is_not_found else f"Failed to get issue {key}",
                error_code="ISSUE_NOT_FOUND" if is_not_found else "API_ERROR",
                log_level="warning" if is_not_found else "error",
                details={"status_code": e.status_code} if e.status_code else None
            )

    @log_client_operation()
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
            ClientResult[List[UIJiraIssue]]
        """
        try:
            # 1. Network call
            payload = {
                "jql": jql,
                "maxResults": max_results,
                "fields": fields or ["summary", "status", "assignee", "priority", "created", "updated"]
            }

            data = self.network.make_request("POST", "search/jql", json=payload)

            # 2. Parse and map each issue
            ui_issues = []
            for issue_data in data.get("issues", []):
                network_issue = self._parse_network_issue(issue_data)
                # Pass raw data to mapper for custom fields access
                ui_issue = from_network_issue(network_issue, raw=issue_data)
                ui_issues.append(ui_issue)

            # 3. Wrap in Result
            return ClientSuccess(
                data=ui_issues,
                message=f"Found {len(ui_issues)} issues"
            )

        except JiraAPIError as e:
            return ClientError(
                error_message=f"Failed to search issues: {e.message}",
                error_code="SEARCH_ERROR"
            )

    @log_client_operation()
    def create_issue(
        self,
        project_key: str,
        issue_type_id: str,
        summary: str,
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[str] = None,
        fields: Optional[dict] = None
    ) -> ClientResult[UIJiraIssue]:
        """
        Create new issue.

        Args:
            project_key: Project key
            issue_type_id: Issue type ID
            summary: Issue summary/title
            description: Issue description
            assignee: Assignee username or email
            labels: List of labels
            priority: Priority name
            fields: Additional Jira fields to merge into payload["fields"]

        Returns:
            ClientResult[UIJiraIssue]
        """
        try:
            # 1. Build payload
            payload = {
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "issuetype": {"id": issue_type_id}
                }
            }

            if description:
                payload["fields"]["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description
                                }
                            ]
                        }
                    ]
                }

            # Add optional fields
            if assignee:
                # Support both accountId (Jira Cloud) and name (Jira Server)
                if assignee.startswith("accountId:"):
                    # Extract accountId from "accountId:xxx" format
                    payload["fields"]["assignee"] = {"accountId": assignee.replace("accountId:", "")}
                else:
                    # Assume it's accountId if it looks like one, otherwise use name
                    # AccountIds are typically long alphanumeric strings
                    if len(assignee) > 20 and "-" not in assignee:
                        payload["fields"]["assignee"] = {"accountId": assignee}
                    else:
                        payload["fields"]["assignee"] = {"name": assignee}
            if labels:
                payload["fields"]["labels"] = labels
            if priority:
                payload["fields"]["priority"] = {"name": priority}
            if fields:
                payload["fields"].update(fields)

            # 2. Network call
            data = self.network.make_request("POST", "issue", json=payload)

            # 3. Get the created issue
            issue_key = data["key"]
            return self.get_issue(issue_key)

        except JiraAPIError as e:
            return ClientError(
                error_message=f"Failed to create issue in {project_key}: {e.message}",
                error_code="CREATE_ISSUE_ERROR"
            )

    @log_client_operation()
    def create_issue_with_type_search(
        self,
        project_key: str,
        issue_type_name: str,
        summary: str,
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[str] = None,
        fields: Optional[dict] = None
    ) -> ClientResult[UIJiraIssue]:
        """
        Create issue with issue type search by name (internal).

        Handles:
        - Finding issue type by name (case-insensitive)
        - Epic name preparation if needed
        - Issue creation

        Args:
            project_key: Project key
            issue_type_name: Issue type name (e.g., "Bug", "Story", "Epic")
            summary: Issue summary/title
            description: Issue description
            assignee: Assignee username or email
            labels: List of labels
            priority: Priority name
            fields: Additional Jira fields to merge into payload["fields"]

        Returns:
            ClientResult[UIJiraIssue]
        """
        if not self.metadata_service:
            return ClientError(
                error_message="MetadataService not available",
                error_code="SERVICE_NOT_AVAILABLE"
            )

        # Get issue types for project
        issue_types_result = self.metadata_service.get_issue_types(project_key)

        match issue_types_result:
            case ClientSuccess(data=issue_types):
                # Search for issue type (case-insensitive)
                issue_type = next(
                    (it for it in issue_types if it.name.lower() == issue_type_name.lower()),
                    None,
                )

                if not issue_type:
                    # Not found - return error with available types
                    available = [it.name for it in issue_types]
                    return ClientError(
                        error_message=f"Issue type '{issue_type_name}' not found. Available: {', '.join(available)}",
                        error_code="INVALID_ISSUE_TYPE"
                    )

                # Create issue with resolved type ID
                return self.create_issue(
                    project_key=project_key,
                    issue_type_id=issue_type.id,
                    summary=summary,
                    description=description,
                    assignee=assignee,
                    labels=labels,
                    priority=priority,
                    fields=fields
                )

            case ClientError() as error:
                return error

    @log_client_operation()
    def create_subtask(
        self,
        parent_key: str,
        project_key: str,
        subtask_type_id: str,
        summary: str,
        description: Optional[str] = None
    ) -> ClientResult[UIJiraIssue]:
        """
        Create subtask under parent issue.

        Args:
            parent_key: Parent issue key
            project_key: Project key
            subtask_type_id: Subtask issue type ID
            summary: Subtask summary
            description: Subtask description

        Returns:
            ClientResult[UIJiraIssue]
        """
        try:
            # 1. Build payload
            payload = {
                "fields": {
                    "project": {"key": project_key},
                    "parent": {"key": parent_key},
                    "summary": summary,
                    "issuetype": {"id": subtask_type_id}
                }
            }

            if description:
                payload["fields"]["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description
                                }
                            ]
                        }
                    ]
                }

            # 2. Network call
            data = self.network.make_request("POST", "issue", json=payload)

            # 3. Get the created subtask
            issue_key = data["key"]
            return self.get_issue(issue_key)

        except JiraAPIError as e:
            return ClientError(
                error_message=f"Failed to create subtask under {parent_key}: {e.message}",
                error_code="CREATE_SUBTASK_ERROR"
            )

    @log_client_operation()
    def assign_fix_version(
        self,
        issue_key: str,
        version_id: str,
    ) -> ClientResult[None]:
        """Assign a fixVersion to an issue using a Jira version ID."""
        try:
            payload = {
                "update": {
                    "fixVersions": [
                        {
                            "add": {"id": version_id}
                        }
                    ]
                }
            }

            self.network.make_request("PUT", f"issue/{issue_key}", json=payload)

            return ClientSuccess(
                data=None,
                message=f"Assigned fixVersion {version_id} to {issue_key}",
            )

        except JiraAPIError as e:
            return ClientError(
                error_message=f"Failed to assign fixVersion {version_id} to {issue_key}: {e.message}",
                error_code="ASSIGN_FIX_VERSION_ERROR",
            )

    @log_client_operation()
    def assign_fix_version_by_name(
        self,
        issue_key: str,
        project_key: str,
        version_name: str,
    ) -> ClientResult[None]:
        """Assign a fixVersion to an issue by resolving a project version name."""
        if not self.metadata_service:
            return ClientError(
                error_message="MetadataService not available",
                error_code="SERVICE_NOT_AVAILABLE"
            )

        versions_result = self.metadata_service.list_project_versions(project_key)
        match versions_result:
            case ClientSuccess(data=versions):
                matching_version = next(
                    (version for version in versions if version.name == version_name),
                    None,
                )
                if not matching_version:
                    return ClientError(
                        error_message=f"Version '{version_name}' not found in project {project_key}",
                        error_code="VERSION_NOT_FOUND"
                    )
                return self.assign_fix_version(issue_key, matching_version.id)
            case ClientError() as error:
                return error

    @log_client_operation()
    def assign_fix_version_reference(
        self,
        issue_key: str,
        project_key: str | None = None,
        version_id: str | None = None,
        version_name: str | None = None,
    ) -> ClientResult[None]:
        """Assign a fixVersion to an issue by version ID or version name."""
        if version_id:
            return self.assign_fix_version(issue_key, version_id)

        if not version_name:
            return ClientError(
                error_message="Either version_id or version_name is required",
                error_code="MISSING_VERSION_REFERENCE"
            )

        if not project_key:
            return ClientError(
                error_message="Project key not provided",
                error_code="MISSING_PROJECT_KEY"
            )

        return self.assign_fix_version_by_name(issue_key, project_key, version_name)

    @log_client_operation()
    def assign_issue(
        self,
        issue_key: str,
        account_id: str,
    ) -> ClientResult[None]:
        """Assign an existing issue to a user by account ID."""
        try:
            self.network.make_request(
                "PUT", f"issue/{issue_key}/assignee", json={"accountId": account_id}
            )

            return ClientSuccess(
                data=None,
                message=f"Assigned {issue_key} to user {account_id}",
            )

        except JiraAPIError as e:
            return ClientError(
                error_message=f"Failed to assign {issue_key} to user {account_id}: {e.message}",
                error_code="ASSIGN_ISSUE_ERROR",
            )

    def _convert_text_to_adf(self, text: str) -> dict:
        """
        Convert plain text to Atlassian Document Format (ADF).

        Handles multi-line text by creating separate paragraphs for each line.

        Args:
            text: Plain text (may contain newlines)

        Returns:
            ADF document structure
        """
        # Split by lines and filter out empty lines at start/end
        lines = text.strip().split('\n')

        # Create ADF paragraphs
        content = []
        for line in lines:
            line = line.strip()
            if line:  # Skip empty lines
                content.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}]
                })

        # If no content, create empty paragraph
        if not content:
            content = [{
                "type": "paragraph",
                "content": [{"type": "text", "text": ""}]
            }]

        return {
            "type": "doc",
            "version": 1,
            "content": content
        }

    # ==================== INTERNAL PARSERS ====================

    def _parse_user(self, user_data: Optional[dict]) -> Optional[NetworkJiraUser]:
        """Parse user data from API response"""
        if not user_data:
            return None

        return NetworkJiraUser(
            displayName=user_data.get("displayName", "Unknown"),
            accountId=user_data.get("accountId"),
            emailAddress=user_data.get("emailAddress"),
            avatarUrls=user_data.get("avatarUrls"),
            active=user_data.get("active", True),
        )

    def _parse_status(self, status_data: Optional[dict]) -> Optional[NetworkJiraStatus]:
        """Parse status data from API response"""
        if not status_data:
            return None

        status_category = None
        if status_data.get("statusCategory"):
            cat_data = status_data["statusCategory"]
            status_category = NetworkJiraStatusCategory(
                id=cat_data.get("id", ""),
                name=cat_data.get("name", ""),
                key=cat_data.get("key", ""),
                colorName=cat_data.get("colorName"),
            )

        return NetworkJiraStatus(
            id=status_data.get("id", ""),
            name=status_data.get("name", "Unknown"),
            description=status_data.get("description"),
            statusCategory=status_category,
        )

    def _parse_issue_type(self, issuetype_data: Optional[dict]) -> Optional[NetworkJiraIssueType]:
        """Parse issue type data from API response"""
        if not issuetype_data:
            return None

        return NetworkJiraIssueType(
            id=issuetype_data.get("id", ""),
            name=issuetype_data.get("name", "Unknown"),
            description=issuetype_data.get("description"),
            subtask=issuetype_data.get("subtask", False),
            iconUrl=issuetype_data.get("iconUrl"),
        )

    def _parse_priority(self, priority_data: Optional[dict]) -> Optional[NetworkJiraPriority]:
        """Parse priority data from API response"""
        if not priority_data:
            return None

        return NetworkJiraPriority(
            id=priority_data.get("id", ""),
            name=priority_data.get("name", "Unknown"),
            iconUrl=priority_data.get("iconUrl"),
        )

    def _parse_network_issue(self, issue_data: dict) -> NetworkJiraIssue:
        """Parse issue data from API response into Network model"""
        fields_data = issue_data.get("fields", {})

        # Parse nested objects
        status = self._parse_status(fields_data.get("status"))
        issuetype = self._parse_issue_type(fields_data.get("issuetype"))
        assignee = self._parse_user(fields_data.get("assignee"))
        reporter = self._parse_user(fields_data.get("reporter"))
        priority = self._parse_priority(fields_data.get("priority"))

        # Parse components
        components = []
        for comp_data in fields_data.get("components", []):
            components.append(NetworkJiraComponent(
                id=comp_data.get("id", ""),
                name=comp_data.get("name", ""),
                description=comp_data.get("description"),
            ))

        # Parse fix versions
        fix_versions = []
        for ver_data in fields_data.get("fixVersions", []):
            fix_versions.append(NetworkJiraVersion(
                id=ver_data.get("id", ""),
                name=ver_data.get("name", ""),
                description=ver_data.get("description"),
                released=ver_data.get("released", False),
                releaseDate=ver_data.get("releaseDate"),
            ))

        # Build fields object
        fields = NetworkJiraFields(
            summary=fields_data.get("summary", ""),
            description=fields_data.get("description"),  # Keep as-is (ADF or string)
            status=status,
            issuetype=issuetype,
            assignee=assignee,
            reporter=reporter,
            priority=priority,
            created=fields_data.get("created"),
            updated=fields_data.get("updated"),
            labels=fields_data.get("labels", []),
            components=components if components else None,
            fixVersions=fix_versions if fix_versions else None,
            parent=fields_data.get("parent"),
            subtasks=fields_data.get("subtasks"),
        )

        # Build issue object
        return NetworkJiraIssue(
            key=issue_data["key"],
            id=issue_data["id"],
            fields=fields,
            self=issue_data.get("self"),
            expand=issue_data.get("expand"),
        )


__all__ = ["IssueService"]
