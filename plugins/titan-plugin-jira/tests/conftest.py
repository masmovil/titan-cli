"""
Pytest configuration and shared fixtures for JIRA plugin tests
"""

import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_jira_client():
    """Create a mock JIRA client for testing"""
    client = Mock()
    client.base_url = "https://test.atlassian.net"
    client.email = "test@example.com"
    client.project_key = "TEST"
    client.timeout = 30
    return client


@pytest.fixture
def mock_workflow_context():
    """Create a mock WorkflowContext for testing steps"""
    ctx = Mock()
    ctx.views = None
    ctx.ui = None
    ctx.data = {}
    ctx.current_step = 1
    ctx.total_steps = 1
    ctx.plugin_manager = None
    ctx.get = lambda key, default=None: ctx.data.get(key, default)
    return ctx


@pytest.fixture
def sample_jira_ticket():
    """Create a sample JIRA ticket for testing"""
    from titan_plugin_jira.models import JiraTicket

    return JiraTicket(
        key="TEST-123",
        summary="Sample test issue",
        description="This is a test issue description",
        status="In Progress",
        issue_type="Bug",
        priority="High",
        assignee="John Doe",
        reporter="Jane Doe",
        created="2025-01-01T12:00:00.000+0000",
        updated="2025-01-02T12:00:00.000+0000",
        labels=["test", "bug"],
        components=["API"],
        project_key="TEST",
        project_name="Test Project"
    )


@pytest.fixture
def sample_jira_project():
    """Create a sample JIRA project for testing"""
    from titan_plugin_jira.models import JiraProject

    return JiraProject(
        id="10000",
        key="TEST",
        name="Test Project",
        description="A test project",
        project_type="software",
        lead="Project Lead"
    )


@pytest.fixture
def sample_issue_types():
    """Create sample JIRA issue types for testing"""
    from titan_plugin_jira.models import JiraIssueType

    return [
        JiraIssueType(
            id="1",
            name="Bug",
            subtask=False,
            description="A software bug"
        ),
        JiraIssueType(
            id="2",
            name="Story",
            subtask=False,
            description="A user story"
        ),
        JiraIssueType(
            id="3",
            name="Task",
            subtask=False,
            description="A task"
        ),
        JiraIssueType(
            id="4",
            name="Sub-task",
            subtask=True,
            description="A sub-task"
        )
    ]


@pytest.fixture
def sample_statuses():
    """Create sample JIRA statuses for testing"""
    return [
        {
            "id": "1",
            "name": "To Do",
            "statusCategory": {"name": "To Do"}
        },
        {
            "id": "2",
            "name": "In Progress",
            "statusCategory": {"name": "In Progress"}
        },
        {
            "id": "3",
            "name": "Done",
            "statusCategory": {"name": "Done"}
        }
    ]


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require real JIRA or mock server)"
    )
    config.addinivalue_line(
        "markers",
        "unit: marks tests as unit tests (use mocks, no external dependencies)"
    )
