import pytest
from unittest.mock import MagicMock, patch
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.core.secrets import SecretManager
from titan_plugin_github.steps.github_prompt_steps import (
    prompt_for_issue_body_step,
    prompt_for_labels_step,
    prompt_for_pr_draft_step,
    prompt_for_self_assign_step,
)
from titan_plugin_github.steps.issue_steps import ai_suggest_issue_title_and_body_step, create_issue_steps
from titan_plugin_github.steps.preview_step import preview_and_confirm_issue_step
from titan_plugin_github.models.view import UIIssue

@pytest.fixture
def mock_secret_manager():
    return MagicMock(spec=SecretManager)

def test_prompt_for_issue_body_step(mock_secret_manager):
    # Arrange
    ctx = WorkflowContext(data={})
    ctx.textual = MagicMock()
    ctx.textual.ask_multiline.return_value = "Test issue body"

    # Act
    result = prompt_for_issue_body_step(ctx)
    ctx.data.update(result.metadata)

    # Assert
    assert isinstance(result, Success)
    assert ctx.get("issue_body") == "Test issue body"
    ctx.textual.begin_step.assert_called_once()
    ctx.textual.end_step.assert_called_once_with("success")

@patch("titan_plugin_github.steps.issue_steps.IssueGeneratorAgent")
def test_ai_suggest_issue_title_and_body(MockIssueGeneratorAgent, mock_secret_manager):
    # Arrange
    mock_issue_generator = MockIssueGeneratorAgent.return_value
    mock_issue_generator.generate_issue.return_value = {
        "title": "feat: Test Feature",
        "body": "Test Body",
        "category": "feature",
        "labels": ["feature"],
        "template_used": True,
        "tokens_used": 450,
        "complexity": "moderate"
    }
    ctx = WorkflowContext(data={"issue_body": "Test issue body"})
    ctx.ai = MagicMock()
    ctx.textual = MagicMock()
    # Mock ai_content_review_flow to return (choice, title, body)
    ctx.textual.ai_content_review_flow.return_value = ("use", "feat: Test Feature", "Test Body")

    # Act
    result = ai_suggest_issue_title_and_body_step(ctx)

    # Assert
    assert isinstance(result, Success)
    assert ctx.get("issue_title") == "feat: Test Feature"
    assert ctx.get("issue_body") == "Test Body"
    assert ctx.get("issue_category") == "feature"
    assert ctx.get("labels") == ["feature"]
    assert "feature" in result.message

def test_ai_suggest_issue_title_and_body_bug_category(mock_secret_manager):
    # Arrange
    with patch("titan_plugin_github.steps.issue_steps.IssueGeneratorAgent") as MockIssueGeneratorAgent:
        mock_issue_generator = MockIssueGeneratorAgent.return_value
        mock_issue_generator.generate_issue.return_value = {
            "title": "fix: Test Bug Fix",
            "body": "Bug description",
            "category": "bug",
            "labels": ["bug"],
            "template_used": True,
            "tokens_used": 380,
            "complexity": "simple"
        }
        ctx = WorkflowContext(data={"issue_body": "Something is broken"})
        ctx.ai = MagicMock()
        ctx.textual = MagicMock()
        # Mock ai_content_review_flow to return (choice, title, body)
        ctx.textual.ai_content_review_flow.return_value = ("use", "fix: Test Bug Fix", "Bug description")

        # Act
        result = ai_suggest_issue_title_and_body_step(ctx)

        # Assert
        assert isinstance(result, Success)
        assert ctx.get("issue_category") == "bug"
        assert ctx.get("labels") == ["bug"]

def test_ai_suggest_issue_title_and_body_without_template(mock_secret_manager):
    # Arrange
    with patch("titan_plugin_github.steps.issue_steps.IssueGeneratorAgent") as MockIssueGeneratorAgent:
        mock_issue_generator = MockIssueGeneratorAgent.return_value
        mock_issue_generator.generate_issue.return_value = {
            "title": "chore: Update dependencies",
            "body": "Chore description",
            "category": "chore",
            "labels": ["chore", "maintenance"],
            "template_used": False,  # No template found
            "tokens_used": 320,
            "complexity": "simple"
        }
        ctx = WorkflowContext(data={"issue_body": "Update deps"})
        ctx.ai = MagicMock()
        ctx.textual = MagicMock()
        # Mock ai_content_review_flow to return (choice, title, body)
        ctx.textual.ai_content_review_flow.return_value = ("use", "chore: Update dependencies", "Chore description")

        # Act
        result = ai_suggest_issue_title_and_body_step(ctx)

        # Assert
        assert isinstance(result, Success)
        assert ctx.get("issue_category") == "chore"
        assert ctx.get("labels") == ["chore", "maintenance"]

