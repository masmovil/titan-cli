"""
Titan CLI - Main CLI application

Combines all tool commands into a single CLI interface.
"""

import typer
import tomli
import tomli_w
import importlib.metadata
from pathlib import Path

from titan_cli.ui.views.banner import render_titan_banner
from titan_cli.messages import msg
from titan_cli.preview import preview_app
from titan_cli.commands.init import init_app
from titan_cli.commands.projects import projects_app, list_projects
from titan_cli.commands.ai import ai_app
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.core.errors import ConfigWriteError
from titan_cli.core.discovery import discover_projects
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.ui.views.prompts import PromptsRenderer
from titan_cli.core.project_init import initialize_project
from titan_cli.ui.views.menu_components.dynamic_menu import DynamicMenu


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

    # Initial Welcome Banner - removed as banner is rendered in the loop
    # render_titan_banner(subtitle=subtitle)

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
        menu_builder.add_category("Project Management", emoji="📂") \
            .add_item(msg.Projects.LIST_TITLE, "Scan the project root and show all configured Titan projects.", "list") \
            .add_item(msg.Projects.CONFIGURE_TITLE, "Select an unconfigured project to initialize with Titan.", "configure")

        menu_builder.add_category("AI Configuration", emoji="🤖") \
            .add_item("Configure AI Provider", "Set up Anthropic, OpenAI, or Gemini", "ai_configure") \
            .add_item("Test AI Connection", "Verify AI provider is working", "ai_test")

        menu_builder.add_category("Exit", emoji="🚪") \
            .add_item("Exit", "Exit the application.", "exit")

        menu = menu_builder.to_menu()

        try:
            choice_item = prompts.ask_menu(menu, allow_quit=False)
        except (KeyboardInterrupt, EOFError):
            choice_item = None

        spacer.line()

        choice_action = "exit"
        if choice_item:
            choice_action = choice_item.action

        if choice_action == "list":
            list_projects()
            spacer.line()
            prompts.ask_text(msg.Interactive.RETURN_TO_MENU_PROMPT, default="")
        
        elif choice_action == "configure":
            text.title(msg.Projects.CONFIGURE_TITLE)
            spacer.line()
            project_root = config.get_project_root() # Re-fetch in case it was just set
            if not project_root:
                text.error(msg.Errors.PROJECT_ROOT_NOT_SET)
                break # Exit loop if something is wrong

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

                try:
                    chosen_project_item = prompts.ask_menu(project_menu, allow_quit=False)
                except (KeyboardInterrupt, EOFError):
                    chosen_project_item = None
                
                spacer.line()

                if chosen_project_item and chosen_project_item.action != "cancel":
                    initialize_project(Path(chosen_project_item.action))

            spacer.line()
            prompts.ask_text(msg.Interactive.RETURN_TO_MENU_PROMPT, default="")

        elif choice_action == "ai_configure":
            from titan_cli.commands.ai import configure_ai_interactive
            configure_ai_interactive()
            spacer.line()
            prompts.ask_text(msg.Interactive.RETURN_TO_MENU_PROMPT, default="")

        elif choice_action == "ai_test":
            from titan_cli.commands.ai import _test_ai_connection
            # We need to reload config and secrets in case they were just changed
            config.load() 
            secrets = SecretManager()
            if not config.config.ai:
                text.error("No AI provider configured. Please run 'Configure AI Provider' first.")
            else:
                provider = config.config.ai.provider
                model = config.config.ai.model
                
                base_url = config.config.ai.base_url
                
                _test_ai_connection(provider, secrets, model, base_url)
            spacer.line()
            prompts.ask_text(msg.Interactive.RETURN_TO_MENU_PROMPT, default="")

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