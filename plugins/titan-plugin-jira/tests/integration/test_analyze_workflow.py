"""
Integration tests for the analyze-jira-issues workflow.

These tests verify the complete workflow execution with mocked JIRA API responses.
"""

import pytest
from unittest.mock import MagicMock, Mock
from titan_cli.engine import WorkflowContextBuilder, Success, Error, Skip
from titan_cli.core.secrets import SecretManager
from titan_plugin_jira.clients.jira_client import JiraTicket


def create_mock_ticket(**kwargs):
    """Helper to create JiraTicket with default values."""
    defaults = {
        "key": "TEST-123",
        "id": "12345",
        "summary": "Test summary",
        "description": "Test description",
        "status": "Open",
        "issue_type": "Task",
        "assignee": "test@example.com",
        "reporter": "reporter@example.com",
        "priority": "Medium",
        "created": "2025-01-01T00:00:00Z",
        "updated": "2025-01-02T00:00:00Z",
        "labels": [],
        "components": [],
        "fix_versions": [],
        "raw": {}
    }
    defaults.update(kwargs)
    return JiraTicket(**defaults)


def execute_step_with_metadata(step_func, ctx):
    """
    Execute a step and merge metadata into context.
    This mimics what WorkflowExecutor does.
    """
    result = step_func(ctx)
    if hasattr(result, 'metadata') and result.metadata:
        ctx.data.update(result.metadata)
    return result


@pytest.fixture
def mock_jira_client():
    """Mock JIRA client with sample data."""
    client = MagicMock()

    # Mock search_tickets to return sample issues
    client.search_tickets.return_value = [
        create_mock_ticket(
            key="ECAPP-123",
            summary="Fix login bug",
            description="Users can't login with valid credentials",
            status="Open",
            priority="High",
            issue_type="Bug",
            assignee="john.doe@example.com",
            labels=["backend", "authentication"],
            components=["API"]
        ),
        create_mock_ticket(
            key="ECAPP-124",
            summary="Add dark mode",
            description="Implement dark mode toggle",
            status="Ready to Dev",
            priority="Medium",
            issue_type="Feature",
            assignee="jane.smith@example.com",
            labels=["frontend", "ui"],
            components=["UI"]
        )
    ]

    # Mock get_ticket (not get_issue) to return full issue details
    client.get_ticket.return_value = create_mock_ticket(
        key="ECAPP-123",
        summary="Fix login bug",
        description="Users can't login with valid credentials. This happens on both mobile and web.",
        status="Open",
        priority="High",
        issue_type="Bug",
        assignee="john.doe@example.com",
        labels=["backend", "authentication"],
        components=["API"]
    )

    return client


@pytest.fixture
def mock_ai_client():
    """Mock AI client with sample analysis."""
    client = MagicMock()
    client.is_available.return_value = True

    # Mock AI response
    mock_response = Mock()
    mock_response.content = """
## 1. Issue Overview
This is a critical authentication bug affecting user login functionality.

## 2. Requirements Breakdown
- Fix authentication validation logic
- Ensure credentials are properly verified
- Test on both mobile and web platforms

## 3. Technical Considerations
- Backend authentication service
- Database user verification
- Session management

## 4. Potential Challenges
- May require database schema changes
- Need to ensure backward compatibility
- Security implications must be carefully reviewed

## 5. Implementation Approach
1. Review authentication flow
2. Add unit tests for validation logic
3. Fix the bug
4. Test on all platforms

## 6. Missing Information
- Error messages users are seeing
- Frequency of the issue
- Specific platforms affected

## 7. Estimated Complexity
**High** - Involves security-critical authentication logic and multi-platform testing.
"""
    client.generate.return_value = mock_response

    return client


@pytest.fixture
def mock_ui_components():
    """Mock UI components."""
    ui = MagicMock()
    ui.text = MagicMock()
    ui.panel = MagicMock()
    ui.table = MagicMock()
    ui.spacer = MagicMock()
    return ui


