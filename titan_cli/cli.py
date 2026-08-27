"""Titan CLI entrypoint.

This module intentionally stays small: it wires the public Typer application,
keeps backwards-compatible imports for tests and packaging, and delegates
feature command trees to command adapters.
"""

import os
import sys

import typer

from titan_cli import __version__
from titan_cli.commands.headless.app import build_app as build_headless_app
from titan_cli.commands.ui import build_app as build_ui_app
from titan_cli.core.config import TitanConfig
from titan_cli.core.logging import get_logger, setup_logging
from titan_cli.messages import msg
from titan_cli.runtime.container import TitanRuntimeContainer
from titan_cli.ui.tui import launch_tui
from titan_cli.utils.autoupdate import (
    check_for_updates,
    get_installed_version,
    meets_target_version,
    update_core,
    update_plugins,
)
from titan_cli.core.services.project_inspection_service import (
    ProjectInspectionService,
)
from titan_cli.core.services.ai_connection_service import AIConnectionService
from titan_cli.core.services.plugin_service import PluginService
from titan_cli.engine.runs.service import WorkflowRunService


app = typer.Typer(
    name=msg.CLI.APP_NAME,
    help=msg.CLI.APP_DESCRIPTION,
    invoke_without_command=True,
    no_args_is_help=False,
)

_HEADLESS_LOGGING_INITIALIZED = False


def get_version() -> str:
    """Retrieve the package version."""
    return __version__


def _workflow_run_service() -> WorkflowRunService:
    """Build the workflow run service used by headless CLI commands.

    Kept as a module-level function so existing tests and integrations can
    monkeypatch the service without reaching into the command modules.
    """
    return WorkflowRunService(config=TitanConfig())


def _project_inspection_service() -> ProjectInspectionService:
    """Build the project inspection service used by headless CLI commands."""
    return ProjectInspectionService(config=TitanConfig())


def _ai_config() -> TitanConfig:
    """Build a lightweight config object for headless AI settings."""
    return TitanConfig(skip_plugin_init=True)


def _plugin_service() -> PluginService:
    """Build the plugin service used by headless CLI commands."""
    return PluginService(config=TitanConfig())


def _ensure_headless_logging(verbose: bool, debug: bool) -> None:
    """Initialize Titan logging for headless mode without using stdout."""
    global _HEADLESS_LOGGING_INITIALIZED
    if _HEADLESS_LOGGING_INITIALIZED:
        return

    setup_logging(verbose=verbose, debug=debug, console_enabled=False)
    _HEADLESS_LOGGING_INITIALIZED = True


class _CLIContainer(TitanRuntimeContainer):
    """Container adapter that preserves the historical cli.py patch points."""

    def workflow_run_service(self) -> WorkflowRunService:
        return _workflow_run_service()

    def project_inspection_service(self) -> ProjectInspectionService:
        return _project_inspection_service()

    def ai_config(self) -> TitanConfig:
        return _ai_config()

    def ai_connection_service(self) -> AIConnectionService:
        return AIConnectionService(config=_ai_config())

    def plugin_service(self) -> PluginService:
        return _plugin_service()


app.add_typer(build_headless_app(_CLIContainer()), name="headless")
app.add_typer(build_ui_app(_CLIContainer()), name="ui")


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output (INFO level logs)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode (DEBUG level logs with detailed output)",
    ),
    devtools: bool = typer.Option(
        False,
        "--devtools",
        help=(
            "Enable Textual devtools (visual debugging for TUI, requires "
            "'textual console' in another terminal)"
        ),
    ),
):
    """Titan CLI - Main entry point."""
    if os.getenv("TITAN_ENV") == "development":
        debug = True

    # Headless commands are consumed by native clients. They must keep stdout
    # clean so responses remain parseable JSON.
    if ctx.invoked_subcommand == "headless":
        _ensure_headless_logging(verbose=verbose, debug=debug)
        ctx.ensure_object(dict)
        ctx.obj["devtools"] = devtools
        return

    setup_logging(verbose=verbose, debug=debug)
    logger = get_logger("titan.cli")

    ctx.ensure_object(dict)
    ctx.obj["devtools"] = devtools

    logger.debug(
        "cli_invoked",
        command=ctx.invoked_subcommand,
        verbose=verbose,
        debug=debug,
        devtools=devtools,
    )

    if ctx.invoked_subcommand is None:
        _launch_with_update_check(logger, debug=debug, devtools=devtools)