def test_preview_and_confirm_issue_step(mock_secret_manager):
    # Arrange
    ctx = WorkflowContext(data={"issue_title": "Test Title", "issue_body": "Test Body"})
    ctx.textual = MagicMock()
    ctx.textual.ask_confirm.return_value = True

    # Act
    result = preview_and_confirm_issue_step(ctx)

    # Assert
    assert isinstance(result, Success)

def test_prompt_for_self_assign_step(mock_secret_manager):
    # Arrange
    ctx = WorkflowContext(data={})
    ctx.github = MagicMock()
    ctx.textual = MagicMock()
    ctx.github.get_current_user.return_value = ClientSuccess(data="testuser", message="User retrieved")
    ctx.textual.ask_confirm.return_value = True

    # Act
    result = prompt_for_self_assign_step(ctx)
    if result.metadata:
        ctx.data.update(result.metadata)

    # Assert
    assert isinstance(result, Success)
    assert ctx.get("assignees") == ["testuser"]


def test_prompt_for_pr_draft_step_uses_true_without_prompt(mock_secret_manager):
    # Arrange
    ctx = WorkflowContext(data={"draft": True})
    ctx.textual = MagicMock()

    # Act
    result = prompt_for_pr_draft_step(ctx)
    if result.metadata:
        ctx.data.update(result.metadata)

    # Assert
    assert isinstance(result, Success)
    assert ctx.get("pr_is_draft") is True
    ctx.textual.ask_confirm.assert_not_called()


def test_prompt_for_pr_draft_step_uses_false_without_prompt(mock_secret_manager):
    # Arrange
    ctx = WorkflowContext(data={"draft": False})
    ctx.textual = MagicMock()

    # Act
    result = prompt_for_pr_draft_step(ctx)
    if result.metadata:
        ctx.data.update(result.metadata)

    # Assert
    assert isinstance(result, Success)
    assert ctx.get("pr_is_draft") is False
    ctx.textual.ask_confirm.assert_not_called()


def test_prompt_for_pr_draft_step_asks_when_unset(mock_secret_manager):
    # Arrange
    ctx = WorkflowContext(data={"draft": None})
    ctx.textual = MagicMock()
    ctx.textual.ask_confirm.return_value = True

    # Act
    result = prompt_for_pr_draft_step(ctx)
    if result.metadata:
        ctx.data.update(result.metadata)

    # Assert
    assert isinstance(result, Success)
    assert ctx.get("pr_is_draft") is True
    ctx.textual.ask_confirm.assert_called_once_with(
        "Create this pull request as draft?",
        default=False,
    )


def test_prompt_for_labels_step_uses_multiselect_and_output_key(mock_secret_manager):
    ctx = WorkflowContext(
        data={
            "output_key": "pr_labels",
            "prompt": "Select labels for this pull request:",
            "pr_labels": ["feature"],
        },
    )
    ctx.github = MagicMock()
    ctx.textual = MagicMock()
    ctx.github.list_labels.return_value = ClientSuccess(
        data=["bug", "feature", "docs"],
        message="Labels retrieved",
    )
    ctx.textual.ask_multiselect.return_value = ["bug", "feature"]

    result = prompt_for_labels_step(ctx)
    if result.metadata:
        ctx.data.update(result.metadata)

    assert isinstance(result, Success)
    assert ctx.get("pr_labels") == ["bug", "feature"]
    ctx.textual.ask_multiselect.assert_called_once()


def test_prompt_for_labels_step_skips_when_repo_has_no_labels(mock_secret_manager):
    from titan_cli.engine.results import Skip

    ctx = WorkflowContext(data={})
    ctx.github = MagicMock()
    ctx.textual = MagicMock()
    ctx.github.list_labels.return_value = ClientSuccess(data=[], message="No labels")

    result = prompt_for_labels_step(ctx)

    assert isinstance(result, Skip)

