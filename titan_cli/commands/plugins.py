import typer
from titan_cli.core.config import TitanConfig
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.components.panel import PanelRenderer
from titan_cli.ui.components.table import TableRenderer
from titan_cli.messages import msg

plugins_app = typer.Typer(name="plugins", help="Manage Titan plugins")


@plugins_app.command("list")
def list_plugins():
    """List installed plugins and their status."""
    text = TextRenderer()
    panel = PanelRenderer()
    table_renderer = TableRenderer()

    config = TitanConfig()

    text.title(msg.Plugins.INSTALLED_TITLE)

    headers = [
        msg.Plugins.TABLE_HEADER_PLUGIN,
        msg.Plugins.TABLE_HEADER_VERSION,
        msg.Plugins.TABLE_HEADER_STATUS
    ]
    rows = []

    for plugin_name in config.registry.list_installed():
        plugin = config.registry.get_plugin(plugin_name)
        if plugin:
            status_text = f"{msg.SYMBOL.SUCCESS} {msg.Plugins.STATUS_AVAILABLE}" if plugin.is_available() else f"{msg.SYMBOL.ERROR} {msg.Plugins.STATUS_UNAVAILABLE}"
            rows.append([plugin_name, plugin.version, status_text])

    table_renderer.print_table(headers=headers, rows=rows)

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