"""Tests for workflow engine."""

import pytest
from titan_cli.engine import (
    WorkflowContext,
    WorkflowContextBuilder,
    BaseWorkflow,
    Success,
    Error,
    Skip,
)


def test_workflow_success():
    """Test workflow with all successful steps."""

    def step1(ctx: WorkflowContext):
        ctx.set("step1_done", True)
        return Success("Step 1 completed")

    def step2(ctx: WorkflowContext):
        assert ctx.get("step1_done") is True
        return Success("Step 2 completed")

    ctx = WorkflowContextBuilder().build()
    workflow = BaseWorkflow(name="Test Workflow", steps=[step1, step2])

    result = workflow.run(ctx)

    assert result.is_success()
    assert ctx.get("step1_done") is True


def test_workflow_halt_on_error():
    """Test workflow halts on error."""

    def step1(ctx: WorkflowContext):
        return Success("Step 1 ok")

    def step2(ctx: WorkflowContext):
        return Error("Step 2 failed")

    def step3(ctx: WorkflowContext):
        ctx.set("step3_ran", True)  # Should not run
        return Success("Step 3 ok")

    ctx = WorkflowContextBuilder().build()
    workflow = BaseWorkflow(name="Test", steps=[step1, step2, step3])

    result = workflow.run(ctx)

    assert result.is_error()
    assert "Step 2 failed" in result.message
    assert ctx.get("step3_ran") is None  # Step 3 didn't run


def test_workflow_skip():
    """Test workflow with skipped step."""

    def step1(ctx: WorkflowContext):
        return Skip("Step 1 not applicable")

    def step2(ctx: WorkflowContext):
        return Success("Step 2 ok")

    ctx = WorkflowContextBuilder().build()
    workflow = BaseWorkflow(name="Test", steps=[step1, step2])

    result = workflow.run(ctx)

    assert result.is_success()  # Skip doesn't stop workflow


def test_context_builder_with_ui():
    """Test context builder with UI components."""

    ctx = WorkflowContextBuilder().with_ui().build()

    assert ctx.text is not None
    assert ctx.prompts is not None


def test_context_builder_with_ai():
    """Test context builder with AI client."""

    ctx = WorkflowContextBuilder().with_ai().build()

    # AI may or may not be configured, just check it doesn't crash
    assert ctx.ai is None or ctx.ai is not None
