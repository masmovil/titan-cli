"""
Preview Subcommand Module

This module contains the Typer sub-application for previewing UI components.
It is imported by the main cli.py and added as a subcommand.
"""

import typer
import runpy

# Sub-application for 'preview' commands
preview_app = typer.Typer(name="preview", help="Preview UI components in isolation.")


@preview_app.command("panel")
def preview_panel():
    """
    Shows a preview of the Panel component with all its variations.
    """
    try:
        runpy.run_module("titan_cli.ui.components.__previews__.panel_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)


@preview_app.command("typography")
def preview_typography():
    """
    Shows a preview of the Typography component with all its variations.
    """
    try:
        runpy.run_module("titan_cli.ui.components.__previews__.typography_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)


@preview_app.command("table")
def preview_table():
    """
    Shows a preview of the Table component with all its variations.
    """
    try:
        runpy.run_module("titan_cli.ui.components.__previews__.table_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)


@preview_app.command("spacer")
def preview_spacer():
    """
    Shows a preview of the Spacer component with all its variations.
    """
    try:
        runpy.run_module("titan_cli.ui.components.__previews__.spacer_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)


@preview_app.command("config")
def preview_config():
    """
    Shows a preview of the TitanConfig component.
    """
    try:
        runpy.run_module("titan_cli.core.__previews__.config_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)


@preview_app.command("prompts")
def preview_prompts():
    """
    Shows a non interactive preview of the Prompts component.
    """
    try:
        runpy.run_module("titan_cli.ui.views.__previews__.prompts_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)


@preview_app.command("menu")
def preview_menu():
    """
    Shows an interactive preview of the Menu component.
    """
    try:
        runpy.run_module("titan_cli.ui.views.menu_components.__previews__.menu_preview", run_name="__main__")
    except ModuleNotFoundError:
        typer.secho("Error: Preview script not found.", fg=typer.colors.RED)
        raise typer.Exit(1)


@preview_app.command("workflow")
def preview_workflow(name: str):
    """
    Shows a preview of a workflow with mocked data.

    Args:
        name: Name of the workflow to preview (e.g., 'create-pr-ai')
    """
    from pathlib import Path
    import sys

    normalized_name = name.replace('-', '_')
    preview_filename = f"{normalized_name}_preview.py"

    # Try multiple locations for the preview file
    search_paths = [
        # 1. System workflows
        Path(__file__).parent / "workflows" / "__previews__" / preview_filename,
        # 2. GitHub plugin workflows (relative to this file)
        Path(__file__).parent.parent / "plugins" / "titan-plugin-github" / "titan_plugin_github" / "workflows" / "__previews__" / preview_filename,
        # 3. Git plugin workflows
        Path(__file__).parent.parent / "plugins" / "titan-plugin-git" / "titan_plugin_git" / "workflows" / "__previews__" / preview_filename,
    ]

    for preview_path in search_paths:
        if preview_path.exists():
            try:
                # Execute the file directly
                with open(preview_path, 'r') as f:
                    code = compile(f.read(), preview_path, 'exec')
                    exec(code, {'__name__': '__main__'})
                return  # Success!
            except Exception as e:
                typer.secho(f"Error executing preview: {e}", fg=typer.colors.RED)
                raise typer.Exit(1)

    # If we get here, preview was not found in any location
    typer.secho(f"Error: Preview for workflow '{name}' not found.", fg=typer.colors.RED)
    typer.secho(f"Searched in:", fg=typer.colors.YELLOW)
    for path in search_paths:
        typer.secho(f"  - {path}", fg=typer.colors.YELLOW)
    raise typer.Exit(1)