@patch("titan_plugin_github.clients.github_client.GitHubClient")
def test_create_issue_step(MockGitHubClient, mock_secret_manager):
    # Arrange
    mock_github_client = MockGitHubClient()
    mock_ui_issue = UIIssue(
        number=1,
        title="Test NetworkIssue",
        body="This is a test issue",
        state="open",
        author_name="testuser",
        labels=[],
        status_icon="⚪",
        formatted_created_at="",
        formatted_updated_at="",
    )
    mock_github_client.create_issue.return_value = ClientSuccess(data=mock_ui_issue, message="Issue created")
    mock_github_client.list_labels.return_value = ClientSuccess(data=["bug", "feature", "improvement"], message="Labels retrieved")

    ctx = WorkflowContext(data={"issue_title": "Test Title", "issue_body": "Test Body", "assignees": ["testuser"], "labels": ["bug"]})
    ctx.github = mock_github_client
    ctx.textual = MagicMock()

    # Act
    result = create_issue_steps(ctx)
    if result and result.metadata:
        ctx.data.update(result.metadata)

    # Assert
    assert isinstance(result, Success)
    assert result.message == "Successfully created issue #1"
    assert ctx.get("issue") == mock_ui_issue
    mock_github_client.create_issue.assert_called_once_with(
        title="Test Title",
        body="Test Body",
        assignees=["testuser"],
        labels=["bug"],
    )

def test_create_issue_with_auto_assigned_labels(mock_secret_manager):
    # Arrange
    with patch("titan_plugin_github.clients.github_client.GitHubClient") as MockGitHubClient:
        mock_github_client = MockGitHubClient()
        mock_ui_issue = UIIssue(
            number=2,
            title="feat: New Feature",
            body="Feature description",
            state="open",
            author_name="testuser",
            labels=["feature"],
            status_icon="⚪",
            formatted_created_at="",
            formatted_updated_at="",
        )
        mock_github_client.create_issue.return_value = ClientSuccess(data=mock_ui_issue, message="Issue created")
        mock_github_client.list_labels.return_value = ClientSuccess(data=["bug", "feature", "improvement"], message="Labels retrieved")

        # Labels auto-assigned by AI categorization
        ctx = WorkflowContext(
            data={
                "issue_title": "feat: New Feature",
                "issue_body": "Feature description",
                "assignees": [],
                "labels": ["feature"]  # Auto-assigned
            }
        )
        ctx.github = mock_github_client
        ctx.textual = MagicMock()

        # Act
        result = create_issue_steps(ctx)
        if result and result.metadata:
            ctx.data.update(result.metadata)

        # Assert
        assert isinstance(result, Success)
        mock_github_client.create_issue.assert_called_once_with(
            title="feat: New Feature",
            body="Feature description",
            assignees=[],
            labels=["feature"],
        )

# ============================================================================
# JSON Parsing Tests
# ============================================================================

def test_issue_contract_maps_the_legacy_description_label_to_body():
    """The pre-JSON format called it DESCRIPTION; this agent calls it body."""
    from titan_plugin_github.agents.issue_generator import ISSUE_CONTRACT

    result = ISSUE_CONTRACT.parse(
        "CATEGORY: feature\n"
        "TITLE: feat(api): add new endpoint\n"
        "DESCRIPTION:\n## Summary\nNew API endpoint for user management"
    )

    assert result.ok
    assert result.data["category"] == "feature"
    assert result.data["title"] == "feat(api): add new endpoint"
    assert "Summary" in result.data["body"]


def test_an_unknown_category_falls_back_to_feature():
    """Only categories this agent has a template for are usable."""
    from unittest.mock import MagicMock

    from titan_plugin_github.agents.issue_generator import IssueGeneratorAgent

    agent = IssueGeneratorAgent(MagicMock())

    normalized = agent._normalize({"category": "epic", "title": "t", "body": "b"})

    assert normalized["category"] == "feature"


def test_a_known_category_is_kept_and_lowercased():
    from unittest.mock import MagicMock

    from titan_plugin_github.agents.issue_generator import IssueGeneratorAgent

    agent = IssueGeneratorAgent(MagicMock())

    normalized = agent._normalize({"category": "BUG", "title": "t", "body": "b"})

    assert normalized["category"] == "bug"


def test_an_empty_answer_gets_usable_placeholders():
    from unittest.mock import MagicMock

    from titan_plugin_github.agents.issue_generator import IssueGeneratorAgent

    agent = IssueGeneratorAgent(MagicMock())

    normalized = agent._normalize({"category": None, "title": None, "body": None})

    assert normalized == {"category": "feature", "title": "New issue", "body": ""}

