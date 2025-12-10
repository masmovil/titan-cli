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
import subprocess
import os
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
from titan_cli.core.plugins.plugin_registry import PluginRegistry

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


def _show_switch_project_menu(prompts: PromptsRenderer, text: TextRenderer, config: TitanConfig):
    """Shows submenu to switch active project."""
    project_root = config.get_project_root()
    if not project_root:
        text.error(msg.Errors.PROJECT_ROOT_NOT_SET)
        return

    configured_projects, _ = discover_projects(project_root)

    if not configured_projects:
        text.info("No configured projects found in project root.")
        return

    menu_builder = DynamicMenu(title="Select Active Project", emoji="📂")
    projects_cat = menu_builder.add_category("Projects")

    current_active_project = config.get_active_project()

    for project_path in configured_projects:
        project_name = project_path.name
        description = str(project_path.relative_to(project_root))
        if project_name == current_active_project:
            description = f"[bold green] (active)[/bold green] {description}"
        projects_cat.add_item(
            project_name,
            description,
            project_name
        )

    menu_builder.add_category("Cancel").add_item("Back to Main Menu", "", "cancel")
    menu = menu_builder.to_menu()

    choice = prompts.ask_menu(menu, allow_quit=False)

    if choice and choice.action and choice.action != "cancel":
        config.set_active_project(choice.action)
        text.success(f"Active project set to: {choice.action}")
        # Reload config to ensure new active project's settings are loaded
        config.load()

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


