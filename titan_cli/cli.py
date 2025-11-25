"""
Titan CLI - Main CLI application

Combines all tool commands into a single CLI interface.
"""

import typer
import importlib.metadata
from titan_cli.ui.views.banner import render_titan_banner
from titan_cli.messages import msg

app = typer.Typer(
    name=msg.CLI.APP_NAME,
    help=msg.CLI.APP_DESCRIPTION,
    invoke_without_command=True,
    no_args_is_help=False,
)


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
    cli_version = importlib.metadata.version("titan-cli")
    typer.echo(msg.CLI.VERSION.format(version=cli_version))


def show_interactive_menu():
    """Display interactive menu system"""
    
    # Get version for subtitle
    version = importlib.metadata.version("titan-cli")
    subtitle = f"Development Tools Orchestrator v{version}"

    # Show welcome banner
    render_titan_banner(subtitle=subtitle)

