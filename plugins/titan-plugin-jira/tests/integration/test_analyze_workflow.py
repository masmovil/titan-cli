"""
Integration tests for the analyze-jira-issues workflow.

These tests verify the complete workflow execution with mocked JIRA API responses.
"""

import json

import pytest
from unittest.mock import MagicMock, Mock
from titan_cli.engine import WorkflowContextBuilder, Success, Error, Skip
from titan_cli.core.secrets import SecretManager
from titan_cli.core.result import ClientSuccess
from titan_plugin_jira.models import UIJiraIssue


def create_mock_ticket(**kwargs):
    """Helper to create UIJiraIssue with default values."""
    defaults = {
        "key": "TEST-123",
        "id": "12345",
        "summary": "Test summary",
        "description": "Test description",
        "status": "Open",
        "status_icon": "⚪",
        "status_category": "To Do",
        "issue_type": "Task",
        "issue_type_icon": "✅",
        "assignee": "test@example.com",
        "assignee_email": "test@example.com",
        "reporter": "reporter@example.com",
        "priority": "Medium",
        "priority_icon": "🟡",
        "formatted_created_at": "01/01/2025 00:00:00",
        "formatted_updated_at": "02/01/2025 00:00:00",
        "labels": [],
        "components": [],
        "fix_versions": [],
        "is_subtask": False,
        "parent_key": None,
        "subtask_count": 0
    }
    defaults.update(kwargs)
    return UIJiraIssue(**defaults)


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
    """Mock JIRA client with sample data (new architecture)."""
    client = MagicMock()

    # Mock search_issues to return ClientSuccess with sample issues
    issues = [
        create_mock_ticket(
            key="ECAPP-123",
            summary="Fix login bug",
            description="Users can't login with valid credentials",
            status="Open",
            status_icon="⚪",
            priority="High",
            priority_icon="🔴",
            issue_type="Bug",
            issue_type_icon="🐛",
            assignee="john.doe@example.com",
            labels=["backend", "authentication"],
            components=["API"]
        ),
        create_mock_ticket(
            key="ECAPP-124",
            summary="Add dark mode",
            description="Implement dark mode toggle",
            status="Ready to Dev",
            status_icon="⚪",
            priority="Medium",
            priority_icon="🟡",
            issue_type="Feature",
            issue_type_icon="📖",
            assignee="jane.smith@example.com",
            labels=["frontend", "ui"],
            components=["UI"]
        )
    ]
    client.search_issues.return_value = ClientSuccess(
        data=issues,
        message="Found 2 issues"
    )

    # Mock get_issue to return ClientSuccess with full issue details
    issue = create_mock_ticket(
        key="ECAPP-123",
        summary="Fix login bug",
        description="Users can't login with valid credentials. This happens on both mobile and web.",
        status="Open",
        status_icon="⚪",
        priority="High",
        priority_icon="🔴",
        issue_type="Bug",
        issue_type_icon="🐛",
        assignee="john.doe@example.com",
        labels=["backend", "authentication"],
        components=["API"]
    )
    client.get_issue.return_value = ClientSuccess(
        data=issue,
        message="Issue retrieved successfully"
    )

    return client