def _show_plugin_management_menu(prompts: PromptsRenderer, text: TextRenderer, config: TitanConfig):
    """Shows the submenu for plugin management."""
    from titan_cli.core.plugins.available import KNOWN_PLUGINS

    def install_plugin_handler():
        """Handles the interactive installation of plugins."""
        while True:
            config.registry.reset()
            installed_plugin_names = set(config.registry.list_installed())
            
            available_to_install = [
                p for p in KNOWN_PLUGINS if p["name"] not in installed_plugin_names
            ]

            if not available_to_install:
                text.success("All known official plugins are already installed.")
                break

            menu_builder = DynamicMenu(title="Install a Plugin", emoji="📦")
            plugin_cat = menu_builder.add_category("Available Plugins")
            for plugin_data in available_to_install:
                plugin_cat.add_item(
                    plugin_data["name"],
                    f"({plugin_data['package_name']}) {plugin_data['description']}",
                    plugin_data["package_name"] # The action is the package name for pipx
                )
            
            menu_builder.add_category("Back").add_item("Return to Previous Menu", "", "back")

            choice = prompts.ask_menu(menu_builder.to_menu(), allow_quit=False)

            if not choice or choice.action == "back":
                break

            plugin_to_install = choice.action
            text.info(f"Installing {plugin_to_install}...")

            try:
                # Build a robust path to the plugin directory, independent of CWD
                cli_file_path = Path(__file__).resolve()
                project_root = cli_file_path.parent.parent
                plugin_path = project_root / "plugins" / plugin_to_install

                if not plugin_path.exists():
                    text.error(f"Plugin source directory not found at: {plugin_path}")
                    continue

                # Use subprocess.run to execute the command with the absolute path
                result = subprocess.run(
                    f"pipx inject titan-cli '{plugin_path}'",
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode == 0:
                    text.success(f"Successfully installed {plugin_to_install}.")
                    text.info("Registry will be updated on next action.")
                else:
                    text.error(f"Failed to install {plugin_to_install}.")
                    if result.stderr:
                        text.body(result.stderr, style="dim")
            except Exception as e:
                text.error(f"An error occurred while trying to install {plugin_to_install}: {e}")

    def list_plugins_handler():
        """Lists all installed and failed plugins."""
        config.registry.reset()
        installed = config.registry.list_installed()
        failed = config.registry.list_failed()

        text.subtitle("Installed & Enabled Plugins")
        if not installed:
            text.body("  No plugins are currently installed and enabled.")
        else:
            for plugin_name in installed:
                text.body(f"  - {plugin_name}")
        
        text.line()

        if failed:
            text.subtitle("Failed Plugins")
            table = TableRenderer()
            table.print_table(
                headers=["Plugin", "Error"],
                rows=[[name, str(err)] for name, err in failed.items()],
            )
        else:
            text.success("All discovered plugins loaded successfully.")

    def toggle_plugins_handler():
        """Handles enabling/disabling plugins for the current project."""
        if not config.get_active_project() or not config.project_config_path:
            text.error("No active project selected. Please use 'Switch Project' first.")
            return

        while True:
            # Reload config on each loop to get the latest status
            config.load()
            installed_plugins = config.registry.list_installed()

            if not installed_plugins:
                text.info("No plugins are installed.")
                break

            menu_builder = DynamicMenu(title="Enable/Disable Plugins", emoji="🔄")
            plugin_cat = menu_builder.add_category("Installed Plugins")

            for plugin_name in installed_plugins:
                is_enabled = config.is_plugin_enabled(plugin_name)
                status_icon = "✅" if is_enabled else "❌"
                status_text = "enabled" if is_enabled else "disabled"
                plugin_cat.add_item(
                    f"{status_icon} {plugin_name}",
                    f"Currently {status_text}. Select to toggle.",
                    plugin_name
                )
            
            menu_builder.add_category("Back").add_item("Return to Previous Menu", "", "back")
            choice = prompts.ask_menu(menu_builder.to_menu(), allow_quit=False)

            if not choice or choice.action == "back":
                break

            plugin_to_toggle = choice.action
            current_status = config.is_plugin_enabled(plugin_to_toggle)
            new_status = not current_status

            try:
                # Read the existing project config file
                project_cfg_path = config.project_config_path
                project_cfg_dict = {}
                if project_cfg_path.exists():
                    with open(project_cfg_path, "rb") as f:
                        project_cfg_dict = tomli.load(f)

                # Ensure tables exist and set the new status
                plugins_table = project_cfg_dict.setdefault("plugins", {})
                plugin_specific_table = plugins_table.setdefault(plugin_to_toggle, {})
                plugin_specific_table["enabled"] = new_status

                # Write the updated config back
                with open(project_cfg_path, "wb") as f:
                    tomli_w.dump(project_cfg_dict, f)

                text.success(f"Plugin '{plugin_to_toggle}' has been {'enabled' if new_status else 'disabled'}.")
            
            except (tomli.TOMLDecodeError, OSError) as e:
                text.error(f"Error updating config file: {e}")
            except Exception as e:
                text.error(f"An unexpected error occurred: {e}")

    def configure_plugin_handler():
        """Handles configuring settings for an enabled plugin."""
        if not config.get_active_project() or not config.project_config_path:
            text.error("No active project selected. Please use 'Switch Project' first.")
            return

        config.load()
        installed_plugins = config.registry.list_installed()
        enabled_plugins = [p for p in installed_plugins if config.is_plugin_enabled(p)]

        if not enabled_plugins:
            text.info("No enabled plugins to configure for this project.")
            return

        # --- Menu to select which plugin to configure ---
        menu_builder = DynamicMenu(title="Configure a Plugin", emoji="🔧")
        plugin_cat = menu_builder.add_category("Enabled Plugins")
        for plugin_name in enabled_plugins:
            plugin_cat.add_item(f"Configure '{plugin_name}'", f"Edit settings for the {plugin_name} plugin.", plugin_name)
        menu_builder.add_category("Back").add_item("Return to Previous Menu", "", "back")
        
        choice = prompts.ask_menu(menu_builder.to_menu(), allow_quit=False)

        if not choice or choice.action == "back":
            return

        plugin_name = choice.action
        plugin = config.registry.get_plugin(plugin_name)

        if not plugin or not hasattr(plugin, "get_config_schema"):
            text.error(f"Plugin '{plugin_name}' does not support interactive configuration.")
            return

        schema = plugin.get_config_schema()
        properties = schema.get("properties", {})
        if not properties:
            text.info(f"Plugin '{plugin_name}' has no configurable properties.")
            return

        text.subtitle(f"Configuring Plugin: {plugin_name}")

        # --- Get current config values ---
        current_plugin_config = (config.config.plugins.get(plugin_name) or {}).config or {}
        new_config_values = {}

        # --- Iterate over schema and ask for new values ---
        for field_name, field_schema in properties.items():
            field_type = field_schema.get("type")
            description = field_schema.get("description", "")
            current_value = current_plugin_config.get(field_name, field_schema.get("default"))

            prompt_text = f"{field_name} ({description})"
            
            # Simple type handling
            if field_type == "boolean":
                new_value = prompts.ask_confirm(prompt_text, default=bool(current_value))
            elif field_type == "integer":
                new_value = prompts.ask_int(prompt_text, default=int(current_value) if current_value is not None else None)
            elif field_type == "array" and field_schema.get("items", {}).get("type") == "string":
                current_list = current_value or []
                text.body(prompt_text)
                text.body(f"Current values: {', '.join(current_list) if current_list else 'None'}", style="dim")
                new_value_str = prompts.ask_text("Enter new comma-separated values (or leave blank to keep current):")
                if new_value_str and new_value_str.strip():
                    new_value = [item.strip() for item in new_value_str.split(",")]
                else:
                    new_value = current_list # Keep current if blank
            else: # Default to string
                new_value = prompts.ask_text(prompt_text, default=str(current_value) if current_value is not None else "")
                if new_value is None:
                    new_value = "" # Coerce None from cancelled prompt to empty string
            
            new_config_values[field_name] = new_value

        # --- Save the new configuration ---
        try:
            project_cfg_path = config.project_config_path
            project_cfg_dict = {}
            if project_cfg_path.exists():
                with open(project_cfg_path, "rb") as f:
                    project_cfg_dict = tomli.load(f)

            plugins_table = project_cfg_dict.setdefault("plugins", {})
            plugin_specific_table = plugins_table.setdefault(plugin_name, {})
            plugin_config_table = plugin_specific_table.setdefault("config", {})
            
            # Update the config with the new values
            plugin_config_table.update(new_config_values)

            with open(project_cfg_path, "wb") as f:
                tomli_w.dump(project_cfg_dict, f)

            text.success(f"Configuration for '{plugin_name}' has been updated.")
            config.load() # Reload to reflect changes immediately
        
        except (tomli.TOMLDecodeError, OSError) as e:
            text.error(f"Error updating config file: {e}")
        except Exception as e:
            text.error(f"An unexpected error occurred: {e}")

    # --- Action Loop ---
    while True:
        # We rebuild the menu inside the loop to refresh the active project name
        submenu_builder = DynamicMenu(title="Plugin Management", emoji="🔌")
        
        # Global Actions
        global_cat = submenu_builder.add_category("Global")
        global_cat.add_item("Install a new Plugin", "Install a new plugin from a known list.", "install")
        global_cat.add_item("List Installed Plugins", "List all globally installed plugins.", "list")

        # Project-specific Actions
        active_project_name = config.get_active_project() or 'None'
        project_cat = submenu_builder.add_category(f"Current Project ({active_project_name})")
        project_cat.add_item("Enable/Disable Plugins", "Enable or disable plugins for the current project.", "toggle")
        project_cat.add_item("Configure Plugin Settings", "Configure settings for an enabled plugin.", "configure")

        submenu_builder.add_category("Back").add_item("Return to Main Menu", "", "back")

        choice_item = prompts.ask_menu(submenu_builder.to_menu(), allow_quit=False)
        if not choice_item or choice_item.action == "back":
            break

        action_map = {
            "install": install_plugin_handler,
            "list": list_plugins_handler,
            "toggle": toggle_plugins_handler,
            "configure": configure_plugin_handler
        }
        
        handler = action_map.get(choice_item.action)
        if handler:
            handler()

        # Pause and wait for user to return, unless it was the list action
        if choice_item and choice_item.action:
             prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)


