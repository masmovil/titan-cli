#!/usr/bin/env python3
"""
JIRA Plugin Data Models

All Pydantic models and dataclasses for the JIRA plugin.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any


class IssueStatus(str, Enum):
    """Common JIRA issue statuses"""
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    IN_REVIEW = "In Review"
    READY_FOR_QA = "Ready for QA"
    IN_QA = "In QA"
    DONE = "Done"
    BLOCKED = "Blocked"


@dataclass
class JiraProject:
    """Represents a JIRA project"""
    id: str
    key: str
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = None
    lead: Optional[str] = None


@dataclass
class JiraIssueType:
    """Represents a JIRA issue type"""
    id: str
    name: str
    description: Optional[str] = None
    subtask: bool = False


@dataclass
class JiraTransition:
    """Represents a JIRA workflow transition"""
    id: str
    name: str
    to_status: str


@dataclass
class JiraComment:
    """Represents a JIRA comment"""
    id: str
    author: str
    body: str
    created: str
    updated: Optional[str] = None


@dataclass
class JiraTicket:
    """Represents a JIRA ticket/issue"""
    key: str
    id: str
    summary: str
    description: Optional[str]
    status: str
    issue_type: str
    assignee: Optional[str]
    reporter: str
    priority: str
    created: str
    updated: str
    labels: List[str]
    components: List[str]
    fix_versions: List[str]
    raw: Dict[str, Any]  # Original API response


__all__ = [
    "IssueStatus",
    "JiraProject",
    "JiraIssueType",
    "JiraTransition",
    "JiraComment",
    "JiraTicket",
]
