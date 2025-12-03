import typer
from titan_cli.core.config import TitanConfig
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.panel import PanelRenderer
from titan_cli.ui.components.table import TableRenderer
from titan_cli.ui.console import get_console
from titan_cli.messages import msg

plugins_app = typer.Typer(name="plugins", help="Manage Titan plugins")


@plugins_app.command("list")
def list_plugins():
    """List installed plugins and their configuration."""
    text = TextRenderer()
    panel = PanelRenderer()
    table_renderer = TableRenderer()

    config = TitanConfig()

    text.title(msg.Plugins.INSTALLED_TITLE)

    headers = [
        msg.Plugins.TABLE_HEADER_PLUGIN,
        msg.Plugins.TABLE_HEADER_ENABLED,
        msg.Plugins.TABLE_HEADER_CONFIGURATION
    ]
    rows = []

    installed_plugins = config.registry.list_installed()
    if installed_plugins:
        for plugin_name in installed_plugins:
            plugin = config.registry.get_plugin(plugin_name)
            if plugin:
                plugin_config = config.config.plugins.get(plugin_name)
                enabled = plugin_config.enabled if plugin_config else True
                config_dict = plugin_config.config if plugin_config else {}
                config_str = "\n".join([f"{k}: {v}" for k, v in config_dict.items()]) if config_dict else msg.Plugins.NO_CONFIG
                rows.append([plugin_name, "✓" if enabled else "✗", config_str])
        table_renderer.print_table(headers=headers, rows=rows)
    else:
        text.body("No plugins installed or loaded.")

    failed = config.registry.list_failed()
    if failed:
        text.line()
        text.warning(msg.Plugins.LOAD_FAILURE_SUMMARY.format(count=len(failed)))
        text.line()

        for plugin_name, error in failed.items():
            error_message = str(error.original_exception) if hasattr(error, 'original_exception') else str(error)
            panel.print(
                msg.Plugins.LOAD_FAILURE_DETAIL.format(plugin_name=plugin_name, error_message=error_message),
                panel_type="warning",
                title=msg.Plugins.LOAD_FAILURE_PANEL_TITLE.format(plugin_name=plugin_name)
            )

@plugins_app.command("doctor")
def doctor():
    """Check plugin health and show warnings."""
    text = TextRenderer()
    panel = PanelRenderer()

    text.title(msg.Plugins.DOCTOR_TITLE)
    text.line()

    config = TitanConfig()

    all_healthy = True

    for plugin_name in config.registry.list_installed():
        plugin = config.registry.get_plugin(plugin_name)
        text.body(msg.Plugins.DOCTOR_CHECKING.format(plugin_name=plugin_name))

        if not plugin or not plugin.is_available():
            all_healthy = False
            panel.print(
                msg.Plugins.DOCTOR_UNAVAILABLE.format(plugin_name=plugin_name),
                panel_type="warning",
                title=msg.Plugins.DOCTOR_UNAVAILABLE_TITLE.format(plugin_name=plugin_name)
            )
        else:
            text.success(msg.Plugins.DOCTOR_HEALTHY.format(plugin_name=plugin_name))

        text.line()

    failed = config.registry.list_failed()
    if failed:
        all_healthy = False
        text.error(msg.Plugins.DOCTOR_LOAD_FAILURE_SUMMARY.format(count=len(failed)))
        text.line()

        for plugin_name, error in failed.items():
            error_message = str(error.original_exception) if hasattr(error, 'original_exception') else str(error)
            panel.print(
                msg.Plugins.DOCTOR_LOAD_FAILURE_DETAIL.format(error_message=error_message),
                panel_type="error",
                title=msg.Plugins.DOCTOR_LOAD_FAILURE_PANEL_TITLE.format(plugin_name=plugin_name)
            )

    text.line()
    if all_healthy:
        text.success(msg.Plugins.DOCTOR_ALL_HEALTHY)
    else:
        text.warning(msg.Plugins.DOCTOR_ISSUES_FOUND)
        raise typer.Exit(code=1)

@plugins_app.command("info")
def plugin_info(name: str):
    """Show detailed information about a plugin."""
    text = TextRenderer()
    config = TitanConfig()

    plugin = config.registry.get_plugin(name)
    if not plugin:
        text.error(msg.Plugins.PLUGIN_NOT_FOUND.format(name=name))
        raise typer.Exit(1)

    text.styled_text((msg.Plugins.PLUGIN_INFO_TITLE.split(':')[0] + ': ', "bold cyan"), (plugin.name, "default"))
    text.styled_text((msg.Plugins.PLUGIN_INFO_VERSION.split(':')[0] + ': ', "dim"), (plugin.version, "dim"))
    text.body(plugin.description)
    text.line()
    text.body(f"Available: {'✓' if plugin.is_available() else '✗'}")
    text.body(f"Dependencies: {', '.join(plugin.dependencies) or 'None'}")

    if hasattr(plugin, 'get_config_schema'):
        text.line()
        text.subtitle("Configuration Schema")
        schema = plugin.get_config_schema()

        for prop_name, prop_schema in schema.get("properties", {}).items():
            default = prop_schema.get("default", "N/A")
            desc = prop_schema.get("description", "")
            text.styled_text(("  • ", "default"), (prop_name, "bold"), (f": {desc}", "default"))
            text.body(f"    Default: {default}", style="dim")

    steps = plugin.get_steps()
    if steps:
        text.line()
        text.subtitle(f"Available Steps ({len(steps)})")
        for step_name in steps.keys():
            text.body(f"  • {step_name}")

@plugins_app.command("configure")
def configure_plugin(name: str):
    """Configure a plugin interactively."""
    text = TextRenderer()
    config = TitanConfig()

    plugin = config.registry.get_plugin(name)
    if not plugin:
        text.error(msg.Plugins.PLUGIN_NOT_FOUND.format(name=name))
        raise typer.Exit(1)

    text.title(msg.Plugins.CONFIGURE_TITLE.format(name=name))
    text.body(msg.Plugins.CONFIGURE_SOON)