@pytest.fixture
def mock_ai_client():
    """
    Mock AI client answering every one of the agent's calls.

    One object serves all five: each call's contract reads only the fields it
    declared and ignores the rest. It has to be a real answer rather than prose
    - with prose every call degrades to empty defaults, and then a test claiming
    "this feature flag produced nothing" cannot tell a working flag apart from a
    response nothing could parse.
    """
    client = MagicMock()
    client.is_available.return_value = True

    mock_response = Mock()
    mock_response.content = json.dumps(
        {
            "functional": ["Fix authentication validation logic"],
            "non_functional": ["Login responds in under 200ms"],
            "acceptance_criteria": ["Valid credentials log the user in"],
            "technical_approach": "Patch the session validation path",
            "risks": ["Security regression in the auth flow"],
            "edge_cases": ["Expired session token"],
            "complexity": "High",
            "effort": "3-5 days",
            "dependencies": ["AUTH-100"],
            "subtasks": [
                {"summary": "Add unit tests", "description": "Cover the validation logic"}
            ],
        }
    )
    mock_response.usage = {"total_tokens": 100}
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

    # Mock textual UI context (required by newer steps)
    ctx.textual = MagicMock()
    ctx.textual.mount = MagicMock()
    ctx.textual.text = MagicMock()
    ctx.textual.markdown = MagicMock()
    ctx.textual.ask_confirm = MagicMock(return_value=True)
    # ask_text returns "1" for issue selection (prompt_select_issue_step expects a number)
    ctx.textual.ask_text = MagicMock(return_value="1")
    # Mock loading as a context manager
    loading_mock = MagicMock()
    loading_mock.__enter__ = MagicMock(return_value=loading_mock)
    loading_mock.__exit__ = MagicMock(return_value=None)
    ctx.textual.loading = MagicMock(return_value=loading_mock)

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
    mock_jira_client.search_issues.assert_called_once()


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


def test_get_issue_step_standalone(workflow_context, mock_jira_client):
    """Test get_issue step as standalone functionality (not part of main workflow)."""
    from titan_plugin_jira.steps.get_issue_step import get_issue_step

    # Setup: Issue key
    workflow_context.data["jira_issue_key"] = "ECAPP-123"
    workflow_context.current_step = 1

    # Execute step
    result = execute_step_with_metadata(get_issue_step, workflow_context)

    # Assertions
    assert isinstance(result, Success)
    assert workflow_context.get("jira_issue") is not None
    assert workflow_context.get("jira_issue").key == "ECAPP-123"

    # Verify JIRA client was called with correct key
    mock_jira_client.get_issue.assert_called_once_with(key="ECAPP-123", expand=None)


def test_workflow_step_3_ai_analysis(workflow_context, mock_ai_client):
    """Test step 3: AI analyzes the selected issue (uses selected_issue, not jira_issue)."""
    from titan_plugin_jira.steps.ai_analyze_issue_step import ai_analyze_issue_requirements_step

    # Setup: Use selected_issue from step 2 (not jira_issue from API call)
    workflow_context.data["selected_issue"] = create_mock_ticket(
        key="ECAPP-123",
        summary="Fix login bug",
        description="Users can't login",
        status="Open",
        priority="High",
        issue_type="Bug",
        assignee="john.doe@example.com"
    )
    workflow_context.current_step = 3

    # Execute step with metadata merge
    result = execute_step_with_metadata(ai_analyze_issue_requirements_step, workflow_context)

    # Assertions
    assert isinstance(result, Success)
    assert workflow_context.get("ai_analysis") is not None

    # Verify template was used (should contain template header)
    ai_analysis = workflow_context.get("ai_analysis")
    assert "# JIRA Issue Analysis" in ai_analysis

    # Verify structured data was saved
    structured = workflow_context.get("ai_analysis_structured")
    assert structured is not None
    assert "functional_requirements" in structured
    assert "acceptance_criteria" in structured
    assert "technical_approach" in structured


def test_workflow_full_execution(workflow_context, mock_jira_client, mock_ai_client):
    """Test complete workflow execution (3 steps: search → select → AI analyze)."""
    # Import all steps
    from titan_plugin_jira.steps.search_saved_query_step import search_saved_query_step
    from titan_plugin_jira.steps.prompt_select_issue_step import prompt_select_issue_step
    from titan_plugin_jira.steps.ai_analyze_issue_step import ai_analyze_issue_requirements_step

    # Step 1: Search issues
    workflow_context.data["query_name"] = "open_issues"
    workflow_context.current_step = 1
    result1 = execute_step_with_metadata(search_saved_query_step, workflow_context)
    assert isinstance(result1, Success)

    # Step 2: Select issue (mock returns 1)
    workflow_context.current_step = 2
    result2 = execute_step_with_metadata(prompt_select_issue_step, workflow_context)
    assert isinstance(result2, Success)

    # Step 3: AI analysis (uses selected_issue directly, no API call)
    workflow_context.current_step = 3
    result3 = execute_step_with_metadata(ai_analyze_issue_requirements_step, workflow_context)
    assert isinstance(result3, Success)

    # Verify final state
    assert workflow_context.get("ai_analysis") is not None
    assert workflow_context.get("selected_issue").key == "ECAPP-123"
    # Verify template header is present
    assert "# JIRA Issue Analysis" in workflow_context.get("ai_analysis")


