# tests/engine/test_create_pr_workflow.py
import pytest
from unittest.mock import MagicMock
from pathlib import Path
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.engine.workflow_executor import WorkflowExecutor
from titan_cli.engine import WorkflowContextBuilder, Success
from titan_cli.core.plugins.plugin_registry import PluginRegistry
from titan_cli.core.workflows.workflow_registry import WorkflowRegistry, ParsedWorkflow

@pytest.fixture
def mock_titan_config():
    """Fixture for a mocked TitanConfig object."""
    mock_config = MagicMock(spec=TitanConfig)
    
    # Mock the nested attributes that will be accessed
    mock_config.config = MagicMock() # Mock the config attribute itself
    mock_config.config.ai = None # Now assign to the mock
    mock_config.project_root = Path("/fake/project")
    
    # Mock the plugin registry that the config holds
    mock_registry = MagicMock(spec=PluginRegistry)
    mock_config.registry = mock_registry
    
    return mock_config

@pytest.fixture
def create_pr_workflow_yaml():
    """Provides the YAML content of the create-pr workflow."""
    return {
        "name": "Create Pull Request",
        "description": "A test PR workflow",
        "source": "test", # Added source
        "params": {},     # Added params
        "steps": [
            {"id": "git_status", "name": "Get Git Status", "plugin": "git", "step": "get_status"},
            {"id": "prompt_for_commit", "name": "Prompt for Commit Message", "plugin": "git", "step": "prompt_for_commit_message"},
            {"id": "create_commit", "name": "Create Commit", "plugin": "git", "step": "create_commit", "requires": ["commit_message"]},
            {"id": "push", "name": "Push Changes", "plugin": "git", "step": "push"},
            {"id": "get_base_branch", "name": "Get Base Branch", "plugin": "git", "step": "get_base_branch"},
            {"id": "get_head_branch", "name": "Get Head Branch", "plugin": "git", "step": "get_current_branch"},
            {"id": "prompt_pr_title", "name": "Prompt for PR Title", "plugin": "github", "step": "prompt_for_pr_title"},
            {"id": "prompt_pr_body", "name": "Prompt for PR Body", "plugin": "github", "step": "prompt_for_pr_body"},
            {"id": "create_pr", "name": "Create Pull Request", "plugin": "github", "step": "create_pr", "requires": ["pr_title", "pr_base_branch", "pr_head_branch"]},
        ]
    }

def test_create_pr_workflow_e2e(mock_titan_config, create_pr_workflow_yaml):
    """
    End-to-end test for the 'create-pr' workflow execution.
    """
    # 1. Arrange
    # ----------------
    
    # Mock clients
    mock_git_client = MagicMock()
    mock_github_client = MagicMock()

    # Create mock steps that return Success with proper metadata
    def create_git_status_step(ctx):
        return Success("Status checked", metadata={
            "git_status": MagicMock(is_clean=False)
        })

    def create_prompt_commit_step(ctx):
        return Success("Commit message captured", metadata={
            "commit_message": "Test Commit Message"
        })

    def create_commit_step(ctx):
        return Success("Committed", metadata={
            "commit_hash": "abcdef123"
        })

    def create_push_step(ctx):
        return Success("Pushed", metadata={})

    def create_get_base_branch_step(ctx):
        return Success("Base branch retrieved", metadata={
            "pr_base_branch": "main"
        })

    def create_get_current_branch_step(ctx):
        return Success("Current branch retrieved", metadata={
            "pr_head_branch": "feature-branch"
        })

    def create_prompt_pr_title_step(ctx):
        return Success("PR title captured", metadata={
            "pr_title": "Test PR Title"
        })

    def create_prompt_pr_body_step(ctx):
        return Success("PR body captured", metadata={
            "pr_body": "Test PR Body"
        })

    def create_pr_step(ctx):
        return Success("PR created", metadata={
            "pr_number": 123,
            "pr_url": "http://fake.url/123"
        })

    # Mock git plugin
    mock_git_plugin = MagicMock()
    mock_git_plugin.get_client.return_value = mock_git_client
    mock_git_plugin.get_steps.return_value = {
        "get_status": create_git_status_step,
        "prompt_for_commit_message": create_prompt_commit_step,
        "create_commit": create_commit_step,
        "push": create_push_step,
        "get_base_branch": create_get_base_branch_step,
        "get_current_branch": create_get_current_branch_step,
    }

    # Mock github plugin
    mock_github_plugin = MagicMock()
    mock_github_plugin.get_client.return_value = mock_github_client
    mock_github_plugin.get_steps.return_value = {
        "prompt_for_pr_title": create_prompt_pr_title_step,
        "prompt_for_pr_body": create_prompt_pr_body_step,
        "create_pr": create_pr_step,
    }

    # Mock plugin registry to return the plugins
    mock_titan_config.registry.get_plugin.side_effect = lambda name: {
        "git": mock_git_plugin,
        "github": mock_github_plugin
    }.get(name)
    mock_titan_config.registry.list_installed.return_value = ["git", "github"]
    
    # Mock workflow registry to return our test workflow
    parsed_workflow = ParsedWorkflow(**create_pr_workflow_yaml)
    mock_workflow_registry = MagicMock(spec=WorkflowRegistry)
    mock_workflow_registry.get_workflow.return_value = parsed_workflow
    mock_titan_config.workflows = mock_workflow_registry
    
    # Build execution context
    ctx = WorkflowContextBuilder(
        plugin_registry=mock_titan_config.registry,
        secrets=MagicMock(spec=SecretManager),
        ai_config=None
    ).with_ui().build()

    # 2. Act
    # ----------------
    executor = WorkflowExecutor(mock_titan_config.registry, mock_titan_config.workflows)
    result = executor.execute(parsed_workflow, ctx)

    # 3. Assert
    # ----------------
    assert isinstance(result, Success), f"Expected Success, got {result}"

    # Assert workflow completed successfully
    assert result.message == "Workflow 'Create Pull Request' finished."

    # Assert context data was populated correctly by the steps
    assert ctx.data.get("commit_message") == "Test Commit Message"
    assert ctx.data.get("commit_hash") == "abcdef123"
    assert ctx.data.get("pr_base_branch") == "main"
    assert ctx.data.get("pr_head_branch") == "feature-branch"
    assert ctx.data.get("pr_title") == "Test PR Title"
    assert ctx.data.get("pr_body") == "Test PR Body"
    assert ctx.data.get("pr_number") == 123
    assert ctx.data.get("pr_url") == "http://fake.url/123"
