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

from titan_cli.ui.views.banner import render_titan_banner
from titan_cli.messages import msg
from titan_cli.preview import preview_app
from titan_cli.commands.init import init_app
from titan_cli.commands.projects import projects_app, list_projects
from titan_cli.commands.ai import ai_app
from titan_cli.commands.plugins import plugins_app
from titan_cli.commands.cli import cli_app
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
from titan_cli.core.plugins.available import KNOWN_PLUGINS

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
app.add_typer(cli_app)


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
        try:
            config.set_active_project(choice.action)
            text.success(msg.Projects.ACTIVE_PROJECT_SET.format(project_name=choice.action))
            # Reload config to ensure new active project's settings are loaded
            config.load()
        except ConfigWriteError as e:
            text.error(str(e))


def _show_cli_submenu(prompts: PromptsRenderer, text: TextRenderer):
    """Shows the submenu for launching external CLIs."""
    from titan_cli.utils.cli_configs import CLI_REGISTRY
    from titan_cli.utils.cli_launcher import CLILauncher
    from titan_cli.utils.launch_helper import launch_cli_tool

    while True:
        submenu_builder = DynamicMenu(title=msg.ExternalCLI.MENU_TITLE, emoji="🚀")
        action_category = submenu_builder.add_category(msg.ExternalCLI.AVAILABLE_CLIS_TITLE)
        
        available_clis = []
        for cli_name, config in CLI_REGISTRY.items():
            if CLILauncher(cli_name).is_available():
                display_name = config.get("display_name", cli_name)
                action_category.add_item(display_name, f"Launch {display_name}", cli_name)
                available_clis.append(cli_name)

        if not available_clis:
            text.warning(msg.ExternalCLI.NO_CLIS_FOUND)
            text.body(msg.ExternalCLI.INSTALL_SUGGESTION, style="dim")
            return

        submenu_builder.add_category(msg.Interactive.MENU_EXIT).add_item(msg.Interactive.RETURN_TO_MENU_PROMPT, "", "back")

        choice_item = prompts.ask_menu(submenu_builder.to_menu())
        if not choice_item or choice_item.action == "back":
            break

        launch_cli_tool(choice_item.action, prompt=None)

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
                initialize_project(Path(chosen_project_item.action), config.registry)

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
    spacer = SpacerRenderer()

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

            # Find the plugin definition to check dependencies
            selected_plugin = next((p for p in KNOWN_PLUGINS if p["package_name"] == plugin_to_install), None)

            if not selected_plugin:
                text.error(f"Plugin '{plugin_to_install}' not found in known plugins.")
                continue

            # Check if dependencies are met
            if selected_plugin.get("dependencies"):
                installed_plugin_names = config.registry.list_installed()
                missing_deps = [dep for dep in selected_plugin["dependencies"] if dep not in installed_plugin_names]

                if missing_deps:
                    text.error(f"Cannot install '{selected_plugin['name']}': missing required dependencies.")
                    text.body(f"Required plugins: {', '.join(missing_deps)}", style="yellow")
                    text.info("Please install the required plugins first.")
                    spacer.line()
                    continue

            text.info(f"Installing {plugin_to_install}...")

            try:
                # Detect if we're in development (local plugins/) or production (installed from PyPI)
                cli_file_path = Path(__file__).resolve()
                project_root = cli_file_path.parent.parent
                plugin_path = project_root / "plugins" / plugin_to_install

                # Check if local plugin directory exists (development mode)
                if plugin_path.exists():
                    # Development mode: install from local path
                    text.body(f"Installing from local path: {plugin_path}", style="dim")
                    result = subprocess.run(
                        ["pipx", "inject", "titan-cli", str(plugin_path)],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                else:
                    # Production mode: install from PyPI
                    text.body(f"Installing from PyPI: {plugin_to_install}", style="dim")
                    result = subprocess.run(
                        ["pipx", "inject", "titan-cli", plugin_to_install],
                        capture_output=True,
                        text=True,
                        check=False
                    )

                if result.returncode == 0:
                    text.success(f"Successfully installed {plugin_to_install}.")

                    # After successful installation, automatically configure the plugin
                    spacer.line()
                    config.registry.reset()

                    # Use the existing interactive configuration function
                    if _configure_plugin_interactive(selected_plugin['name']):
                        text.success(f"Plugin '{selected_plugin['name']}' has been configured successfully.")
                    else:
                        text.warning(f"Plugin '{selected_plugin['name']}' configuration was skipped or failed.")
                        text.info("You can configure it later from 'Enable/Disable Plugins' menu.")
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

    def _configure_plugin_interactive(plugin_name: str) -> bool:
        """
        Prompts user for plugin configuration interactively.

        Returns:
            True if configuration succeeded, False otherwise
        """
        # Get the plugin instance (could be initialized or not)
        # Try from active plugins first, then from all discovered plugins
        plugin = config.registry.get_plugin(plugin_name)

        # If not in active plugins, it might be in _plugins (discovered but not initialized)
        if not plugin:
            plugin = config.registry._plugins.get(plugin_name)

        # If still not found, try to reload it from entry points
        if not plugin:
            from importlib.metadata import entry_points
            discovered = entry_points(group='titan.plugins')
            for ep in discovered:
                if ep.name == plugin_name:
                    try:
                        plugin_class = ep.load()
                        plugin = plugin_class()
                        break
                    except Exception as e:
                        text.error(f"Failed to load plugin '{plugin_name}': {e}")
                        return False

        if not plugin:
            text.warning(f"Cannot find plugin '{plugin_name}'.")
            return False

        # Check if plugin supports configuration
        if not hasattr(plugin, "get_config_schema"):
            text.info(f"Plugin '{plugin_name}' does not require configuration.")
            return True  # Allow enabling even without config schema

        try:
            schema = plugin.get_config_schema()
        except Exception as e:
            text.warning(f"Cannot get configuration schema: {e}")
            return False

        properties = schema.get("properties", {})
        if not properties:
            text.info(f"Plugin '{plugin_name}' has no required configuration.")
            return True  # No config needed, allow enabling

        text.subtitle(f"Configuring Plugin: {plugin_name}")
        spacer.small()

        # Get current config values if any
        current_plugin_config = {}
        if config.config.plugins and plugin_name in config.config.plugins:
            plugin_entry = config.config.plugins[plugin_name]
            if hasattr(plugin_entry, 'config'):
                current_plugin_config = plugin_entry.config or {}

        new_config_values = {}

        # Track secrets separately
        secrets_to_save = {}

        # Iterate over schema and ask for values
        for field_name, field_schema in properties.items():
            field_type = field_schema.get("type")
            description = field_schema.get("description", "")
            field_format = field_schema.get("format", "")
            current_value = current_plugin_config.get(field_name, field_schema.get("default"))
            is_required = field_name in schema.get("required", [])

            # Skip fields that have defaults and are not required
            # (they will use their default values from the model)
            has_default = "default" in field_schema
            if not is_required and has_default and field_name not in current_plugin_config:
                # Use default value, don't prompt
                continue

            # Detect if this is a secret field (by name pattern or format)
            is_secret = (
                "token" in field_name.lower() or
                "password" in field_name.lower() or
                "secret" in field_name.lower() or
                "api_key" in field_name.lower() or
                field_format == "password"
            )

            prompt_text = f"{field_name}"
            if description:
                prompt_text += f" ({description})"
            if is_required:
                prompt_text += " [required]"

            # Simple type handling
            if field_type == "boolean":
                new_value = prompts.ask_confirm(prompt_text, default=bool(current_value) if current_value is not None else False)
            elif field_type == "integer":
                new_value = prompts.ask_int(prompt_text, default=int(current_value) if current_value is not None else None)
            elif field_type == "array" and field_schema.get("items", {}).get("type") == "string":
                current_list = current_value or []
                text.body(prompt_text)
                if current_list:
                    text.body(f"Current: {', '.join(current_list)}", style="dim")
                new_value_str = prompts.ask_text("Enter comma-separated values" + (" (leave blank to keep current)" if current_list else "") + ":")
                if new_value_str and new_value_str.strip():
                    new_value = [item.strip() for item in new_value_str.split(",")]
                else:
                    new_value = current_list
            else:  # Default to string
                default_val = str(current_value) if current_value is not None else ""
                # For secrets, check if already exists in keychain
                if is_secret:
                    # Try to get from keychain with project-specific key
                    project_name = config.get_active_project()
                    secret_key = f"{plugin_name}_{field_name}"
                    keychain_key = f"{project_name}_{secret_key}" if project_name else secret_key

                    # Also try without project prefix for backwards compatibility
                    existing_secret = config.secrets.get(keychain_key) or config.secrets.get(secret_key)

                    if existing_secret:
                        text.body("(Already configured)", style="dim")
                        skip_secret = prompts.ask_confirm("Keep existing value?", default=True)
                        if skip_secret:
                            # Keep the existing secret (will be saved to keychain later)
                            secrets_to_save[secret_key] = existing_secret
                            continue  # Don't prompt for new value

                # Ask for value (hidden if secret)
                new_value = prompts.ask_text(prompt_text, default=default_val if not is_secret else "", password=is_secret)
                if new_value is None or (not new_value and is_required):
                    if is_required:
                        text.error(f"Field '{field_name}' is required.")
                        return False
                    new_value = ""

            # Store secrets separately
            if is_secret and new_value:
                secrets_to_save[f"{plugin_name}_{field_name}"] = new_value
            else:
                new_config_values[field_name] = new_value

        # Save the configuration
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

            # Save secrets to user keychain (secure, per-project)
            # Use project name in key to support multiple projects
            project_name = config.get_active_project()
            for secret_key, secret_value in secrets_to_save.items():
                # Format: projectname_pluginname_fieldname (e.g., titan-cli_jira_api_token)
                keychain_key = f"{project_name}_{secret_key}" if project_name else secret_key
                config.secrets.set(keychain_key, secret_value, scope="user")

            spacer.small()
            text.success(f"Configuration for '{plugin_name}' saved successfully.")
            if secrets_to_save:
                text.info(f"Saved {len(secrets_to_save)} secret(s) to project secrets.")
            return True

        except Exception as e:
            text.error(f"Failed to save configuration: {e}")
            return False

    def toggle_plugins_handler():
        """Handles enabling/disabling plugins for the current project."""
        if not config.get_active_project() or not config.project_config_path:
            text.error("No active project selected. Please use 'Switch Project' first.")
            return

        while True:
            # Reload config on each loop to get the latest status
            config.load()
            # We need all discovered plugins to show their enabled/disabled status
            installed_plugins = config.registry.list_discovered()

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

            # If enabling, ask for configuration first
            if new_status:
                spacer.line()
                text.info(f"Enabling plugin '{plugin_to_toggle}'...")
                spacer.small()

                if not _configure_plugin_interactive(plugin_to_toggle):
                    text.warning(f"Plugin '{plugin_to_toggle}' was not enabled due to configuration errors.")
                    spacer.line()
                    continue

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

                spacer.small()
                text.success(f"Plugin '{plugin_to_toggle}' has been {'enabled' if new_status else 'disabled'}.")

                # Reload config to reinitialize plugins
                if new_status:
                    text.info("Reloading configuration...")
                    config.load()

                    # Check if plugin initialized successfully
                    failed = config.registry.list_failed()
                    if plugin_to_toggle in failed:
                        text.error(f"Plugin '{plugin_to_toggle}' failed to initialize:")
                        text.body(str(failed[plugin_to_toggle]), style="red")

                        # Revert to disabled
                        plugin_specific_table["enabled"] = False
                        with open(project_cfg_path, "wb") as f:
                            tomli_w.dump(project_cfg_dict, f)
                        config.load()
                        text.warning(f"Plugin '{plugin_to_toggle}' has been disabled due to initialization failure.")

                spacer.line()

            except (tomli.TOMLDecodeError, OSError) as e:
                text.error(f"Error updating config file: {e}")
                spacer.line()
            except Exception as e:
                text.error(f"An unexpected error occurred: {e}")
                spacer.line()

    # --- Action Loop ---
    while True:
        # We rebuild the menu inside the loop to refresh the active project name
        submenu_builder = DynamicMenu(title="Plugin Management", emoji="🔌")
        
        # Global Actions
        global_cat = submenu_builder.add_category("Global")
        global_cat.add_item("Install a new Plugin", "Install a new plugin from a known list.", "install")
        global_cat.add_item("List Installed Plugins", "List all globally installed plugins.", "list")

        # Project-specific Actions (only if there's an active project)
        active_project_name = config.get_active_project()
        if active_project_name:
            project_cat = submenu_builder.add_category(f"Current Project ({active_project_name})")
            project_cat.add_item("Enable/Disable Plugins", "Enable or disable plugins for the current project.", "toggle")

        submenu_builder.add_category("Back").add_item("Return to Main Menu", "", "back")

        choice_item = prompts.ask_menu(submenu_builder.to_menu(), allow_quit=False)
        if not choice_item or choice_item.action == "back":
            break

        action_map = {
            "install": install_plugin_handler,
            "list": list_plugins_handler,
            "toggle": toggle_plugins_handler
        }
        
        handler = action_map.get(choice_item.action)
        if handler:
            handler()

        # Pause and wait for user to return, unless it was the list action
        if choice_item and choice_item.action:
             prompts.ask_confirm(msg.Interactive.RETURN_TO_MENU_PROMPT_CONFIRM, default=True)


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
    while True:
        text.title("Run a Workflow")
        spacer.line()

        # Reload config to ensure latest changes are picked up
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
            original_cwd = os.getcwd()

            try:
                parsed_workflow = config.workflows.get_workflow(selected_workflow_name)
                if not parsed_workflow:
                    text.error(f"Failed to load workflow '{selected_workflow_name}'.")
                    continue # Loop back to menu

                # Show workflow info panel and ask for confirmation
                if not _show_workflow_info_panel(parsed_workflow, PanelRenderer(), spacer, prompts):
                    continue # Loop back to menu if user cancels

                spacer.line()
                text.info("✨ Executing workflow...")
                spacer.small()

                if config.active_project_path:
                    os.chdir(config.active_project_path)
                    text.body(f"Working directory: {config.active_project_path}", style="dim")
                    spacer.small()

                secrets = SecretManager(project_path=config.active_project_path or config.project_root)
                
                ui_components = UIComponents(
                    text=text,
                    panel=PanelRenderer(),
                    table=TableRenderer(),
                    spacer=spacer
                )
                
                ctx_builder = WorkflowContextBuilder(
                    plugin_registry=config.registry,
                    secrets=secrets,
                    ai_config=config.config.ai
                )
                ctx_builder.with_ui(ui=ui_components)
                ctx_builder.with_ai()
                
                # Add registered plugins to context
                for plugin_name in config.registry.list_installed():
                    plugin = config.registry.get_plugin(plugin_name)
                    if plugin and hasattr(ctx_builder, f"with_{plugin_name}"):
                        try:
                            client = plugin.get_client()
                            getattr(ctx_builder, f"with_{plugin_name}")(client)
                        except Exception:
                            # Plugin client initialization failed (e.g., missing credentials).
                            # This is acceptable - workflow steps using this plugin will
                            # fail gracefully with a clear error message when they try to access it.
                            # We don't stop execution here to allow workflows that don't need
                            # this plugin to run successfully.
                            pass

                execution_context = ctx_builder.build()
                executor = WorkflowExecutor(config.registry, config.workflows)

                executor.execute(parsed_workflow, execution_context)

            except (WorkflowNotFoundError, WorkflowExecutionError) as e:
                text.error(str(e))
            except Exception as e:
                text.error(f"An unexpected error occurred: {type(e).__name__} - {e}")
            finally:
                os.chdir(original_cwd) # Always restore

            spacer.line()
            text.info("Workflow execution finished. Returning to workflow list...")
            spacer.line()
        else:
            # User chose to cancel or exited prompt
            break


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
    # Build visually enhanced list of steps
    steps_list_parts = []

    for i, step in enumerate(workflow.steps):
        step_id = step.get("id", "")
        step_name = step.get("name") or step_id

        # Determine step type and icon
        if step.get("hook"):
            # Hook injection point
            icon = "⚡"
            step_type = f"[dim]hook:[/dim] {step.get('hook')}"
            step_display = f"{icon} {step_type}"
        elif step.get("workflow"):
            # Nested workflow
            icon = "🔄"
            workflow_name = step.get("workflow")
            step_type = f"[cyan]workflow:[/cyan] {workflow_name}"
            step_display = f"{icon} {step_name}\n      [dim]{step_type}[/dim]"
        elif step.get("plugin") and step.get("step"):
            # Plugin step
            icon = "🔧"
            plugin = step.get("plugin")
            plugin_step = step.get("step")
            step_type = f"[blue]{plugin}[/blue].[dim]{plugin_step}[/dim]"
            step_display = f"{icon} {step_name}\n      [dim]{step_type}[/dim]"
        elif step.get("command"):
            # Command step
            icon = "💻"
            command = step.get("command")
            # Truncate long commands
            command_preview = command[:50] + "..." if len(command) > 50 else command
            step_display = f"{icon} {step_name}\n      [dim]$ {command_preview}[/dim]"
        else:
            # Unknown/fallback
            icon = "❓"
            step_display = f"{icon} {step_name}"

        # Add step number and content
        steps_list_parts.append(f"  [bold]{i+1}.[/bold] {step_display}")

    steps_list = "\n".join(steps_list_parts)

    # Use only the first line of the description
    description = workflow.description.split('\n')[0] if workflow.description else ""

    # Build metadata section
    metadata_parts = []
    if workflow.source:
        metadata_parts.append(f"[dim]Source:[/dim] {workflow.source}")
    if workflow.params:
        param_count = len(workflow.params)
        metadata_parts.append(f"[dim]Parameters:[/dim] {param_count} configured")

    metadata = "\n".join(metadata_parts) if metadata_parts else ""

    # Compose final content
    content_parts = []
    if description:
        content_parts.append(description)
    if metadata:
        content_parts.append(f"\n{metadata}")
    content_parts.append(f"\n[bold]Steps:[/bold]\n{steps_list}")

    content = "\n".join(content_parts)

    panel.print(
        content,
        panel_type="info",
        title=f"📋 Workflow: {workflow.name}"
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
        menu_builder.add_top_level_item("Launch External CLI", "Open an interactive session with an external CLI.", "cli")
        menu_builder.add_top_level_item("Project Management", "List, configure, or initialize projects.", "projects")

        # Only show Workflows if there are enabled plugins
        installed_plugins = config.registry.list_installed()
        enabled_plugins = [p for p in installed_plugins if config.is_plugin_enabled(p)]
        if enabled_plugins:
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

        if choice_action == "cli":
            _show_cli_submenu(prompts, text)

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
    