def _show_ai_config_submenu(prompts: PromptsRenderer, text: TextRenderer, config: TitanConfig):
    """Shows the submenu for AI configuration."""
    from titan_cli.commands.ai import configure_ai_interactive, _test_ai_connection
    
    def configure_ai_handler():
        configure_ai_interactive()

    def test_ai_handler():
        config.load()
        secrets = SecretManager() # Re-init to load any new secrets
        if not config.config.ai:
            text.error("No AI provider configured. Please run 'Configure AI Provider' first.")
        else:
            provider = config.config.ai.provider
            model = config.config.ai.model
            base_url = config.config.ai.base_url
            _test_ai_connection(provider, secrets, model, base_url)

    _show_submenu(
        prompts,
        text,
        config,
        title="AI Configuration",
        emoji="⚙️",
        actions={
            "actions": [
                ("Configure AI Provider", "Set up Anthropic, OpenAI, or Gemini", "ai_configure"),
                ("Test AI Connection", "Verify AI provider is working", "ai_test")
            ],
            "handlers": {
                "ai_configure": configure_ai_handler,
                "ai_test": test_ai_handler
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

    # This is the entry point for interactive mode.
    # We create a single PluginRegistry that will be passed to the config.
    # The config object will be reloaded, but the registry will persist.
    plugin_registry = PluginRegistry()

    # Initial config load
    config = TitanConfig(registry=plugin_registry)

    # Check for project_root and prompt if not set (only runs once)
    project_root = config.get_project_root()
    if not project_root or not Path(project_root).is_dir():
        if not _prompt_for_project_root(text, prompts):
            text.warning(msg.Config.PROJECT_ROOT_SETUP_CANCELLED)
            raise typer.Exit(0)
        # Reload config after setting it
        config.load()
        project_root = config.get_project_root() # Re-fetch project root

    while True:
        # Before showing the menu, reload the config to get the latest state
        config.load()
        cli_version = get_version()

        # Get active project and append to subtitle if available
        active_project = config.get_active_project()
        subtitle = f"Development Tools Orchestrator v{cli_version}"
        if active_project:
            subtitle += f" | 📂 {active_project}"

        # Re-render banner and menu in each loop iteration
        render_titan_banner(subtitle=subtitle)
        
        # Build and show the main menu
        menu_builder = DynamicMenu(title=msg.Interactive.MAIN_MENU_TITLE, emoji="🚀")
        menu_builder.add_top_level_item("Launch Claude Code", "Open an interactive session with Claude Code CLI.", "code")
        menu_builder.add_top_level_item("Project Management", "List, configure, or initialize projects.", "projects")
        menu_builder.add_top_level_item("Workflows", "Execute a predefined or custom workflow.", "run_workflow")
        menu_builder.add_top_level_item("Plugin Management", "Install, configure, and manage plugins.", "plugin_management")
        menu_builder.add_top_level_item("AI Configuration", "Configure AI providers and test connections.", "ai_config")
        menu_builder.add_top_level_item("Switch Project", "Change the currently active project.", "switch_project")
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

        elif choice_action == "plugin_management":
            _show_plugin_management_menu(prompts, text, config)
            
        elif choice_action == "ai_config":
            _show_ai_config_submenu(prompts, text, config)
            
        elif choice_action == "switch_project":
            _show_switch_project_menu(prompts, text, config)
            # We don't ask for "return to menu" here, as the menu will just redisplay
            
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
