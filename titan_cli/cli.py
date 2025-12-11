"""
Titan CLI - Main CLI application

Combines all tool commands into a single CLI interface.
"""
from titan_cli.engine.ui_container import UIComponents
from titan_cli.ui.components.panel import PanelRenderer
from titan_cli.ui.components.table import TableRenderer
import typer
import tomli
import tomli_w
import importlib.metadata
from pathlib import Path
from typing import Optional

from titan_cli.ui.views.banner import render_titan_banner
from titan_cli.messages import msg
from titan_cli.preview import preview_app
from titan_cli.commands.init import init_app
from titan_cli.commands.projects import projects_app, list_projects
from titan_cli.commands.ai import ai_app
from titan_cli.commands.plugins import plugins_app
from titan_cli.commands.code import code_app, launch_code
from titan_cli.utils.claude_integration import ClaudeCodeLauncher
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.core.errors import ConfigWriteError
from titan_cli.core.discovery import discover_projects
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.ui.views.prompts import PromptsRenderer
from titan_cli.core.project_init import initialize_project
from titan_cli.ui.views.menu_components.dynamic_menu import DynamicMenu

# New Workflow-related imports
from titan_cli.engine.workflow_executor import WorkflowExecutor
from titan_cli.engine.builder import WorkflowContextBuilder
from titan_cli.core.workflows.workflow_exceptions import WorkflowNotFoundError, WorkflowExecutionError


# Main Typer Application
app = typer.Typer(
    name=msg.CLI.APP_NAME,
    help=msg.CLI.APP_DESCRIPTION,
    invoke_without_command=True,
    no_args_is_help=False,
)

# Add subcommands from other modules
app.add_typer(preview_app)
app.add_typer(init_app)
app.add_typer(projects_app)
app.add_typer(ai_app)
app.add_typer(plugins_app)
app.add_typer(code_app)


# --- Helper function for version retrieval ---
def get_version() -> str:
    """Retrieves the package version from pyproject.toml."""
    return importlib.metadata.version("titan-cli")


def _prompt_for_project_root(text: TextRenderer, prompts: PromptsRenderer) -> bool:
    """Asks the user for the project root and saves it to the global config."""
    welcome_title = msg.Config.PROJECT_ROOT_WELCOME_TITLE
    info_msg = msg.Config.PROJECT_ROOT_INFO_MSG
    body_msg = msg.Config.PROJECT_ROOT_BODY_MSG
    prompt_msg = msg.Config.PROJECT_ROOT_PROMPT_MSG
    success_msg = msg.Config.PROJECT_ROOT_SUCCESS_MSG

    text.title(welcome_title)
    text.line()
    text.info(info_msg)
    text.body(body_msg)
    text.line()

    global_config_path = TitanConfig.GLOBAL_CONFIG
    global_config_path.parent.mkdir(parents=True, exist_ok=True)

    config = {}
    if global_config_path.exists():
        with open(global_config_path, "rb") as f:
            try:
                config = tomli.load(f)
            except tomli.TOMLDecodeError:
                text.error(f"Could not parse existing global config at {global_config_path}. A new one will be created.")
                config = {}

    try:
        project_root_str = prompts.ask_text(prompt_msg, default=str(Path.home()))
        if not project_root_str:
            return False

        project_root = str(Path(project_root_str).expanduser().resolve())
        config.setdefault("core", {})["project_root"] = project_root

        with open(global_config_path, "wb") as f:
            tomli_w.dump(config, f)

        text.success(success_msg.format(project_root=project_root))
        text.line()
        return True

    except (EOFError, KeyboardInterrupt):
        return False
    except (OSError, PermissionError) as e:
        error = ConfigWriteError(file_path=str(global_config_path), original_exception=e)
        text.error(str(error))
        return False


