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
    import glob
    from pathlib import Path

    project_root = Path(__file__).parent.parent
    
    search_patterns = [
        str(project_root / "plugins" / "titan-plugin-*" / "titan_plugin_*" / "workflows" / "__previews__" / "*_preview.py"),
        str(project_root / "titan_cli" / "workflows" / "__previews__" / "*_preview.py")
    ]

    preview_files = []
    for pattern in search_patterns:
        preview_files.extend(glob.glob(pattern))

    previews = {}
    for file_path_str in preview_files:
        p = Path(file_path_str)
        try:
            relative_p = p.relative_to(project_root)
            preview_name = p.name.replace("_preview.py", "").replace("_", "-")
            module_path = str(relative_p.with_suffix('')).replace('/', '.')
            previews[preview_name] = module_path
        except ValueError:
            # This can happen if the file is not within the project root, which is unexpected
            # for previews. We'll just ignore such files.
            pass

    if name in previews:
        try:
            runpy.run_module(previews[name], run_name="__main__")
        except ModuleNotFoundError:
            typer.secho(f"Error: Preview script for workflow '{name}' could not be loaded as a module.", fg=typer.colors.RED)
            raise typer.Exit(1)
        except Exception as e:
            typer.secho(f"Error executing preview for workflow '{name}': {e}", fg=typer.colors.RED)
            raise typer.Exit(1)
    else:
        typer.secho(f"Error: Preview for workflow '{name}' not found.", fg=typer.colors.RED)
        if previews:
            typer.secho("Available previews:", fg=typer.colors.YELLOW)
            for key in sorted(previews.keys()):
                typer.secho(f"  - {key}", fg=typer.colors.YELLOW)
        else:
            typer.secho("No workflow previews found in expected plugin paths.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
