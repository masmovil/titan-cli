"""
AI Code Assistant Step

Generic step that launches an AI coding assistant CLI (like Claude Code)
with context from previous workflow steps.

Can be used after linting, testing, builds, or any step that produces
errors or context that could benefit from AI assistance.
"""

import json

from titan_cli.ai.router import (
    AIRouteDecision,
    AIProviderType,
    AITask,
    declare_ai_usage,
)
from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, Skip, WorkflowResult
from titan_cli.external_cli.configs import CLI_REGISTRY
from titan_cli.messages import msg


@declare_ai_usage(
    task=AITask.GENERIC_ASSISTANT,
    # Fixing lint/test/build issues means editing files and running commands in
    # a real terminal session - only an interactive CLI can do that.
    executes=[AIProviderType.CLI_INTERACTIVE],
    enforces=True,
)
def execute_ai_assistant_step(step: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
    """
    Launch AI coding assistant with context from workflow.

    Parameters (in step.params):
        context_key: str - Key in ctx.data to read context from
        prompt_template: str - Template for the prompt (use {context} placeholder)
        ask_confirmation: bool - Whether to ask user before launching (default: True)
        fail_on_decline: bool - If True, return Error when user declines (default: False)
        pre_launch_warning: str - Optional warning panel shown just before the CLI starts

    Which CLI runs is not a step parameter: it is the default CLI configured once in AI
    Configuration, so every workflow uses the same one and nothing is asked mid-run.

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
    if not ctx.textual:
        return Error(msg.AIAssistant.UI_CONTEXT_NOT_AVAILABLE)

    # Begin step container - use step name from workflow
    ctx.textual.begin_step(step.name or "AI Code Assistant")

    # Get parameters
    context_key = step.params.get("context_key")
    prompt_template = step.params.get("prompt_template", "{context}")
    ask_confirmation = step.params.get("ask_confirmation", True)
    fail_on_decline = step.params.get("fail_on_decline", False)
    pre_launch_warning = step.params.get("pre_launch_warning")

    # Validate required parameters
    if not context_key:
        ctx.textual.error_text(msg.AIAssistant.CONTEXT_KEY_REQUIRED)
        ctx.textual.end_step("error")
        return Error(msg.AIAssistant.CONTEXT_KEY_REQUIRED)

    # Get context data
    context_data = ctx.data.get(context_key)
    if not context_data:
        # No context to work with - skip silently with user-friendly message
        # Infer what we're skipping based on step name
        step_name = step.name or "AI Code Assistant"
        if "lint" in step_name.lower():
            friendly_msg = "No linting issues found - skipping AI assistance"
        elif "test" in step_name.lower():
            friendly_msg = "No test failures found - skipping AI assistance"
        else:
            friendly_msg = "No issues to fix - skipping AI assistance"

        ctx.textual.dim_text(friendly_msg)
        ctx.textual.end_step("skip")
        return Skip(friendly_msg)

    # Clear the context data immediately to prevent contamination of subsequent steps
    if context_key in ctx.data:
        del ctx.data[context_key]

    # Build the prompt
    try:
        if isinstance(context_data, str):
            prompt = prompt_template.format(context=context_data)
        else:
            # If it's not a string, convert to string representation
            context_str = json.dumps(context_data, indent=2)
            prompt = prompt_template.format(context=context_str)
    except KeyError as e:
        ctx.textual.error_text(msg.AIAssistant.INVALID_PROMPT_TEMPLATE.format(e=e))
        ctx.textual.end_step("error")
        return Error(msg.AIAssistant.INVALID_PROMPT_TEMPLATE.format(e=e))
    except Exception as e:
        ctx.textual.error_text(msg.AIAssistant.FAILED_TO_BUILD_PROMPT.format(e=e))
        ctx.textual.end_step("error")
        return Error(msg.AIAssistant.FAILED_TO_BUILD_PROMPT.format(e=e))

    # Ask for confirmation if needed
    if ask_confirmation:
        ctx.textual.text("")  # spacing
        should_launch = ctx.textual.ask_confirm(
            msg.AIAssistant.CONFIRM_LAUNCH_ASSISTANT,
            default=True
        )
        if not should_launch:
            if fail_on_decline:
                ctx.textual.warning_text(msg.AIAssistant.DECLINED_ASSISTANCE_STOPPED)
                ctx.textual.end_step("error")
                return Error(msg.AIAssistant.DECLINED_ASSISTANCE_STOPPED)
            ctx.textual.dim_text(msg.AIAssistant.DECLINED_ASSISTANCE_SKIPPED)
            ctx.textual.end_step("skip")
            return Skip(msg.AIAssistant.DECLINED_ASSISTANCE_SKIPPED)

    # This step owns its own execution (it launches an interactive session and suspends the
    # TUI), so it resolves the route instead of asking the façade to run a prompt. Which CLI
    # runs is never asked here: it is configured beforehand in AI Configuration.
    if not ctx.ai_router:
        ctx.textual.error_text(msg.AIAssistant.ROUTING_UNAVAILABLE)
        ctx.textual.end_step("error")
        return Error(msg.AIAssistant.ROUTING_UNAVAILABLE)

    # No CLI installed at all is an environment that simply cannot do this, not a
    # misconfiguration - it stays the friendly skip it has always been.
    if not ctx.ai_router.availability.available_interactive_clis():
        ctx.textual.warning_text(msg.AIAssistant.NO_ASSISTANT_CLI_FOUND)
        ctx.textual.end_step("skip")
        return Skip(msg.AIAssistant.NO_ASSISTANT_CLI_FOUND)

    resolution = ctx.ai_router.resolve(policy=execute_ai_assistant_step)

    if not isinstance(resolution, AIRouteDecision):
        message = f"{resolution.reason}. {msg.AIAssistant.CONFIGURE_HINT}"
        ctx.textual.error_text(message)
        ctx.textual.end_step("error")
        return Error(message)

    if resolution.provider == AIProviderType.OFF:
        ctx.textual.dim_text(msg.AIAssistant.AI_DISABLED)
        ctx.textual.end_step("skip")
        return Skip(msg.AIAssistant.AI_DISABLED)

    if resolution.provider != AIProviderType.CLI_INTERACTIVE or not resolution.cli:
        message = msg.AIAssistant.INTERACTIVE_CLI_REQUIRED.format(
            provider=resolution.provider
        )
        ctx.textual.error_text(message)
        ctx.textual.end_step("error")
        return Error(message)

    cli_to_launch = resolution.cli
    cli_name = CLI_REGISTRY.get(cli_to_launch, {}).get("display_name", cli_to_launch)

    if pre_launch_warning:
        ctx.textual.panel(pre_launch_warning, panel_type="warning")
        ctx.textual.text("")  # spacing

    # Launch the CLI
    ctx.textual.primary_text(msg.AIAssistant.LAUNCHING_ASSISTANT.format(cli_name=cli_name))

    project_root = ctx.get("project_root", ".")

    # Launch CLI and suspend TUI while it runs
    exit_code = ctx.textual.launch_external_cli(
        cli_name=cli_to_launch,
        prompt=prompt,
        cwd=project_root
    )

    ctx.textual.text("")  # spacing
    ctx.textual.success_text(msg.AIAssistant.BACK_IN_TITAN)

    if exit_code != 0:
        ctx.textual.warning_text(msg.AIAssistant.ASSISTANT_EXITED_WITH_CODE.format(cli_name=cli_name, exit_code=exit_code))
        ctx.textual.end_step("error")
        return Error(msg.AIAssistant.ASSISTANT_EXITED_WITH_CODE.format(cli_name=cli_name, exit_code=exit_code))

    ctx.textual.success_text(msg.AIAssistant.ASSISTANT_EXITED_WITH_CODE.format(cli_name=cli_name, exit_code=exit_code))
    ctx.textual.end_step("success")
    return Success(msg.AIAssistant.ASSISTANT_EXITED_WITH_CODE.format(cli_name=cli_name, exit_code=exit_code), metadata={"ai_exit_code": exit_code})
