#!/usr/bin/env python3
"""
JIRA REST API Client

Complete Python SDK for JIRA REST API v2 (JIRA Server compatible)
No external dependencies beyond requests.

Migrated from: /Users/rpedraza/MultiAgentClaude/src/jira/api_client.py
"""

import json
from typing import Dict, List, Optional, Any, Union

import requests

from ..models import (
    JiraProject,
    JiraIssueType,
    JiraTransition,
    JiraComment,
    JiraTicket,
)
from ..exceptions import JiraAPIError


class JiraClient:
    """
    JIRA REST API v2 Client (for JIRA Server)

    Provides direct HTTP access to JIRA without external CLI dependencies.
    Supports JIRA Server 9.x with Personal Access Token (Bearer) authentication.
    """

    def __init__(self, base_url: str, email: str, api_token: str,
                 project_key: Optional[str] = None, timeout: int = 30,
                 enable_cache: bool = True, cache_ttl: int = 300):
        """
        Initialize JIRA client

        Args:
            base_url: JIRA instance URL
            email: User email for authentication
            api_token: JIRA API token (Personal Access Token)
            project_key: Default project key (optional)
            timeout: Request timeout in seconds
            enable_cache: Enable in-memory caching (default: True)
            cache_ttl: Cache time-to-live in seconds (default: 300 = 5 minutes)

        Note:
            JIRA Server/Next uses Basic Auth with Personal Access Token.
            For JIRA Cloud: API tokens can be created at https://id.atlassian.com/manage/api-tokens
        """
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.project_key = project_key
        self.timeout = timeout

        if not self.api_token:
            raise JiraAPIError("JIRA API token not provided")

        if not self.base_url:
            raise JiraAPIError("JIRA base URL not provided")

        if not self.email:
            raise JiraAPIError("JIRA user email not provided")

        self.session = requests.Session()
        # Use Bearer Token Authentication (OAuth 2.0) for JIRA API
        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        })

        # Cache disabled for now (TODO: implement JiraCache)
        self._cache = None

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Union[Dict, List]:
        """Make HTTP request to JIRA API"""
        # JIRA Server uses API v2
        url = f"{self.base_url}/rest/api/2/{endpoint.lstrip('/')}"

        # Add Content-Type only for POST/PUT/PATCH (not GET/DELETE)
        if method.upper() in ('POST', 'PUT', 'PATCH') and 'json' in kwargs:
            headers = kwargs.get('headers', {})
            headers['Content-Type'] = 'application/json'
            kwargs['headers'] = headers

        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)

            if response.status_code == 204:
                return {}

            response.raise_for_status()
            return response.json() if response.content else {}

        except requests.exceptions.HTTPError as e:
            error_msg = f"JIRA API error: {e}"
            try:
                error_detail = e.response.json()
                error_msg = f"{error_msg}\nDetails: {json.dumps(error_detail, indent=2)}"
            except (ValueError, AttributeError):
                # If not JSON, show raw text
                error_msg = f"{error_msg}\nResponse: {e.response.text[:500]}"

            try:
                response_json = e.response.json() if e.response.content else None
            except (ValueError, AttributeError):
                response_json = None

            raise JiraAPIError(error_msg, status_code=e.response.status_code, response=response_json)

        except requests.exceptions.RequestException as e:
            raise JiraAPIError(f"Request failed: {e}")

    # ==================== TICKET OPERATIONS ====================

    def get_ticket(self, ticket_key: str, expand: Optional[List[str]] = None) -> JiraTicket:
        """
        Get ticket details

        Args:
            ticket_key: Ticket key (e.g., "PROJ-123")
            expand: Additional fields to expand (e.g., ["changelog", "renderedFields"])

        Returns:
            JiraTicket object
        """
        params = {}
        if expand:
            params["expand"] = ",".join(expand)

        data = self._make_request("GET", f"issue/{ticket_key}", params=params)

        fields = data.get("fields", {})

        return JiraTicket(
            key=data["key"],
            id=data["id"],
            summary=fields.get("summary", ""),
            description=fields.get("description"),
            status=fields.get("status", {}).get("name", "Unknown"),
            issue_type=fields.get("issuetype", {}).get("name", "Unknown"),
            assignee=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            reporter=fields.get("reporter", {}).get("displayName", "Unknown"),
            priority=fields.get("priority", {}).get("name", "Unknown"),
            created=fields.get("created", ""),
            updated=fields.get("updated", ""),
            labels=fields.get("labels", []),
            components=[c.get("name", "") for c in fields.get("components", [])],
            fix_versions=[v.get("name", "") for v in fields.get("fixVersions", [])],
            raw=data
        )

    def search_tickets(self, jql: str, max_results: int = 50, fields: Optional[List[str]] = None) -> List[JiraTicket]:
        """
        Search tickets using JQL

        Args:
            jql: JQL query string
            max_results: Maximum number of results
            fields: List of fields to return

        Returns:
            List of JiraTicket objects
        """
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields or ["summary", "status", "assignee", "priority", "created", "updated"]
        }

        data = self._make_request("POST", "search", json=payload)

        tickets = []
        for issue in data.get("issues", []):
            fields_data = issue.get("fields", {})
            tickets.append(JiraTicket(
                key=issue["key"],
                id=issue["id"],
                summary=fields_data.get("summary", ""),
                description=fields_data.get("description"),
                status=(fields_data.get("status") or {}).get("name", "Unknown"),
                issue_type=(fields_data.get("issuetype") or {}).get("name", "Unknown"),
                assignee=(fields_data.get("assignee") or {}).get("displayName") if fields_data.get("assignee") else None,
                reporter=(fields_data.get("reporter") or {}).get("displayName", "Unknown"),
                priority=(fields_data.get("priority") or {}).get("name", "Unknown"),
                created=fields_data.get("created", ""),
                updated=fields_data.get("updated", ""),
                labels=fields_data.get("labels", []),
                components=[c.get("name", "") for c in fields_data.get("components", [])],
                fix_versions=[v.get("name", "") for v in fields_data.get("fixVersions", [])],
                raw=issue
            ))

        return tickets

    def update_ticket_status(self, ticket_key: str, new_status: str, comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Update ticket status using transitions

        Args:
            ticket_key: Ticket key
            new_status: Target status name
            comment: Optional comment to add with transition

        Returns:
            Result dictionary
        """
        # Get available transitions
        transitions = self.get_transitions(ticket_key)

        # Find transition to target status
        transition_id = None
        for trans in transitions:
            if trans.to_status.lower() == new_status.lower():
                transition_id = trans.id
                break

        if not transition_id:
            available = [t.to_status for t in transitions]
            raise JiraAPIError(
                f"Cannot transition to '{new_status}'. Available transitions: {', '.join(available)}"
            )

        payload = {
            "transition": {"id": transition_id}
        }

        # Add comment if provided
        if comment:
            payload["update"] = {
                "comment": [{
                    "add": {
                        "body": {
                            "type": "doc",
                            "version": 1,
                            "content": [{
                                "type": "paragraph",
                                "content": [{"type": "text", "text": comment}]
                            }]
                        }
                    }
                }]
            }

        self._make_request("POST", f"issue/{ticket_key}/transitions", json=payload)

        return {
            "ticket_key": ticket_key,
            "new_status": new_status,
            "transition_id": transition_id
        }

    def get_transitions(self, ticket_key: str) -> List[JiraTransition]:
        """
        Get available transitions for a ticket

        Args:
            ticket_key: Ticket key

        Returns:
            List of available transitions
        """
        data = self._make_request("GET", f"issue/{ticket_key}/transitions")

        transitions = []
        for trans in data.get("transitions", []):
            transitions.append(JiraTransition(
                id=trans["id"],
                name=trans["name"],
                to_status=trans.get("to", {}).get("name", trans["name"])
            ))

        return transitions

    # ==================== COMMENT OPERATIONS ====================

    def add_comment(self, ticket_key: str, body: str) -> JiraComment:
        """
        Add comment to ticket

        Args:
            ticket_key: Ticket key
            body: Comment text

        Returns:
            Created comment
        """
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": body
                            }
                        ]
                    }
                ]
            }
        }

        data = self._make_request("POST", f"issue/{ticket_key}/comment", json=payload)

        return JiraComment(
            id=data["id"],
            author=data.get("author", {}).get("displayName", "Unknown"),
            body=body,
            created=data.get("created", ""),
            updated=data.get("updated")
        )

    def get_comments(self, ticket_key: str) -> List[JiraComment]:
        """
        Get all comments for a ticket

        Args:
            ticket_key: Ticket key

        Returns:
            List of comments
        """
        data = self._make_request("GET", f"issue/{ticket_key}/comment")

        comments = []
        for comment in data.get("comments", []):
            # Extract text from Atlassian Document Format
            body_text = self._extract_text_from_adf(comment.get("body", {}))

            comments.append(JiraComment(
                id=comment["id"],
                author=comment.get("author", {}).get("displayName", "Unknown"),
                body=body_text,
                created=comment.get("created", ""),
                updated=comment.get("updated")
            ))

        return comments

    def _extract_text_from_adf(self, adf: Dict) -> str:
        """Extract plain text from Atlassian Document Format"""
        if not adf:
            return ""

        text_parts = []

        def extract_recursive(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))

                if "content" in node:
                    for child in node["content"]:
                        extract_recursive(child)

        extract_recursive(adf)
        return " ".join(text_parts)

    # ==================== LINK OPERATIONS ====================

    def link_issue(self, inward_issue: str, outward_issue: str, link_type: str = "Relates") -> Dict[str, Any]:
        """
        Create link between two issues

        Args:
            inward_issue: Source issue key
            outward_issue: Target issue key
            link_type: Link type name (e.g., "Relates", "Blocks", "Duplicate")

        Returns:
            Result dictionary
        """
        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_issue},
            "outwardIssue": {"key": outward_issue}
        }

        self._make_request("POST", "issueLink", json=payload)

        return {
            "inward_issue": inward_issue,
            "outward_issue": outward_issue,
            "link_type": link_type
        }

    def add_remote_link(self, ticket_key: str, url: str, title: str, relationship: str = "relates to") -> Dict[str, Any]:
        """
        Add remote link (e.g., GitHub PR) to ticket

        Args:
            ticket_key: Ticket key
            url: URL to link
            title: Link title
            relationship: Relationship description

        Returns:
            Created link info
        """
        payload = {
            "object": {
                "url": url,
                "title": title
            },
            "relationship": relationship
        }

        data = self._make_request("POST", f"issue/{ticket_key}/remotelink", json=payload)

        return {
            "ticket_key": ticket_key,
            "url": url,
            "title": title,
            "link_id": data.get("id")
        }

    # ==================== PROJECT OPERATIONS ====================

    def get_project(self, project_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Get project details

        Args:
            project_key: Project key (uses default if not provided)

        Returns:
            Project details
        """
        key = project_key or self.project_key
        if not key:
            raise JiraAPIError("Project key not provided")

        return self._make_request("GET", f"project/{key}")

    def get_issue_types(self, project_key: Optional[str] = None) -> List[JiraIssueType]:
        """
        Get available issue types for project.

        Results are cached for 5 minutes by default.

        Args:
            project_key: Project key (uses default if not provided)

        Returns:
            List of issue types
        """
        key = project_key or self.project_key
        if not key:
            raise JiraAPIError("Project key not provided")

        # Check cache
        cache_key = f"issue_types:{key}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Fetch from API
        project = self.get_project(key)
        issue_types = []

        for issue_type in project.get("issueTypes", []):
            issue_types.append(JiraIssueType(
                id=issue_type["id"],
                name=issue_type["name"],
                description=issue_type.get("description"),
                subtask=issue_type.get("subtask", False)
            ))

        # Cache result
        if self._cache:
            self._cache.set(cache_key, issue_types)

        return issue_types

    def list_projects(self) -> List[JiraProject]:
        """
        List all accessible JIRA projects.

        Results are cached for 5 minutes by default.

        Returns:
            List of JiraProject objects
        """
        # Check cache
        cache_key = "projects"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Fetch from API
        data = self._make_request("GET", "project")

        projects = []
        for project_data in data:
            projects.append(JiraProject(
                id=project_data["id"],
                key=project_data["key"],
                name=project_data["name"],
                description=project_data.get("description"),
                project_type=project_data.get("projectTypeKey"),
                lead=project_data.get("lead", {}).get("displayName")
            ))

        # Cache result
        if self._cache:
            self._cache.set(cache_key, projects)

        return projects

    def get_project_by_key(self, project_key: str) -> Optional[JiraProject]:
        """
        Get a specific project by key.

        Results are cached for 5 minutes by default.

        Args:
            project_key: Project key (e.g., "ECAPP", "JAZZ")

        Returns:
            JiraProject object or None if not found
        """
        # Check cache
        cache_key = f"project:{project_key}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Fetch from API
        try:
            data = self._make_request("GET", f"project/{project_key}")
            project = JiraProject(
                id=data["id"],
                key=data["key"],
                name=data["name"],
                description=data.get("description"),
                project_type=data.get("projectTypeKey"),
                lead=data.get("lead", {}).get("displayName")
            )

            # Cache result
            if self._cache:
                self._cache.set(cache_key, project)

            return project
        except JiraAPIError:
            return None

    def list_statuses(self, project_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all available statuses for a project.

        Results are cached for 5 minutes by default.

        Args:
            project_key: Project key (uses default if not provided)

        Returns:
            List of status dictionaries
        """
        key = project_key or self.project_key
        if not key:
            raise JiraAPIError("Project key not provided")

        # Check cache
        cache_key = f"statuses:{key}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Get all statuses for the project
        data = self._make_request("GET", f"project/{key}/statuses")

        # Extract unique statuses
        statuses = []
        seen_names = set()

        for issue_type_data in data:
            for status in issue_type_data.get("statuses", []):
                status_name = status.get("name")
                if status_name and status_name not in seen_names:
                    statuses.append({
                        "id": status.get("id"),
                        "name": status_name,
                        "description": status.get("description"),
                        "category": status.get("statusCategory", {}).get("name")
                    })
                    seen_names.add(status_name)

        # Cache result
        if self._cache:
            self._cache.set(cache_key, statuses)

        return statuses

    # ==================== SUBTASK OPERATIONS ====================

    def create_subtask(self, parent_key: str, summary: str, description: Optional[str] = None) -> JiraTicket:
        """
        Create subtask under parent issue

        Args:
            parent_key: Parent issue key
            summary: Subtask summary
            description: Subtask description

        Returns:
            Created subtask

        Raises:
            JiraAPIError: If no default project is configured
        """
        if not self.project_key:
            raise JiraAPIError(
                "No default project configured. "
                "Please set default_project in JIRA plugin configuration."
            )

        # Get subtask issue type
        issue_types = self.get_issue_types()
        subtask_type = next((it for it in issue_types if it.subtask), None)

        if not subtask_type:
            raise JiraAPIError("No subtask issue type found for project")

        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "parent": {"key": parent_key},
                "summary": summary,
                "issuetype": {"id": subtask_type.id}
            }
        }

        if description:
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}]
                    }
                ]
            }

        data = self._make_request("POST", "issue", json=payload)

        return self.get_ticket(data["key"])

    def create_issue(self, issue_type: str, summary: str, description: Optional[str] = None,
                     project: Optional[str] = None, assignee: Optional[str] = None,
                     labels: Optional[List[str]] = None, priority: Optional[str] = None) -> JiraTicket:
        """
        Create new JIRA issue

        Args:
            issue_type: Issue type name (Bug, Story, Task, etc.)
            summary: Issue summary/title
            description: Issue description
            project: Project key (uses default if not provided)
            assignee: Assignee username or email
            labels: List of labels
            priority: Priority name

        Returns:
            Created issue
        """
        project_key = project or self.project_key
        if not project_key:
            raise JiraAPIError("Project key not provided")

        # Get issue type ID
        issue_types = self.get_issue_types(project_key)
        issue_type_obj = next((it for it in issue_types if it.name.lower() == issue_type.lower()), None)

        if not issue_type_obj:
            available = [it.name for it in issue_types]
            raise JiraAPIError(
                f"Issue type '{issue_type}' not found. Available: {', '.join(available)}"
            )

        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"id": issue_type_obj.id}
            }
        }

        # Add description if provided
        if description:
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}]
                    }
                ]
            }

        # Add optional fields
        if assignee:
            payload["fields"]["assignee"] = {"name": assignee}

        if labels:
            payload["fields"]["labels"] = labels

        if priority:
            payload["fields"]["priority"] = {"name": priority}

        data = self._make_request("POST", "issue", json=payload)

        return self.get_ticket(data["key"])


# Export public API
__all__ = [
    "JiraClient",
]
