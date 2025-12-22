"""
AI Code Assistant Step

Generic step that launches an AI coding assistant CLI (like Claude Code)
with context from previous workflow steps.

Can be used after linting, testing, builds, or any step that produces
errors or context that could benefit from AI assistance.
"""

import json 

from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, Skip, WorkflowResult
from titan_cli.external_cli.launcher import CLILauncher
from titan_cli.external_cli.configs import CLI_REGISTRY
from titan_cli.messages import msg
from titan_cli.ui.views.menu_components.dynamic_menu import DynamicMenu


def execute_ai_assistant_step(step: WorkflowStepModel, ctx: WorkflowContext) -> WorkflowResult:
    """
    Launch AI coding assistant with context from workflow.

    Parameters (in step.params):
        context_key: str - Key in ctx.data to read context from
        prompt_template: str - Template for the prompt (use {context} placeholder)
        ask_confirmation: bool - Whether to ask user before launching (default: True)
        fail_on_decline: bool - If True, return Error when user declines (default: False)
        cli_preference: str - Which CLI to use: "claude", "gemini", "auto" (default: "auto")

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
        return Error(msg.AIAssistant.UI_CONTEXT_NOT_AVAILABLE)

    # Get parameters
    context_key = step.params.get("context_key")
    prompt_template = step.params.get("prompt_template", "{context}")
    ask_confirmation = step.params.get("ask_confirmation", True)
    fail_on_decline = step.params.get("fail_on_decline", False)
    cli_preference = step.params.get("cli_preference", "auto")

    # Validate cli_preference
    VALID_CLI_PREFERENCES = {"auto", "claude", "gemini"}
    if cli_preference not in VALID_CLI_PREFERENCES:
        return Error(f"Invalid cli_preference: {cli_preference}. Must be one of {VALID_CLI_PREFERENCES}")

    # Validate required parameters
    if not context_key:
        return Error(msg.AIAssistant.CONTEXT_KEY_REQUIRED)

    # Get context data
    context_data = ctx.data.get(context_key)
    if not context_data:
        # No context to work with - skip silently
        return Skip(msg.AIAssistant.NO_DATA_IN_CONTEXT.format(context_key=context_key))

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
        return Error(msg.AIAssistant.INVALID_PROMPT_TEMPLATE.format(e=e))
    except Exception as e:
        return Error(msg.AIAssistant.FAILED_TO_BUILD_PROMPT.format(e=e))

    # Ask for confirmation if needed
    if ask_confirmation:
        ctx.ui.spacer.small()
        should_launch = ctx.views.prompts.ask_confirm(
            msg.AIAssistant.CONFIRM_LAUNCH_ASSISTANT,
            default=True
        )
        if not should_launch:
            if fail_on_decline:
                return Error(msg.AIAssistant.DECLINED_ASSISTANCE_STOPPED)
            return Skip(msg.AIAssistant.DECLINED_ASSISTANCE_SKIPPED)

    # Determine which CLI to use
    cli_to_launch = None

    preferred_clis = []
    if cli_preference == "auto":
        preferred_clis = list(CLI_REGISTRY.keys())
    else:
        preferred_clis = [cli_preference]
    
    available_launchers = {}
    for cli_name in preferred_clis:
        config = CLI_REGISTRY.get(cli_name)
        if config:
            launcher = CLILauncher(
                cli_name=cli_name,
                install_instructions=config.get("install_instructions"),
                prompt_flag=config.get("prompt_flag")
            )
            if launcher.is_available():
                available_launchers[cli_name] = launcher

    if not available_launchers:
        ctx.ui.text.warning(msg.AIAssistant.NO_ASSISTANT_CLI_FOUND)
        return Skip(msg.AIAssistant.NO_ASSISTANT_CLI_FOUND)
    
    if len(available_launchers) == 1:
        cli_to_launch = list(available_launchers.keys())[0]
    else:
        menu = DynamicMenu(title=msg.AIAssistant.SELECT_ASSISTANT_CLI)
        cat = menu.add_category("Available CLIs")
        for cli_name, launcher_instance in available_launchers.items():
            display_name = CLI_REGISTRY[cli_name].get("display_name", cli_name)
            cat.add_item(display_name, f"Launch {display_name}", cli_name)
        
        choice = ctx.views.prompts.ask_menu(menu.to_menu())
        if not choice:
            return Skip(msg.AIAssistant.DECLINED_ASSISTANCE_SKIPPED)
        cli_to_launch = choice.action

    # Get the selected launcher
    launcher = available_launchers.get(cli_to_launch)
    if not launcher:
        return Error(f"Unknown CLI to launch: {cli_to_launch}")

    cli_name = CLI_REGISTRY[cli_to_launch].get("display_name", cli_to_launch)

    # Launch the CLI
    ctx.ui.spacer.small()
    ctx.ui.text.info(msg.AIAssistant.LAUNCHING_ASSISTANT.format(cli_name=cli_name))
    # Using msg.AIAssistant.PROMPT_PREVIEW for consistency
    prompt_preview_text = msg.AIAssistant.PROMPT_PREVIEW.format(
        prompt_preview=f"{prompt[:100]}..." if len(prompt) > 100 else prompt
    )
    ctx.ui.text.body(prompt_preview_text, style="dim")
    ctx.ui.spacer.small()

    project_root = ctx.get("project_root", ".")
    exit_code = launcher.launch(prompt=prompt, cwd=project_root)

    ctx.ui.spacer.small()
    ctx.ui.text.success(msg.AIAssistant.BACK_IN_TITAN)

    if exit_code != 0:
        return Error(msg.AIAssistant.ASSISTANT_EXITED_WITH_CODE.format(cli_name=cli_name, exit_code=exit_code))

    return Success(msg.AIAssistant.ASSISTANT_EXITED_WITH_CODE.format(cli_name=cli_name, exit_code=exit_code), metadata={"ai_exit_code": exit_code})