def _show_submenu(
    prompts: PromptsRenderer,
    text: TextRenderer,
    config: TitanConfig,
    title: str,
    emoji: str,
    actions: dict,
    on_confirm_return_to_main: bool = True
):
    """Shows a generic submenu for various configurations."""
    while True:
        submenu_builder = DynamicMenu(title=title, emoji=emoji)
        action_category = submenu_builder.add_category("Actions")
        for action_name, action_desc, action_id in actions["actions"]:
            action_category.add_item(action_name, action_desc, action_id)
        submenu_builder.add_category("Back").add_item("Return to Main Menu", "", "back")

        choice_item = prompts.ask_menu(submenu_builder.to_menu())
        if not choice_item or choice_item.action == "back":
            break

        if choice_item.action in actions["handlers"]:
            actions["handlers"][choice_item.action]()

        prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)

def _show_projects_submenu(prompts: PromptsRenderer, text: TextRenderer, config: TitanConfig):
    """Shows the submenu for project management."""
    def list_projects_handler():
        list_projects()

    def configure_project_handler():
        text.title(msg.Projects.CONFIGURE_TITLE)
        project_root = config.get_project_root()
        if not project_root:
            text.error(msg.Errors.PROJECT_ROOT_NOT_SET)
            return

        _conf, unconfigured = discover_projects(str(project_root))
        if not unconfigured:
            text.success("No unconfigured Git projects found to initialize.")
        else:
            project_menu_builder = DynamicMenu(title=msg.Interactive.SELECT_PROJECT_TITLE, emoji="✨")
            cat_idx = project_menu_builder.add_category("Unconfigured Projects")
            for p in unconfigured:
                try:
                    rel_path = str(p.relative_to(project_root))
                except ValueError:
                    rel_path = str(p)
                cat_idx.add_item(p.name, rel_path, str(p.resolve()))

            project_menu_builder.add_category("Cancel").add_item("Back to Main Menu", "Return without initializing.", "cancel")
            
            project_menu = project_menu_builder.to_menu()
            chosen_project_item = prompts.ask_menu(project_menu, allow_quit=False)

            if chosen_project_item and chosen_project_item.action != "cancel":
                initialize_project(Path(chosen_project_item.action))

    _show_submenu(
        prompts,
        text,
        config,
        title="Project Management",
        emoji="📂",
        actions={
            "actions": [
                ("List Configured Projects", "Scan the project root and show all configured Titan projects.", "list"),
                ("Configure a New Project", "Select an unconfigured project to initialize with Titan.", "configure")
            ],
            "handlers": {
                "list": list_projects_handler,
                "configure": configure_project_handler
            }
        }
    )


def _show_ai_config_submenu(prompts: PromptsRenderer, text: TextRenderer, config: TitanConfig):
    """Shows the submenu for AI configuration."""
    from titan_cli.commands.ai import configure_ai_interactive, _test_ai_connection_by_id, list_providers, set_default_provider
    
    def configure_ai_handler():
        configure_ai_interactive()

    def test_ai_handler():
        # Reload config to get latest (e.g., if configured via `ai_configure` in same session)
        config.load()
        secrets = SecretManager() # Re-init to load any new secrets

        if not config.config.ai or not config.config.ai.providers:
            text.error(msg.AI.PROVIDER_NOT_CONFIGURED)
            text.body(msg.AI.AI_SEE_AVAILABLE_PROVIDERS)
            return

        provider_id = config.config.ai.default
        if not provider_id:
            text.error(msg.AI.AI_NO_DEFAULT_PROVIDER)
            text.body(msg.AI.AI_SEE_AVAILABLE_PROVIDERS)
            return

        provider_cfg = config.config.ai.providers.get(provider_id)
        if not provider_cfg:
            text.error(msg.AI.AI_PROVIDER_NOT_FOUND_IN_CONFIG.format(provider_id=provider_id))
            text.body(msg.AI.AI_SEE_AVAILABLE_PROVIDERS)
            return

        _test_ai_connection_by_id(provider_id, secrets, config.config.ai, provider_cfg)

    def set_default_handler():
        set_default_provider(provider_id=None)

    _show_submenu(
        prompts,
        text,
        config,
        title="AI Configuration",
        emoji="⚙️",
        actions={
            "actions": [
                ("Configure AI Provider", "Set up Anthropic, OpenAI, or Gemini", "ai_configure"),
                ("Test AI Connection", "Verify AI provider is working", "ai_test"),
                ("List AI Providers", "List all configured AI providers.", "ai_list"),
                ("Set Default Provider", "Change which AI provider is used by default", "ai_set_default")
            ],
            "handlers": {
                "ai_configure": configure_ai_handler,
                "ai_test": test_ai_handler,
                "ai_list": list_providers,
                "ai_set_default": set_default_handler,
            }
        }
    )


