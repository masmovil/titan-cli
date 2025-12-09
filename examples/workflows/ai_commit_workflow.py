"""
Example: AI-Powered Commit Workflow

Demonstrates using AI agent steps to automatically generate commit messages.

This workflow:
1. Gets git status
2. AI analyzes changes
3. AI suggests commit message
4. Creates commit with AI-suggested message
5. Pushes to remote

Usage:
    from examples.workflows.ai_commit_workflow import create_ai_commit_workflow

    workflow = create_ai_commit_workflow()
    result = workflow.run(ctx)
"""

from titan_cli.engine import BaseWorkflow
from titan_plugin_git.steps import (
    get_git_status_step,
    create_git_commit_step,
)
from titan_plugin_git.steps.push_step import push_step
from titan_cli.agents.steps import (
    ai_analyze_changes_step,
    ai_suggest_commit_message_step,
)


def create_ai_commit_workflow(push_after_commit: bool = False) -> BaseWorkflow:
    """
    Create workflow that uses AI to generate commit messages.

    Args:
        push_after_commit: If True, adds push step after commit

    Returns:
        BaseWorkflow configured with AI-powered commit steps
    """

    steps = [
        # Step 1: Get current git status
        get_git_status_step,

        # Step 2: AI analyzes the changes (optional - for logging/insights)
        ai_analyze_changes_step,

        # Step 3: AI suggests commit message
        # This populates ctx.data["commit_message"] for the next step
        ai_suggest_commit_message_step,

        # Step 4: Create commit using AI-suggested message
        create_git_commit_step,
    ]

    # Optionally add push step
    if push_after_commit:
        steps.append(push_step)

    return BaseWorkflow(
        name="AI-Powered Commit",
        steps=steps
    )


def create_hybrid_commit_workflow() -> BaseWorkflow:
    """
    Hybrid workflow: AI suggests, user confirms or modifies.

    This workflow:
    1. Gets git status
    2. AI suggests commit message
    3. User can accept or modify the suggestion
    4. Creates commit
    """

    from titan_plugin_git.steps.prompt_step import prompt_for_commit_message_step

    def prompt_with_ai_suggestion_step(ctx):
        """Custom step that shows AI suggestion and lets user modify it."""
        from titan_cli.engine import Success, Skip

        # Check if AI already suggested a message
        suggested = ctx.data.get("suggested_commit_message")

        if not suggested:
            # No AI suggestion, fall back to normal prompt
            return prompt_for_commit_message_step(ctx)

        # Show AI suggestion and ask for confirmation/modification
        print(f"\n🤖 AI suggested commit message:")
        print(f"   {suggested}\n")

        choice = ctx.views.prompts.ask_confirm(
            "Use this message?",
            default=True
        )

        if choice:
            # User accepted AI suggestion
            return Success(
                "Using AI-suggested commit message",
                metadata={"commit_message": suggested}
            )
        else:
            # User wants to modify - prompt for new message
            return prompt_for_commit_message_step(ctx)

    prompt_with_ai_suggestion_step.__name__ = "prompt_with_ai_suggestion_step"

    return BaseWorkflow(
        name="Hybrid AI Commit",
        steps=[
            get_git_status_step,
            ai_suggest_commit_message_step,
            prompt_with_ai_suggestion_step,  # User can accept/modify
            create_git_commit_step,
        ]
    )


# Example usage in a CLI command
if __name__ == "__main__":
    """
    Example CLI integration:

    titan commit-ai           # Fully automated
    titan commit-ai --hybrid  # AI suggests, user confirms
    """
    import typer
    from titan_cli.engine import WorkflowContextBuilder
    from titan_cli.core.config import TitanConfig
    from titan_cli.core.secrets import SecretManager

    app = typer.Typer()

    @app.command()
    def commit_ai(
        hybrid: bool = typer.Option(False, "--hybrid", help="Let user confirm/modify AI suggestion"),
        push: bool = typer.Option(False, "--push", help="Push after committing"),
    ):
        """Create a commit using AI-generated message."""

        # Initialize
        config = TitanConfig()
        secrets = SecretManager()

        # Build context
        ctx = (
            WorkflowContextBuilder(config=config, secrets=secrets)
            .with_git()
            .with_ai()
            .with_ui()
            .build()
        )

        # Select workflow
        if hybrid:
            workflow = create_hybrid_commit_workflow()
        else:
            workflow = create_ai_commit_workflow(push_after_commit=push)

        # Run
        result = workflow.run(ctx)

        if result.success:
            print(f"✅ {result.message}")
        else:
            print(f"❌ {result.message}")
            raise typer.Exit(1)

    app()
