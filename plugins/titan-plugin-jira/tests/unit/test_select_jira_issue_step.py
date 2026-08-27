"""
Unit tests for select_jira_issue_step

Covers the three issue-selection modes: plain number, full key, and the Ready to Dev list + pick.
"""

from titan_cli.engine import Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_jira.steps.select_jira_issue_step import select_jira_issue_step


def test_numeric_input_composes_with_default_project(mock_workflow_context, mock_jira_client_new):
    """A plain number is composed with ctx.jira.project_key into a full issue key"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    mock_workflow_context.textual.ask_text.return_value = "123"

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Success)
    assert result.metadata["jira_issue_key"] == "TEST-123"


def test_numeric_input_without_default_project_fails(mock_workflow_context, mock_jira_client_new):
    """A plain number with no default project configured cannot be resolved"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = None
    mock_workflow_context.textual.ask_text.return_value = "123"

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)
    assert "default jira project" in result.message.lower()


def test_full_key_input_used_as_is(mock_workflow_context, mock_jira_client_new):
    """A full key (e.g. from another board) is used directly, uppercased"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    mock_workflow_context.textual.ask_text.return_value = "otherproj-45"

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Success)
    assert result.metadata["jira_issue_key"] == "OTHERPROJ-45"


def test_invalid_input_format_fails(mock_workflow_context, mock_jira_client_new):
    """Input that's neither a number nor a full key is rejected"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    mock_workflow_context.textual.ask_text.return_value = "not a key"

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)
    assert "invalid issue key format" in result.message.lower()


def test_no_jira_client(mock_workflow_context):
    """No JIRA client available"""
    mock_workflow_context.jira = None

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)


def test_empty_input_lists_ready_to_dev_and_selects(mock_workflow_context, mock_jira_client_new, sample_ui_issue):
    """Leaving the input empty lists Ready to Dev issues, then picks from the results"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    # 1st ask_text -> empty (list Ready to Dev), 2nd -> selection index
    mock_workflow_context.textual.ask_text.side_effect = ["", "1"]

    mock_jira_client_new.search_issues.return_value = ClientSuccess(
        data=[sample_ui_issue],
        message="Found 1 issues"
    )

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Success)
    assert result.metadata["jira_issue_key"] == sample_ui_issue.key
    assert result.metadata["selected_issue"] == sample_ui_issue
    mock_jira_client_new.search_issues.assert_called_once()
    called_kwargs = mock_jira_client_new.search_issues.call_args.kwargs
    assert "TEST" in called_kwargs["jql"]
    assert "Ready to Dev" in called_kwargs["jql"]


def test_empty_input_without_default_project_fails(mock_workflow_context, mock_jira_client_new):
    """Empty input with no default project configured cannot list Ready to Dev issues"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = None
    mock_workflow_context.textual.ask_text.return_value = ""

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)
    assert "default jira project" in result.message.lower()


def test_search_with_no_results_fails(mock_workflow_context, mock_jira_client_new):
    """Ready to Dev list with no matching issues is an error"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    mock_workflow_context.textual.ask_text.return_value = ""

    mock_jira_client_new.search_issues.return_value = ClientSuccess(data=[], message="Found 0 issues")

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)
    assert "no ready to dev issues found" in result.message.lower()


def test_search_failure_returns_error(mock_workflow_context, mock_jira_client_new):
    """A failed search call surfaces as an Error"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    mock_workflow_context.textual.ask_text.return_value = ""

    mock_jira_client_new.search_issues.return_value = ClientError(
        error_message="Invalid JQL",
        error_code="SEARCH_ERROR"
    )

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)


def test_search_selection_out_of_range_fails(mock_workflow_context, mock_jira_client_new, sample_ui_issue):
    """Selecting an index outside the result list is an error"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    mock_workflow_context.textual.ask_text.side_effect = ["", "5"]

    mock_jira_client_new.search_issues.return_value = ClientSuccess(
        data=[sample_ui_issue],
        message="Found 1 issues"
    )

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)
    assert "invalid selection" in result.message.lower()


def test_search_selection_not_a_number_fails(mock_workflow_context, mock_jira_client_new, sample_ui_issue):
    """Selecting with non-numeric input is an error"""
    mock_workflow_context.jira = mock_jira_client_new
    mock_jira_client_new.project_key = "TEST"
    mock_workflow_context.textual.ask_text.side_effect = ["", "abc"]

    mock_jira_client_new.search_issues.return_value = ClientSuccess(
        data=[sample_ui_issue],
        message="Found 1 issues"
    )

    result = select_jira_issue_step(mock_workflow_context)

    assert isinstance(result, Error)
    assert "not a number" in result.message.lower()
