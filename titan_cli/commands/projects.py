"""
Projects Subcommand Module

This module contains the 'projects' command, which discovers and lists
Titan projects in the configured project root.
"""

import typer
from pathlib import Path

from ..core.config import TitanConfig
from ..core.discovery import discover_projects
from ..ui.components.typography import TextRenderer
from ..ui.components.spacer import SpacerRenderer
from ..ui.components.table import TableRenderer

projects_app = typer.Typer(name="projects", help="Discover and manage Titan projects.")

@projects_app.callback()
def projects_callback():
    """Discover and manage Titan projects."""
    pass # No default action, subcommands will be implemented here


@projects_app.command("list")
def list_projects():
    """
    List discovered Titan projects in the configured project root.
    Categorizes projects as configured (with .titan/config.toml)
    and unconfigured (git repos without .titan/config.toml).
    """
    text = TextRenderer()
    spacer = SpacerRenderer()
    table_renderer = TableRenderer()

    text.title("Project Discovery")
    spacer.line()

    config = TitanConfig()
    project_root = None
    if config.config.core and config.config.core.project_root:
        project_root = Path(config.config.core.project_root)

    if not project_root or (project_root and not project_root.is_dir()):
        text.error("Project root not configured or does not exist.")
        text.info("Please run 'titan init' to set your project root.", show_emoji=False)
        raise typer.Exit(1)

    text.body(f"Scanning for projects in: [primary]{project_root}[/primary]")
    spacer.line()

    configured_projects, unconfigured_projects = discover_projects(str(project_root))

    # Display Configured Projects
    text.success("Configured Projects:")
    if configured_projects:
        headers = ["Project Name", "Path"]
        rows = []
        for p in configured_projects:
            try:
                rel_path = str(p.relative_to(project_root))
            except ValueError:
                rel_path = str(p) # Fallback to absolute path
            rows.append([p.name, rel_path])
        table_renderer.print_table(headers=headers, rows=rows, show_lines=True)
    else:
        text.body("No configured Titan projects found.")
    spacer.line()

    # Display Unconfigured Projects
    text.warning("Unconfigured Git Projects (candidates for 'titan init'):")
    if unconfigured_projects:
        headers = ["Project Name", "Path"]
        rows = []
        for p in unconfigured_projects:
            try:
                rel_path = str(p.relative_to(project_root))
            except ValueError:
                rel_path = str(p) # Fallback to absolute path
            rows.append([p.name, rel_path])
        table_renderer.print_table(headers=headers, rows=rows, show_lines=True)
    else:
        text.body("No unconfigured Git projects found.")
    spacer.line()

    text.info("To initialize an unconfigured project, navigate to its directory and run 'titan init'.")
