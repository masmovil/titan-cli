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
from titan_cli.core.config import TitanConfig
from titan_cli.core.errors import ConfigWriteError
from titan_cli.core.discovery import discover_projects
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.ui.components.table import TableRenderer
from titan_cli.ui.views.prompts import PromptsRenderer
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


# --- Helper function for version retrieval ---
def get_version() -> str:
    """Retrieves the package version from pyproject.toml."""
    return importlib.metadata.version("titan-cli")


def _prompt_for_project_root(text: TextRenderer, prompts: PromptsRenderer) -> bool:
    """Asks the user for the project root and saves it to the global config."""
    text.title("👋 Welcome to Titan CLI! Let's get you set up.")
    text.line()
    text.info("To get started, Titan needs to know where you store your projects.")
    text.body("This is the main folder where you keep all your git repositories (e.g., ~/git, ~/Projects).")
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
        project_root_str = prompts.ask_text(
            "Enter the absolute path to your projects root directory",
            default=str(Path.home())
        )
        if not project_root_str:
            return False

        project_root = str(Path(project_root_str).expanduser().resolve())
        config.setdefault("core", {})["project_root"] = project_root

        with open(global_config_path, "wb") as f:
            tomli_w.dump(config, f)

        text.success(f"Configuration saved. Project root set to: {project_root}")
        text.line()
        return True

    except (EOFError, KeyboardInterrupt):
        return False
    except (OSError, PermissionError) as e:
        error = ConfigWriteError(file_path=str(global_config_path), original_exception=e)
        text.error(str(error))
        return False


def show_interactive_menu():
    """Display interactive menu system."""
    text = TextRenderer()
    prompts = PromptsRenderer(text_renderer=text)

    # Get version for subtitle
    cli_version = get_version()
    subtitle = f"Development Tools Orchestrator v{cli_version}"

    # Show welcome banner
    render_titan_banner(subtitle=subtitle)

    # Check for project_root and prompt if not set
    config = TitanConfig()
    project_root = config.get_project_root()

    if not project_root or not Path(project_root).is_dir():
        if not _prompt_for_project_root(text, prompts):
            text.warning(msg.Errors.OPERATION_CANCELLED_NO_CHANGES)
            raise typer.Exit(0)
        # Reload config after setting it
        config.load()
        render_titan_banner(subtitle=subtitle)

    # Build and show the main menu
    menu_builder = DynamicMenu(title="What would you like to do?", emoji="🚀")
    menu_builder.add_category("Project Management", emoji="📂") \
        .add_item("List Configured Projects", "Scan the project root and show all configured Titan projects.", "list") \
        .add_item("Configure a New Project", "See unconfigured projects and learn how to initialize them.", "configure")
    
    menu_builder.add_category("Exit", emoji="🚪") \
        .add_item("Exit", "Exit the application.", "exit")
    
    menu = menu_builder.to_menu()

    try:
        choice_item = prompts.ask_menu(menu, allow_quit=False) # Explicit exit option is clearer
    except (KeyboardInterrupt, EOFError):
        choice_item = None # Treat Ctrl+C as an exit action

    spacer = SpacerRenderer()
    spacer.line()

    # Default to exit if user cancels
    choice_action = "exit"
    if choice_item:
        choice_action = choice_item.action

    if choice_action == "list":
        list_projects()
    elif choice_action == "configure":
        # Temporary logic as discussed
        text.title("Configure a New Project")
        spacer.line()
        project_root = config.get_project_root()
        if not project_root:
            text.error("Project root not set. Cannot discover projects.")
            raise typer.Exit(1)
            
        _conf, unconfigured = discover_projects(str(project_root))
        if unconfigured:
            text.warning("Found these unconfigured Git projects:")
            table_renderer = TableRenderer()
            headers = ["Project Name", "Path"]
            rows = []
            for p in unconfigured:
                try:
                    rel_path = str(p.relative_to(project_root))
                except ValueError:
                    rel_path = str(p) # Fallback to absolute path
                rows.append([p.name, rel_path])
            table_renderer.print_table(headers=headers, rows=rows)
            spacer.line()
            text.info("To initialize a project, navigate to its directory and run: [primary]titan init[/primary]")
        else:
            text.success("No unconfigured Git projects found in your project root.")
    elif choice_action == "exit":
        text.body("Goodbye!")
        raise typer.Exit()


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