def test_workflow_ai_not_available(workflow_context):
    """Test workflow when AI is not configured."""
    from titan_plugin_jira.steps.ai_analyze_issue_step import ai_analyze_issue_requirements_step

    # Setup: Disable AI
    workflow_context.ai.is_available.return_value = False
    workflow_context.data["jira_issue"] = create_mock_ticket(
        key="ECAPP-123",
        summary="Fix login bug",
        status="Open"
    )
    workflow_context.current_step = 4

    # Execute step
    result = ai_analyze_issue_requirements_step(workflow_context)

    # Should skip when AI not available
    assert isinstance(result, Skip)


def test_workflow_no_issues_found(workflow_context, mock_jira_client):
    """Test workflow when no issues match the query."""
    from titan_plugin_jira.steps.search_saved_query_step import search_saved_query_step

    # Mock empty results
    mock_jira_client.search_issues.return_value = ClientSuccess(
        data=[],
        message="Found 0 issues"
    )

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

    # Mock user cancelling (ask_text returns empty string when cancelled)
    workflow_context.textual.ask_text.return_value = ""
    workflow_context.current_step = 2

    result = execute_step_with_metadata(prompt_select_issue_step, workflow_context)

    # Should return error when no issue selected
    assert isinstance(result, Error)


def test_formatter_with_template():
    """Test that formatter uses Jinja2 template when available."""
    from titan_plugin_jira.formatters import IssueAnalysisMarkdownFormatter
    from titan_plugin_jira.agents.jira_agent import IssueAnalysis

    # Create formatter with template
    formatter = IssueAnalysisMarkdownFormatter(template_path="issue_analysis.md.j2")
    assert formatter.template is not None

    # Create sample analysis
    analysis = IssueAnalysis(
        functional_requirements=["FR1: User authentication", "FR2: Password reset"],
        acceptance_criteria=["User can login", "User can reset password"],
        technical_approach="Use JWT tokens for auth",
        complexity_score="medium",
        estimated_effort="3-5 days"
    )

    # Format the analysis
    output = formatter.format(analysis)

    # Verify template was used (contains template header)
    assert "# JIRA Issue Analysis" in output
    # Verify content is present
    assert "FR1: User authentication" in output
    assert "User can login" in output
    assert "JWT tokens" in output


def test_formatter_without_template():
    """Test that formatter falls back to built-in when template not found."""
    from titan_plugin_jira.formatters import IssueAnalysisMarkdownFormatter
    from titan_plugin_jira.agents.jira_agent import IssueAnalysis

    # Create formatter without template (will use fallback)
    formatter = IssueAnalysisMarkdownFormatter(template_path="nonexistent.md.j2")
    assert formatter.template is None  # Template should fail to load

    # Create sample analysis
    analysis = IssueAnalysis(
        functional_requirements=["FR1: User authentication"],
        acceptance_criteria=["User can login"],
        technical_approach="Use JWT tokens",
        complexity_score="medium"
    )

    # Format the analysis
    output = formatter.format(analysis)

    # Verify built-in formatter was used (uses ## headers, not # header)
    assert output.startswith("\n## 1. Requirements Breakdown") or "## 1. Requirements Breakdown" in output
    # Verify content is present with built-in format
    assert "Requirements Breakdown" in output
    assert "FR1: User authentication" in output
    assert "Acceptance Criteria" in output