# ============================================================================
# Error Scenario Tests
# ============================================================================

@patch("titan_plugin_github.steps.issue_steps.IssueGeneratorAgent")
def test_ai_suggest_issue_when_ai_client_fails(MockIssueGeneratorAgent, mock_secret_manager):
    """Test behavior when AI client raises exception"""
    # Arrange
    mock_issue_generator = MockIssueGeneratorAgent.return_value
    mock_issue_generator.generate_issue.side_effect = Exception("API Error")

    ctx = WorkflowContext(data={"issue_body": "Test issue body"})
    ctx.ai = MagicMock()
    ctx.textual = MagicMock()

    # Act
    result = ai_suggest_issue_title_and_body_step(ctx)

    # Assert
    assert isinstance(result, Error)
    assert "Failed to generate issue" in result.message
    assert "API Error" in result.message

@patch("titan_plugin_github.steps.issue_steps.IssueGeneratorAgent")
def test_ai_suggest_issue_with_malformed_response(MockIssueGeneratorAgent, mock_secret_manager):
    """Test behavior when AI returns malformed response missing required keys"""
    # Arrange
    mock_issue_generator = MockIssueGeneratorAgent.return_value
    # Malformed response - missing required keys like "title" or "body"
    mock_issue_generator.generate_issue.return_value = {
        "category": "bug"
        # Missing: title, body, labels
    }

    ctx = WorkflowContext(data={"issue_body": "Test issue body"})
    ctx.ai = MagicMock()
    ctx.textual = MagicMock()

    # Act
    result = ai_suggest_issue_title_and_body_step(ctx)

    # Assert
    assert isinstance(result, Error)
    assert "Failed to generate issue" in result.message

@patch("titan_plugin_github.clients.github_client.GitHubClient")
def test_create_issue_with_invalid_labels(MockGitHubClient, mock_secret_manager):
    """Test behavior when labels don't exist in repository - they should be filtered out"""
    # Arrange
    mock_github_client = MockGitHubClient()
    mock_github_client.list_labels.return_value = ClientSuccess(data=["bug", "feature", "improvement"], message="Labels retrieved")
    mock_ui_issue = UIIssue(
        number=3,
        title="Test Title",
        body="Test Body",
        state="open",
        author_name="testuser",
        labels=[],  # No labels since invalid ones were filtered
        status_icon="⚪",
        formatted_created_at="",
        formatted_updated_at="",
    )
    mock_github_client.create_issue.return_value = ClientSuccess(data=mock_ui_issue, message="Issue created")

    ctx = WorkflowContext(
        data={
            "issue_title": "Test Title",
            "issue_body": "Test Body",
            "assignees": [],
            "labels": ["invalid-label", "nonexistent"]  # Labels that don't exist
        }
    )
    ctx.github = mock_github_client
    ctx.textual = MagicMock()

    # Act
    result = create_issue_steps(ctx)

    # Assert
    # The step should succeed but filter out invalid labels
    assert isinstance(result, Success)
    # Verify create_issue was called with empty labels (invalid ones filtered)
    mock_github_client.create_issue.assert_called_once_with(
        title="Test Title",
        body="Test Body",
        assignees=[],
        labels=[],  # Invalid labels filtered out
    )

@patch("titan_plugin_github.clients.github_client.GitHubClient")
def test_create_issue_when_github_api_fails(MockGitHubClient, mock_secret_manager):
    """Test behavior when GitHub API fails to create issue"""
    # Arrange
    mock_github_client = MockGitHubClient()
    mock_github_client.list_labels.return_value = ClientSuccess(data=["bug", "feature"], message="Labels retrieved")
    mock_github_client.create_issue.return_value = ClientError(
        error_message="GitHub API Error",
        error_code="API_ERROR"
    )

    ctx = WorkflowContext(
        data={
            "issue_title": "Test Title",
            "issue_body": "Test Body",
            "assignees": [],
            "labels": ["bug"]
        }
    )
    ctx.github = mock_github_client
    ctx.textual = MagicMock()

    # Act
    result = create_issue_steps(ctx)

    # Assert
    assert isinstance(result, Error)
    assert "Failed to create issue" in result.message
    assert "GitHub API Error" in result.message
