"""
AI Code Assistant Step

Generic step that launches an AI coding assistant CLI (like Claude Code)
with context from previous workflow steps.

Can be used after linting, testing, builds, or any step that produces
errors or context that could benefit from AI assistance.
"""

from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, Skip, WorkflowResult
from titan_cli.utils.claude_integration import ClaudeCodeLauncher


def execute_ai_assistant_step(step: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
    """
    Launch AI coding assistant with context from workflow.

    Parameters (in step.params):
        context_key: str - Key in ctx.data to read context from
        prompt_template: str - Template for the prompt (use {context} placeholder)
        ask_confirmation: bool - Whether to ask user before launching (default: True)
        fail_on_decline: bool - If True, return Error when user declines (default: False)
        cli_preference: str - Which CLI to use: "claude-code", "auto" (default: "auto")

    Example workflow usage:
        - id: ai-help
          plugin: core
          step: ai_code_assistant
          params:
            context_key: "test_failures"
            prompt_template: "Help me fix these test failures:\n{context}"
            ask_confirmation: true
            fail_on_decline: true
          on_error: fail
    """
    if not ctx.ui:
        return Error("UI context is not available for this step.")

    # Get parameters
    context_key = step.params.get("context_key")
    prompt_template = step.params.get("prompt_template", "{context}")
    ask_confirmation = step.params.get("ask_confirmation", True)
    fail_on_decline = step.params.get("fail_on_decline", False)
    cli_preference = step.params.get("cli_preference", "auto")

    # Validate required parameters
    if not context_key:
        return Error("Parameter 'context_key' is required for ai_code_assistant step")

    # Get context data
    context_data = ctx.data.get(context_key)
    if not context_data:
        # No context to work with - skip silently
        return Skip(f"No data found in context key '{context_key}' - skipping AI assistance")

    # Clear the context data immediately to prevent contamination of subsequent steps
    if context_key in ctx.data:
        del ctx.data[context_key]

    # Build the prompt
    try:
        if isinstance(context_data, str):
            prompt = prompt_template.format(context=context_data)
        else:
            # If it's not a string, convert to string representation
            import json
            context_str = json.dumps(context_data, indent=2)
            prompt = prompt_template.format(context=context_str)
    except KeyError as e:
        return Error(f"Invalid prompt_template: missing placeholder {e}")
    except Exception as e:
        return Error(f"Failed to build prompt: {e}")

    # Ask for confirmation if needed
    if ask_confirmation:
        ctx.ui.spacer.small()
        should_launch = ctx.views.prompts.ask_confirm(
            "Would you like AI assistance to help fix these issues?",
            default=True
        )
        if not should_launch:
            if fail_on_decline:
                return Error("User declined AI assistance - workflow stopped")
            return Skip("User declined AI assistance")

    # Determine which CLI to use
    launcher = None
    cli_name = None

    if cli_preference in ("claude-code", "auto"):
        if ClaudeCodeLauncher.is_available():
            launcher = ClaudeCodeLauncher
            cli_name = "Claude Code"

    # TODO: Add support for other CLIs (Cursor, Windsurf, etc.) when configured

    if not launcher:
        ctx.ui.text.warning("No AI coding assistant CLI found")
        ctx.ui.text.body("Install Claude Code: npm install -g @anthropic/claude-code", style="dim")
        return Skip("No AI assistant available")

    # Launch the CLI
    ctx.ui.spacer.small()
    ctx.ui.text.info(f"🤖 Launching {cli_name}...")
    ctx.ui.text.body(f"Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"Prompt: {prompt}", style="dim")
    ctx.ui.spacer.small()

    project_root = ctx.get("project_root", ".")
    exit_code = launcher.launch(prompt=prompt, cwd=project_root)

    ctx.ui.spacer.small()
    ctx.ui.text.success("✓ Back in Titan workflow")

    if exit_code != 0:
        return Error(f"{cli_name} exited with code {exit_code}")

    return Success(f"{cli_name} session completed", metadata={"ai_exit_code": exit_code})
