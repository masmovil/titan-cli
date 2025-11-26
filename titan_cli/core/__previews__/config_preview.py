"""
Config Component Preview

Run this script to preview the TitanConfig component:
    poetry run python -m titan_cli.core.__previews__.config_preview

This demonstrates how TitanConfig loads, merges, and validates configuration.
"""

from pathlib import Path
import shutil # Import shutil for robust directory removal
from titan_cli.core.config import TitanConfig
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.spacer import SpacerRenderer
from titan_cli.ui.components.table import TableRenderer

def preview_all():
    text = TextRenderer()
    spacer = SpacerRenderer()
    table_renderer = TableRenderer()

    text.title("TitanConfig Preview")
    text.subtitle("Demonstrates loading, merging, and validating configuration.")
    spacer.line()

    text.info("1. Initializing TitanConfig (no project_path)")
    config_instance = TitanConfig()
    text.body(f"Global config path: {TitanConfig.GLOBAL_CONFIG}")
    text.body(f"Project config path: {config_instance.project_config_path}")
    spacer.line()

    text.info("2. Validated Configuration (TitanConfigModel)")
    text.body(f"Project Name: {config_instance.config.project.name if config_instance.config.project else 'N/A'}")
    text.body(f"Project Type: {config_instance.config.project.type if config_instance.config.project else 'N/A'}")
    text.body(f"AI Provider: {config_instance.config.ai.provider if config_instance.config.ai else 'N/A'}")
    text.body(f"Core Project Root: {config_instance.config.core.project_root if config_instance.config.core else 'N/A'}")
    spacer.line()

    text.info("3. Discovered Plugins")
    installed_plugins = config_instance.registry.list_installed()
    if installed_plugins:
        headers = ["Plugin Name"]
        rows = [[p] for p in installed_plugins]
        table_renderer.print_table(headers=headers, rows=rows)
    else:
        text.warning("No plugins discovered via entry points 'titan.plugins'.")
    spacer.line()

    text.info("4. Enabled Plugins from Config")
    enabled_plugins = config_instance.get_enabled_plugins()
    if enabled_plugins:
        headers = ["Enabled Plugin"]
        rows = [[p] for p in enabled_plugins]
        table_renderer.print_table(headers=headers, rows=rows)
    else:
        text.warning("No plugins enabled in configuration.")
    spacer.line()
    
    # Test project config path discovery
    text.info("5. Testing Project Config Discovery (Current Dir)")
    temp_dir = Path("./temp_project_with_titan")
    try:
        # Temporarily create a dummy config file
        temp_dir.mkdir(exist_ok=True)
        temp_titan_dir = temp_dir / ".titan"
        temp_titan_dir.mkdir(exist_ok=True)
        temp_config_path = temp_titan_dir / "config.toml"
        temp_config_path.write_text('[project]\nname = "Temp Project"\ntype = "test"')

        temp_config_instance = TitanConfig(project_path=temp_dir)
        text.body(f"Simulated Project Root: {temp_dir}")
        text.body(f"Discovered Project Config: {temp_config_instance.project_config_path}")
        text.body(f"Project Name from Config: {temp_config_instance.config.project.name}")
    finally:
        # Clean up the temporary directory, ignoring errors if it doesn't exist
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    spacer.line()

    text.success("TitanConfig Preview Complete")

if __name__ == "__main__":
    preview_all()