def test_formatter_no_template_specified():
    """Test that formatter uses built-in when no template specified."""
    from titan_plugin_jira.formatters import IssueAnalysisMarkdownFormatter
    from titan_plugin_jira.agents.jira_agent import IssueAnalysis

    # Create formatter with no template
    formatter = IssueAnalysisMarkdownFormatter()
    assert formatter.template is None

    # Create sample analysis
    analysis = IssueAnalysis(
        functional_requirements=["FR1: Test requirement"],
        complexity_score="low"
    )

    # Format the analysis
    output = formatter.format(analysis)

    # Verify built-in formatter was used
    assert "Requirements Breakdown" in output
    assert "FR1: Test requirement" in output


def test_agent_feature_flag_requirement_extraction(mock_ai_client, mock_jira_client):
    """Test that enable_requirement_extraction flag controls requirement extraction."""
    from titan_plugin_jira.agents.jira_agent import JiraAgent, IssueAnalysis
    from titan_plugin_jira.agents.config_loader import JiraAgentConfig

    # Create config with requirement extraction disabled
    config = JiraAgentConfig(
        name="JiraAgent",
        enable_requirement_extraction=False,  # Disabled
        enable_risk_analysis=True,
        enable_subtasks=True,
        enable_dependency_detection=True,
        max_description_length=8000,
        max_tokens=2000,
        temperature=0.3
    )

    # Create agent with custom config
    agent = JiraAgent(mock_ai_client, mock_jira_client)
    agent.config = config  # Override config

    # Analyze issue
    analysis = agent.analyze_issue("TEST-123", include_subtasks=True)

    # Verify requirements were NOT extracted (should be empty)
    assert isinstance(analysis, IssueAnalysis)
    assert len(analysis.functional_requirements) == 0
    assert len(analysis.non_functional_requirements) == 0
    assert len(analysis.acceptance_criteria) == 0

    # The flags left enabled did produce something. Without this the test would
    # also pass if nothing were ever parsed, which is what it used to do.
    assert len(analysis.risks) > 0
    assert len(analysis.dependencies) > 0


def test_agent_feature_flag_risk_analysis(mock_ai_client, mock_jira_client):
    """Test that enable_risk_analysis flag controls risk analysis."""
    from titan_plugin_jira.agents.jira_agent import JiraAgent, IssueAnalysis
    from titan_plugin_jira.agents.config_loader import JiraAgentConfig

    # Create config with risk analysis disabled
    config = JiraAgentConfig(
        name="JiraAgent",
        enable_requirement_extraction=True,
        enable_risk_analysis=False,  # Disabled
        enable_subtasks=True,
        enable_dependency_detection=True,
        max_description_length=8000,
        max_tokens=2000,
        temperature=0.3
    )

    # Create agent with custom config
    agent = JiraAgent(mock_ai_client, mock_jira_client)
    agent.config = config

    # Analyze issue
    analysis = agent.analyze_issue("TEST-123", include_subtasks=True)

    # Verify risks were NOT analyzed (should be empty)
    assert isinstance(analysis, IssueAnalysis)
    assert len(analysis.risks) == 0
    assert len(analysis.edge_cases) == 0
    assert analysis.complexity_score is None
    assert analysis.estimated_effort is None


def test_agent_feature_flag_subtask_suggestion(mock_ai_client, mock_jira_client):
    """Test that enable_subtasks flag controls subtask generation."""
    from titan_plugin_jira.agents.jira_agent import JiraAgent, IssueAnalysis
    from titan_plugin_jira.agents.config_loader import JiraAgentConfig

    # Create config with subtask suggestion disabled
    config = JiraAgentConfig(
        name="JiraAgent",
        enable_requirement_extraction=True,
        enable_risk_analysis=True,
        enable_subtasks=False,  # Disabled
        enable_dependency_detection=True,
        max_description_length=8000,
        max_tokens=2000,
        temperature=0.3
    )

    # Create agent with custom config
    agent = JiraAgent(mock_ai_client, mock_jira_client)
    agent.config = config

    # Analyze issue WITH include_subtasks=True
    analysis = agent.analyze_issue("TEST-123", include_subtasks=True)

    # Verify subtasks were NOT generated (should be empty)
    assert isinstance(analysis, IssueAnalysis)
    assert len(analysis.suggested_subtasks) == 0