def _handle_run_workflow_action(config: TitanConfig, text: TextRenderer, spacer: SpacerRenderer, prompts: PromptsRenderer):
    """Handle the 'run workflow' menu action."""
    text.title("Run a Workflow")
    spacer.line()

    # Reload config to ensure latest changes (e.g., GitHub repo settings) are picked up
    config.load()
    available_workflows = config.workflows.discover()
    if not available_workflows:
        text.info("No workflows found.")
        spacer.line()
        prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)
        return

    workflow_menu_builder = DynamicMenu(title="Select a workflow to run", emoji="⚡")
    workflow_cat_idx = workflow_menu_builder.add_category("Available Workflows")
    for wf_info in available_workflows:
        workflow_cat_idx.add_item(wf_info.name, f"({wf_info.source}) {wf_info.description}", wf_info.name)
    workflow_menu_builder.add_category("Cancel").add_item("Back to Main Menu", "Return without running a workflow.", "cancel")

    workflow_menu = workflow_menu_builder.to_menu()

    try:
        chosen_workflow_item = prompts.ask_menu(workflow_menu, allow_quit=False)
    except (KeyboardInterrupt, EOFError):
        chosen_workflow_item = None

    spacer.line()

    if chosen_workflow_item and chosen_workflow_item.action != "cancel":
        selected_workflow_name = chosen_workflow_item.action

        try:
            parsed_workflow = config.workflows.get_workflow(selected_workflow_name)
            if not parsed_workflow:
                text.error(f"Failed to load workflow '{selected_workflow_name}'.")
                spacer.line()
                prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)
                return

            # Show workflow info panel and ask for confirmation
            panel = PanelRenderer()
            if not _show_workflow_info_panel(parsed_workflow, panel, spacer, prompts):
                spacer.line()
                prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)
                return

            spacer.line()
            text.info("✨ Executing workflow...")
            spacer.small()

            # Build execution context
            secrets = SecretManager(project_path=config.project_root)

            ui = UIComponents(
                text=text,
                panel=panel,
                table=TableRenderer(),
                spacer=spacer
            )

            ctx_builder = WorkflowContextBuilder(
                plugin_registry=config.registry,
                secrets=secrets,
                ai_config=config.config.ai
            )
            ctx_builder.with_ui(ui=ui)
            ctx_builder.with_ai()  # Initialize AI client

            # Add registered plugins to context
            for plugin_name in config.registry.list_installed():
                plugin = config.registry.get_plugin(plugin_name)
                if plugin:
                    client = plugin.get_client()
                    if hasattr(ctx_builder, f"with_{plugin_name}"):
                        getattr(ctx_builder, f"with_{plugin_name}")(client)

            execution_context = ctx_builder.build()
            executor = WorkflowExecutor(config.registry)

            # Execute workflow (steps handle their own UI)
            executor.execute(parsed_workflow, execution_context)

        except (WorkflowNotFoundError, WorkflowExecutionError) as e:
            text.error(str(e))
        except Exception as e:
            text.error(f"An unexpected error occurred: {type(e).__name__} - {e}")

    spacer.line()
    prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)