@pytest.fixture
def mock_views():
    """Mock UI views."""
    views = MagicMock()
    views.prompts = MagicMock()
    views.menu = MagicMock()
    views.step_header = MagicMock()

    # Mock user selecting issue #1 (ask_int returns integer)
    views.prompts.ask_int.return_value = 1

    return views


@pytest.fixture
def workflow_context(mock_jira_client, mock_ai_client, mock_ui_components, mock_views):
    """Build workflow context with mocked dependencies."""
    secrets = SecretManager()

    ctx = WorkflowContextBuilder(
        plugin_registry=None,  # Not needed for this test
        secrets=secrets,
        ai_config=None
    ).build()

    # Inject mocked clients
    ctx.jira = mock_jira_client
    ctx.ai = mock_ai_client
    ctx.ui = mock_ui_components
    ctx.views = mock_views

    # Set workflow metadata
    ctx.workflow_name = "analyze-jira-issues"
    ctx.total_steps = 4

    return ctx


def test_workflow_step_1_search_issues(workflow_context, mock_jira_client):
    """Test step 1: Search for open issues."""
    from titan_plugin_jira.steps.search_saved_query_step import search_saved_query_step

    # Set params
    workflow_context.data["query_name"] = "open_issues"
    workflow_context.current_step = 1

    # Execute step with metadata merge
    result = execute_step_with_metadata(search_saved_query_step, workflow_context)

    # Assertions
    assert isinstance(result, Success)
    assert workflow_context.get("jira_issues") is not None
    assert workflow_context.get("jira_issue_count") == 2
    assert len(workflow_context.get("jira_issues")) == 2

    # Verify JIRA client was called
    mock_jira_client.search_tickets.assert_called_once()


def test_workflow_step_2_select_issue(workflow_context):
    """Test step 2: User selects an issue."""
    from titan_plugin_jira.steps.prompt_select_issue_step import prompt_select_issue_step

    # Setup: Populate issues from step 1
    workflow_context.data["jira_issues"] = [
        create_mock_ticket(
            key="ECAPP-123",
            summary="Fix login bug",
            status="Open",
            priority="High",
            issue_type="Bug"
        )
    ]
    workflow_context.current_step = 2

    # Mock user input (selecting issue #1) - ask_int returns integer
    workflow_context.views.prompts.ask_int.return_value = 1

    # Execute step
    result = execute_step_with_metadata(prompt_select_issue_step, workflow_context)

    # Assertions
    assert isinstance(result, Success)
    assert workflow_context.get("jira_issue_key") == "ECAPP-123"
    assert workflow_context.get("selected_issue") is not None


def test_workflow_step_3_get_issue_details(workflow_context, mock_jira_client):
    """Test step 3: Fetch full issue details."""
    from titan_plugin_jira.steps.get_issue_step import get_issue_step

    # Setup: Issue key from step 2
    workflow_context.data["jira_issue_key"] = "ECAPP-123"
    workflow_context.current_step = 3

    # Execute step
    result = execute_step_with_metadata(get_issue_step, workflow_context)

    # Assertions
    assert isinstance(result, Success)
    assert workflow_context.get("jira_issue") is not None
    assert workflow_context.get("jira_issue").key == "ECAPP-123"

    # Verify JIRA client was called with correct key (get_ticket, not get_issue)
    mock_jira_client.get_ticket.assert_called_once_with(ticket_key="ECAPP-123", expand=None)


