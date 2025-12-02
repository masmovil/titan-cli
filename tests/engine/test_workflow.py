"""Tests for workflow engine."""

import pytest
from unittest.mock import MagicMock
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.engine import (
    WorkflowContext,
    WorkflowContextBuilder,
    BaseWorkflow,
    Success,
    Error,
    Skip,
    is_success,
    is_error
)

@pytest.fixture
def mock_core_deps():
    """Provides mock TitanConfig and SecretManager."""
    mock_config = MagicMock(spec=TitanConfig)
    mock_secrets = MagicMock(spec=SecretManager)
    # Ensure nested attributes used in builder exist
    # We need to mock the nested 'config' object itself
    mock_config.config = MagicMock()
    mock_config.config.ai = None
    return mock_config, mock_secrets


def test_workflow_success(mock_core_deps):
    """Test workflow with all successful steps."""
    mock_config, mock_secrets = mock_core_deps

    def step1(ctx: WorkflowContext):
        ctx.set("step1_done", True)
        return Success("Step 1 completed")

    def step2(ctx: WorkflowContext):
        assert ctx.get("step1_done") is True
        return Success("Step 2 completed")

    ctx = WorkflowContextBuilder(mock_config, mock_secrets).build()
    workflow = BaseWorkflow(name="Test Workflow", steps=[step1, step2])

    result = workflow.run(ctx)

    assert is_success(result)
    assert ctx.get("step1_done") is True


def test_workflow_halt_on_error(mock_core_deps):
    """Test workflow halts on error."""
    mock_config, mock_secrets = mock_core_deps

    def step1(ctx: WorkflowContext):
        return Success("Step 1 ok")

    def step2(ctx: WorkflowContext):
        return Error("Step 2 failed")

    def step3(ctx: WorkflowContext):
        ctx.set("step3_ran", True)  # Should not run
        return Success("Step 3 ok")

    ctx = WorkflowContextBuilder(mock_config, mock_secrets).build()
    workflow = BaseWorkflow(name="Test", steps=[step1, step2, step3])

    result = workflow.run(ctx)

    assert is_error(result)
    assert "Step 2 failed" in result.message
    assert ctx.get("step3_ran") is None  # Step 3 didn't run


def test_workflow_skip(mock_core_deps):
    """Test workflow with skipped step."""
    mock_config, mock_secrets = mock_core_deps

    def step1(ctx: WorkflowContext):
        return Skip("Step 1 not applicable")

    def step2(ctx: WorkflowContext):
        return Success("Step 2 ok")

    ctx = WorkflowContextBuilder(mock_config, mock_secrets).build()
    workflow = BaseWorkflow(name="Test", steps=[step1, step2])

    result = workflow.run(ctx)

    assert is_success(result)  # Skip doesn't stop workflow


def test_workflow_metadata_auto_merging(mock_core_deps):
    """Test that metadata from results is auto-merged into context."""
    mock_config, mock_secrets = mock_core_deps

    def step1(ctx: WorkflowContext):
        return Success("Step 1 with metadata", metadata={"step1_data": "foo"})

    def step2(ctx: WorkflowContext):
        return Skip("Step 2 with metadata", metadata={"step2_data": "bar"})

    def step3(ctx: WorkflowContext):
        assert ctx.get("step1_data") == "foo"
        assert ctx.get("step2_data") == "bar"
        return Success("Step 3 verified data")

    ctx = WorkflowContextBuilder(mock_config, mock_secrets).build()
    workflow = BaseWorkflow(name="Metadata Test", steps=[step1, step2, step3])
    workflow.run(ctx)

    # Final check on context data
    assert ctx.data == {"step1_data": "foo", "step2_data": "bar"}


def test_context_builder_with_ui_auto_creation(mock_core_deps):
    """Test context builder auto-creates UI components."""
    mock_config, mock_secrets = mock_core_deps
    ctx = WorkflowContextBuilder(mock_config, mock_secrets).with_ui().build()

    assert ctx.text is not None
    assert ctx.prompts is not None
    # Check that prompts is using the created text renderer
    assert ctx.prompts.text == ctx.text


def test_context_builder_with_ui_injection(mock_core_deps):
    """Test context builder with injected UI components."""
    mock_config, mock_secrets = mock_core_deps
    mock_text = MagicMock()
    mock_prompts = MagicMock()
    
    ctx = WorkflowContextBuilder(mock_config, mock_secrets).with_ui(
        text=mock_text,
        prompts=mock_prompts
    ).build()

    assert ctx.text is mock_text
    assert ctx.prompts is mock_prompts


def test_context_builder_with_ai_auto_creation(mock_core_deps):
    """Test context builder auto-creates the AI client."""
    mock_config, mock_secrets = mock_core_deps
    
    # The builder will always create an AIClient instance due to lazy loading
    # of the provider. The check for a valid config happens inside the client.
    # This test just ensures the builder doesn't crash.
    ctx = WorkflowContextBuilder(mock_config, mock_secrets).with_ai().build()
    
    assert ctx.ai is not None
    # We can also check that it is an instance of AIClient
    from titan_cli.ai.client import AIClient
    assert isinstance(ctx.ai, AIClient)

def test_context_builder_with_ai_injection(mock_core_deps):
    """Test context builder with an injected AI client."""
    mock_config, mock_secrets = mock_core_deps
    mock_ai_client = MagicMock()

    ctx = WorkflowContextBuilder(mock_config, mock_secrets).with_ai(
        ai_client=mock_ai_client
    ).build()

    assert ctx.ai is mock_ai_client
