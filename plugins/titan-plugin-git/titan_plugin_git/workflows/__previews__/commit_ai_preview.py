#!/usr/bin/env python3
"""
Commit with AI Workflow Preview

Preview the commit-ai workflow by executing real steps with mocked data.
Run: titan preview workflow commit-ai
"""

from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.engine.mock_context import (
    MockGitClient,
    MockAIClient,
    MockSecretManager,
)
from titan_cli.engine import WorkflowContext
from titan_cli.engine.ui_container import UIComponents
from titan_cli.engine.views_container import UIViews
from titan_cli.engine.results import Success, Error, Skip


def create_commit_ai_mock_context() -> WorkflowContext:
    """
    Create mock context specifically for commit-ai workflow.

    Customizes mock data to simulate the commit-ai workflow scenario:
    - Git status with uncommitted changes
    - AI generates commit message
    - Commit is created and pushed

    Pre-populates context data to ensure all steps execute successfully
    and display their full UI in the preview.
    """
    # Create UI components
    ui = UIComponents.create()
    views = UIViews.create(ui)

    # Override prompts to auto-confirm (non-interactive preview)
    views.prompts.ask_confirm = lambda question, default=True: True

    # Create mock clients with workflow-specific data
    git = MockGitClient()
    git.current_branch = "feat/improve-ux"
    git.main_branch = "master"
    git.default_remote = "origin"

    ai = MockAIClient()

    secrets = MockSecretManager()

    # Build context
    ctx = WorkflowContext(
        secrets=secrets,
        ui=ui,
        views=views
    )

    # Inject mocked clients
    ctx.git = git
    ctx.ai = ai

    return ctx


def preview_workflow():
    """
    Preview the commit-ai workflow by executing real steps with mocked context.

    This ensures the preview always matches the real workflow execution.
    """
    text = TextRenderer()
    spacer = SpacerRenderer()

    # Header
    text.title("Commit with AI - PREVIEW")
    text.subtitle("(Executing real steps with mocked data)")
    spacer.line()

    # Create workflow-specific mock context
    ctx = create_commit_ai_mock_context()

    # Import steps
    from titan_plugin_git.steps.status_step import get_git_status_step
    from titan_plugin_git.steps.ai_commit_message_step import ai_generate_commit_message
    from titan_plugin_git.steps.commit_step import create_git_commit_step
    from titan_plugin_git.steps.push_step import create_git_push_step

    # Execute steps in order (same as workflow YAML)
    steps = [
        ("git_status", get_git_status_step),
        ("ai_commit_message", ai_generate_commit_message),
        ("create_commit", create_git_commit_step),
        ("push", create_git_push_step),
    ]

    text.info("Executing workflow...")
    spacer.small()

    # Inject workflow metadata (like the real executor does)
    ctx.workflow_name = "commit-ai"
    ctx.total_steps = len(steps)

    for i, (step_name, step_fn) in enumerate(steps, 1):
        # Inject current step number (like the real executor does)
        ctx.current_step = i

        # Execute the step - it will handle all its own UI
        result = step_fn(ctx)

        # Merge metadata into context (like the real executor does)
        if isinstance(result, (Success, Skip)) and result.metadata:
            ctx.data.update(result.metadata)

        # Only handle errors (steps handle their own success/skip UI)
        if isinstance(result, Error):
            text.error(f"Step '{step_name}' failed: {result.message}")
            break

    spacer.line()
    text.info("(This was a preview - no actual git operations were performed)")


if __name__ == "__main__":
    preview_workflow()
