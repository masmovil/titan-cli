"""
Titan CLI - Main CLI application

Combines all tool commands into a single CLI interface.
"""

import typer
import importlib.metadata
from titan_cli.ui.views.banner import render_titan_banner
from titan_cli.messages import msg
from titan_cli.preview import preview_app # Import the preview subcommand
from titan_cli.commands.init import init_app # Import the init subcommand
from titan_cli.commands.projects import projects_app # Import the projects subcommand

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
# --- End of Helper function ---


@app.callback()
def main(ctx: typer.Context):
    """Titan CLI - Main entry point"""
    # If no subcommand was invoked, show interactive menu
    if ctx.invoked_subcommand is None:
        show_interactive_menu()


@app.command()
def version():
    """
    Show Titan CLI version.
    """
    cli_version = get_version() # Use helper function
    typer.echo(msg.CLI.VERSION.format(version=cli_version))


def show_interactive_menu():
    """Display interactive menu system"""
    
    # Get version for subtitle
    version = get_version() # Use helper function
    subtitle = f"Development Tools Orchestrator v{version}"

    # Show welcome banner
    render_titan_banner(subtitle=subtitle)