def _launch_with_update_check(logger, *, debug: bool, devtools: bool) -> None:
    """Check updates before launching the interactive TUI."""
    try:
        logger.debug("checking_for_updates")
        update_info = check_for_updates()
        if update_info["update_available"]:
            current = update_info["current_version"]
            latest = update_info["latest_version"]

            logger.info("update_available", current=current, latest=latest)

            typer.echo(f"🔔 Update available: v{current} → v{latest}")
            typer.echo()

            if typer.confirm("Would you like to update now?", default=True):
                _run_update_flow(logger, latest=latest)
            else:
                logger.info("update_skipped")
                typer.echo()
                typer.echo("   Please update manually:")
                typer.echo("     pipx upgrade --force titan-cli")
                typer.echo("     pipx upgrade --include-injected titan-cli")
                sys.exit(1)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        logger.warning("update_check_failed", error=str(exc))

    launch_tui(debug=debug, devtools=devtools)


def _run_update_flow(logger, *, latest: str) -> None:
    """Update Titan and plugins, then ask the user to restart."""
    logger.info("update_initiated")

    typer.echo("⏳ Updating Titan CLI...")
    core_result = update_core(target_version=latest)

    if not core_result["success"]:
        logger.error("update_core_failed", error=core_result["error"])
        typer.echo(f"❌ Failed to update Titan CLI: {core_result['error']}")
        typer.echo()
        typer.echo("   Please update manually:")
        typer.echo("     pipx upgrade --force titan-cli")
        typer.echo("     pipx upgrade --include-injected titan-cli")
        sys.exit(1)

    installed_version = core_result.get("installed_version", latest)
    logger.info(
        "update_core_successful",
        version=installed_version,
        method=core_result["method"],
    )
    typer.echo(f"✅ Titan CLI updated to v{installed_version}")

    typer.echo("⏳ Updating plugins...")
    plugins_result = update_plugins()

    if not plugins_result["success"]:
        logger.error("update_plugins_failed", error=plugins_result["error"])
        typer.echo(f"❌ Failed to update plugins: {plugins_result['error']}")
        typer.echo()
        typer.echo("   Please run manually:")
        typer.echo("     pipx upgrade --include-injected titan-cli")
        sys.exit(1)

    if not plugins_result.get("skipped"):
        typer.echo("✅ Plugins updated")

    final_version = get_installed_version()
    if not final_version or not meets_target_version(final_version, latest):
        logger.error(
            "update_final_version_check_failed",
            expected=latest,
            installed=final_version,
        )
        typer.echo(
            "❌ Failed to verify Titan CLI after plugin update: "
            f"installed version is {final_version or 'unknown'}, "
            f"expected at least {latest}"
        )
        typer.echo()
        typer.echo("   Please update manually:")
        typer.echo("     pipx upgrade --force titan-cli")
        typer.echo("     pipx upgrade --include-injected titan-cli")
        sys.exit(1)

    logger.info("update_successful", version=final_version)
    typer.echo()
    typer.echo(
        "✅ Update complete. Please run `titan` again to use "
        f"v{final_version}."
    )
    sys.exit(0)


@app.command()
def version():
    """Show Titan CLI version."""
    cli_version = get_version()
    typer.echo(msg.CLI.VERSION.format(version=cli_version))


@app.command()
def tui(ctx: typer.Context):
    """Launch Titan in TUI mode (Textual interface)."""
    debug = ctx.parent.params.get("debug", False) if ctx.parent else False
    devtools = (
        ctx.parent.obj.get("devtools", False)
        if ctx.parent and ctx.parent.obj
        else False
    )
    launch_tui(debug=debug, devtools=devtools)