def test_agent_feature_flag_dependency_detection(mock_ai_client, mock_jira_client):
    """Test that enable_dependency_detection flag controls dependency detection."""
    from titan_plugin_jira.agents.jira_agent import JiraAgent, IssueAnalysis
    from titan_plugin_jira.agents.config_loader import JiraAgentConfig

    # Create config with dependency detection disabled
    config = JiraAgentConfig(
        name="JiraAgent",
        enable_requirement_extraction=True,
        enable_risk_analysis=True,
        enable_subtasks=True,
        enable_dependency_detection=False,  # Disabled
        max_description_length=8000,
        max_tokens=2000,
        temperature=0.3
    )

    # Create agent with custom config
    agent = JiraAgent(mock_ai_client, mock_jira_client)
    agent.config = config

    # Analyze issue
    analysis = agent.analyze_issue("TEST-123", include_subtasks=True)

    # Verify dependencies were NOT detected (should be empty)
    assert isinstance(analysis, IssueAnalysis)
    assert len(analysis.dependencies) == 0


def test_agent_feature_flags_all_disabled(mock_ai_client, mock_jira_client):
    """Test that all feature flags can be disabled simultaneously."""
    from titan_plugin_jira.agents.jira_agent import JiraAgent, IssueAnalysis
    from titan_plugin_jira.agents.config_loader import JiraAgentConfig

    # Create config with ALL features disabled
    config = JiraAgentConfig(
        name="JiraAgent",
        enable_requirement_extraction=False,
        enable_risk_analysis=False,
        enable_subtasks=False,
        enable_dependency_detection=False,
        max_description_length=8000,
        max_tokens=2000,
        temperature=0.3
    )

    # Create agent with custom config
    agent = JiraAgent(mock_ai_client, mock_jira_client)
    agent.config = config

    # Analyze issue
    analysis = agent.analyze_issue("TEST-123", include_subtasks=True)

    # Verify ALL features are disabled (empty analysis)
    assert isinstance(analysis, IssueAnalysis)
    assert len(analysis.functional_requirements) == 0
    assert len(analysis.non_functional_requirements) == 0
    assert len(analysis.acceptance_criteria) == 0
    assert len(analysis.risks) == 0
    assert len(analysis.edge_cases) == 0
    assert len(analysis.dependencies) == 0
    assert len(analysis.suggested_subtasks) == 0
    assert analysis.complexity_score is None
    assert analysis.estimated_effort is None


# New tests for workflow YAML structure (TESTING.md Section 7)

def test_workflow_yaml_structure():
    """Test that workflow YAML has correct structure after removing get_issue step."""
    import yaml
    from pathlib import Path

    # Path relative to this test file
    workflow_path = Path(__file__).parent.parent.parent / "titan_plugin_jira" / "workflows" / "analyze-jira-issues.yaml"
    with open(workflow_path) as f:
        workflow = yaml.safe_load(f)

    # Verify basic structure
    assert workflow["name"] == "Analyze JIRA Open and Ready to Dev Issues"
    assert "steps" in workflow

    # Verify step count (should be 3, not 4 - get_issue was removed)
    steps = workflow["steps"]
    assert len(steps) == 3, \
        f"Expected 3 steps after removing get_issue, got {len(steps)}"

    # Verify step IDs
    step_ids = [s["id"] for s in steps]
    assert step_ids == [
        "search_open_issues",
        "prompt_select_issue",
        "ai_analyze_issue"  # No get_issue_details anymore
    ], f"Unexpected step IDs: {step_ids}"

    # Verify ai_analyze_issue doesn't require jira_issue
    # (it uses selected_issue from prompt_select_issue instead)
    ai_step = next(s for s in steps if s["id"] == "ai_analyze_issue")
    requires = ai_step.get("requires", [])
    assert "jira_issue" not in requires, \
        "ai_analyze_issue should not require jira_issue (uses selected_issue instead)"