def _show_workflow_info_panel(workflow, panel: PanelRenderer, spacer: SpacerRenderer, prompts: PromptsRenderer) -> bool:
    """
    Shows a generic info panel for any workflow with its steps and asks for confirmation.

    Args:
        workflow: ParsedWorkflow instance
        panel: Panel renderer
        spacer: Spacer renderer
        prompts: Prompts renderer

    Returns:
        bool: True if user wants to execute, False to cancel
    """
    # Build list of steps
    steps_list_parts = []
    for i, step in enumerate(workflow.steps):
        step_name = step.get("name") or step.get("id")
        if not step_name:
            step_name = f"Hook: {step.get('hook')}" if step.get('hook') else "unnamed"
        steps_list_parts.append(f"  {i+1}. {step_name}")
    steps_list = "\n".join(steps_list_parts)

    # Use only the first line of the description
    description = workflow.description.split('\n')[0] if workflow.description else ""

    content = f"{description}\n\nSteps:\n{steps_list}"

    panel.print(
        content,
        panel_type="info",
        title=f"Workflow: {workflow.name}"
    )
    spacer.small()

    return prompts.ask_confirm("Execute this workflow?", default=True)


def show_interactive_menu():
    """
    Displays the main interactive menu for the Titan CLI. 
    
    This function serves as the primary user interface when the CLI is run
    without any subcommands. It handles the initial setup, displays a persistent
    menu of actions, and routes the user to the correct functionality.
    The menu loops after each action until the user chooses to exit.
    """
    text = TextRenderer()
    prompts = PromptsRenderer(text_renderer=text)
    spacer = SpacerRenderer()

    # Get version for subtitle
    cli_version = get_version()
    subtitle = f"Development Tools Orchestrator v{cli_version}"

    # Check for project_root and prompt if not set (only runs once)
    config = TitanConfig()
    project_root = config.get_project_root()
    if not project_root or not Path(project_root).is_dir():
        if not _prompt_for_project_root(text, prompts):
            text.warning(msg.Config.PROJECT_ROOT_SETUP_CANCELLED)
            raise typer.Exit(0)
        # Reload config after setting it
        config.load()
        project_root = config.get_project_root() # Re-fetch project root

    while True:
        # Re-render banner and menu in each loop iteration
        render_titan_banner(subtitle=subtitle)
        
        # Build and show the main menu
        menu_builder = DynamicMenu(title=msg.Interactive.MAIN_MENU_TITLE, emoji="🚀")
        menu_builder.add_top_level_item("Launch Claude Code", "Open an interactive session with Claude Code CLI.", "code")
        menu_builder.add_top_level_item("Project Management", "List, configure, or initialize projects.", "projects")
        menu_builder.add_top_level_item("Workflows", "Execute a predefined or custom workflow.", "run_workflow")
        menu_builder.add_top_level_item("AI Configuration", "Configure AI providers and test connections.", "ai_config")
        menu_builder.add_top_level_item("Exit", "Exit the application.", "exit")

        menu = menu_builder.to_menu()

        try:
            choice_item = prompts.ask_menu(menu, allow_quit=False)
        except (KeyboardInterrupt, EOFError):
            choice_item = None

        spacer.line()

        choice_action = "exit"
        if choice_item:
            choice_action = choice_item.action

        if choice_action == "code":
            launch_code(prompt=None)
            spacer.line()
            prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)

        elif choice_action == "projects":
            _show_projects_submenu(prompts, text, config)

        elif choice_action == "run_workflow":
            _handle_run_workflow_action(config, text, spacer, prompts)

        elif choice_action == "ai_config":
            _show_ai_config_submenu(prompts, text, config)

        elif choice_action == "exit":
            text.body(msg.Interactive.GOODBYE)
            break



@app.callback()
def main(ctx: typer.Context):
    """Titan CLI - Main entry point"""
    if ctx.invoked_subcommand is None:
        show_interactive_menu()


@app.command()
def version():
    """Show Titan CLI version."""
    cli_version = get_version()
    typer.echo(msg.CLI.VERSION.format(version=cli_version))
