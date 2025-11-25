"""
Titan CLI - Main CLI application

Combines all tool commands into a single CLI interface.
"""

import typer
import importlib.metadata
from titan_cli.ui.banner import render_titan_banner

app = typer.Typer(
    name="titan",
    help="Titan CLI - Development tools orchestrator",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback()
def main(ctx: typer.Context):
    """
    Titan CLI - Development tools orchestrator

    When run without arguments, shows interactive menu.
    """
    # If no subcommand was invoked, show interactive menu
    if ctx.invoked_subcommand is None:
        show_interactive_menu()


@app.command()
def version():
    """
    Show Titan CLI version.
    """
    cli_version = importlib.metadata.version("titan-cli")
    typer.echo(f"Titan CLI v{cli_version}")


def show_interactive_menu():
    """Display interactive menu system"""
    
    # Show welcome banner
    render_titan_banner()