def test_workflow_data_flow_without_get_issue():
    """Test that data flows correctly without the get_issue step."""
    from titan_plugin_jira.steps.search_saved_query_step import search_saved_query_step
    from titan_plugin_jira.steps.prompt_select_issue_step import prompt_select_issue_step
    from titan_plugin_jira.steps.ai_analyze_issue_step import ai_analyze_issue_requirements_step
    from unittest.mock import Mock

    # Create context
    mock_jira = Mock()
    mock_ai = Mock()
    mock_textual = Mock()

    # Mock Jira search
    issues = [
        create_mock_ticket(key="ECAPP-123", summary="Bug 1"),
        create_mock_ticket(key="ECAPP-124", summary="Bug 2"),
    ]
    mock_jira.search_issues.return_value = ClientSuccess(data=issues)

    # Mock AI
    mock_ai.is_available.return_value = True
    mock_response = Mock()
    mock_response.content = "AI analysis result"
    mock_ai.generate.return_value = mock_response

    # Mock textual input (user selects first issue)
    mock_textual.ask_text.return_value = "1"
    mock_textual.begin_step = Mock()
    mock_textual.end_step = Mock()
    mock_textual.loading = Mock()
    mock_textual.loading.return_value.__enter__ = Mock()
    mock_textual.loading.return_value.__exit__ = Mock()
    mock_textual.text = Mock()
    mock_textual.success_text = Mock()
    mock_textual.bold_text = Mock()
    mock_textual.dim_text = Mock()
    mock_textual.mount = Mock()

    ctx = Mock()
    ctx.data = {}
    ctx.get = lambda key, default=None: ctx.data.get(key, default)
    ctx.jira = mock_jira
    ctx.ai = mock_ai
    ctx.textual = mock_textual

    # Mock plugin_manager (needed for saved queries lookup)
    mock_plugin = Mock()
    mock_config = Mock()
    mock_config.saved_queries = None  # No custom queries
    mock_plugin._config = mock_config
    mock_plugin_manager = Mock()
    mock_plugin_manager.get_plugin.return_value = mock_plugin
    ctx.plugin_manager = mock_plugin_manager

    # Step 1: Search
    ctx.data["query_name"] = "open_issues"
    result1 = search_saved_query_step(ctx)
    assert isinstance(result1, Success)
    ctx.data.update(result1.metadata)

    # Verify jira_issues is available
    assert "jira_issues" in ctx.data
    assert len(ctx.data["jira_issues"]) == 2

    # Step 2: Select (no get_issue step needed!)
    result2 = prompt_select_issue_step(ctx)
    assert isinstance(result2, Success)
    ctx.data.update(result2.metadata)

    # Verify selected_issue is available (from prompt_select_issue)
    assert "selected_issue" in ctx.data, \
        "selected_issue should be available from prompt_select_issue"
    assert ctx.data["selected_issue"].key == "ECAPP-123"

    # Mock get_issue for AI agent (agent needs full issue data)
    full_issue = create_mock_ticket(key="ECAPP-123", summary="Bug 1")
    mock_jira.get_issue.return_value = ClientSuccess(data=full_issue)

    # Step 3: AI analyze (uses selected_issue to get key, then agent fetches full data)
    result3 = ai_analyze_issue_requirements_step(ctx)
    assert isinstance(result3, Success)

    # The workflow completes successfully. The get_issue_details STEP was removed
    # (which was redundant), but the AI agent still fetches the issue internally
    # for full analysis. This is expected - the optimization was removing the
    # intermediate step, not the agent's internal fetch.
    mock_jira.get_issue.assert_called_once_with("ECAPP-123")


def test_workflow_params_structure():
    """Test that workflow params are correctly defined."""
    import yaml
    from pathlib import Path

    # Path relative to this test file
    workflow_path = Path(__file__).parent.parent.parent / "titan_plugin_jira" / "workflows" / "analyze-jira-issues.yaml"
    with open(workflow_path) as f:
        workflow = yaml.safe_load(f)

    # Verify params
    if "params" in workflow:
        params = workflow["params"]
        # Check expected params
        assert "query_name" in params, "query_name param should be defined"