def test_workflow_step_4_ai_analysis(workflow_context, mock_ai_client):
    """Test step 4: AI analyzes the issue."""
    from titan_plugin_jira.steps.ai_analyze_issue_step import ai_analyze_issue_requirements

    # Setup: Issue from step 3
    workflow_context.data["jira_issue"] = create_mock_ticket(
        key="ECAPP-123",
        summary="Fix login bug",
        description="Users can't login",
        status="Open",
        priority="High",
        issue_type="Bug",
        assignee="john.doe@example.com"
    )
    workflow_context.current_step = 4

    # Execute step with metadata merge
    result = execute_step_with_metadata(ai_analyze_issue_requirements, workflow_context)

    # Assertions
    assert isinstance(result, Success)
    assert workflow_context.get("ai_analysis") is not None
    assert "Issue Overview" in workflow_context.get("ai_analysis")
    assert "Requirements Breakdown" in workflow_context.get("ai_analysis")

    # Verify AI was called
    mock_ai_client.generate.assert_called_once()


def test_workflow_full_execution(workflow_context, mock_jira_client, mock_ai_client):
    """Test complete workflow execution (all 4 steps)."""
    # Import all steps
    from titan_plugin_jira.steps.search_saved_query_step import search_saved_query_step
    from titan_plugin_jira.steps.prompt_select_issue_step import prompt_select_issue_step
    from titan_plugin_jira.steps.get_issue_step import get_issue_step
    from titan_plugin_jira.steps.ai_analyze_issue_step import ai_analyze_issue_requirements

    # Step 1: Search issues
    workflow_context.data["query_name"] = "open_issues"
    workflow_context.current_step = 1
    result1 = execute_step_with_metadata(search_saved_query_step, workflow_context)
    assert isinstance(result1, Success)

    # Step 2: Select issue (mock returns 1)
    workflow_context.current_step = 2
    result2 = execute_step_with_metadata(prompt_select_issue_step, workflow_context)
    assert isinstance(result2, Success)

    # Step 3: Get issue details
    workflow_context.current_step = 3
    result3 = execute_step_with_metadata(get_issue_step, workflow_context)
    assert isinstance(result3, Success)

    # Step 4: AI analysis
    workflow_context.current_step = 4
    result4 = execute_step_with_metadata(ai_analyze_issue_requirements, workflow_context)
    assert isinstance(result4, Success)

    # Verify final state
    assert workflow_context.get("ai_analysis") is not None
    assert workflow_context.get("jira_issue").key == "ECAPP-123"


def test_workflow_ai_not_available(workflow_context):
    """Test workflow when AI is not configured."""
    from titan_plugin_jira.steps.ai_analyze_issue_step import ai_analyze_issue_requirements

    # Setup: Disable AI
    workflow_context.ai.is_available.return_value = False
    workflow_context.data["jira_issue"] = create_mock_ticket(
        key="ECAPP-123",
        summary="Fix login bug",
        status="Open"
    )
    workflow_context.current_step = 4

    # Execute step
    result = ai_analyze_issue_requirements(workflow_context)

    # Should skip when AI not available
    assert isinstance(result, Skip)


def test_workflow_no_issues_found(workflow_context, mock_jira_client):
    """Test workflow when no issues match the query."""
    from titan_plugin_jira.steps.search_saved_query_step import search_saved_query_step

    # Mock empty results
    mock_jira_client.search_tickets.return_value = []

    workflow_context.data["query_name"] = "open_issues"
    workflow_context.current_step = 1

    result = execute_step_with_metadata(search_saved_query_step, workflow_context)

    # Should succeed but with empty list
    assert isinstance(result, Success)
    assert workflow_context.get("jira_issue_count") == 0
    assert workflow_context.get("jira_issues") == []


def test_workflow_invalid_issue_selection(workflow_context):
    """Test workflow when user cancels issue selection."""
    from titan_plugin_jira.steps.prompt_select_issue_step import prompt_select_issue_step

    # Setup issues
    workflow_context.data["jira_issues"] = [
        create_mock_ticket(key="ECAPP-123", summary="Issue 1", status="Open")
    ]

    # Mock user cancelling (ask_int returns None when cancelled)
    workflow_context.views.prompts.ask_int.return_value = None
    workflow_context.current_step = 2

    result = execute_step_with_metadata(prompt_select_issue_step, workflow_context)

    # Should return error when no issue selected
    assert isinstance(result, Error)
