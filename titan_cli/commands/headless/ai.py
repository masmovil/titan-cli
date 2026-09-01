"""Headless AI configuration commands."""

import os

import typer

from titan_cli.commands.headless.common import (
    fail_headless_command,
    parse_json_object,
    run_headless_operation,
)
from titan_cli.runtime.container import TitanRuntimeContainer
from titan_cli.runtime.output import output_presenter
from titan_cli.external_cli.interactive_session import run_interactive_session


def build_app(container: TitanRuntimeContainer) -> typer.Typer:
    """Build AI headless commands."""
    app = typer.Typer(name="ai", help="Inspect and configure Titan AI connections.")

    @app.command("session")
    def interactive_session(
        ai_cli_id: str = typer.Option(
            ...,
            "--ai-cli-id",
            help="Registered AI CLI command to launch in an interactive PTY session.",
        ),
        project_path: str | None = typer.Option(
            None,
            "--project-path",
            help="Working directory for the interactive CLI.",
        ),
    ):
        """Bridge an interactive AI CLI using JSON Lines over stdin/stdout."""
        try:
            result = run_interactive_session(ai_cli_id, cwd=project_path)
            if result.exit_code != 0:
                raise RuntimeError(f"Interactive CLI exited with code {result.exit_code}")
        except Exception as exc:
            fail_headless_command(exc, as_json=False)

    @app.command("list")
    def list_ai_connections(
        output_json: bool = typer.Option(
            False,
            "--json",
            help="Print a machine-readable JSON response.",
        ),
    ):
        """List configured AI connections without launching the TUI."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_connection_service().list_connections()
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("upsert")
    def upsert_ai_connection(
        connection_id: str = typer.Argument(..., help="Stable AI connection ID."),
        connection_json: str = typer.Option(
            ...,
            "--connection-json",
            help="JSON object with AI connection settings.",
        ),
        api_key: str | None = typer.Option(
            None,
            "--api-key",
            help="Optional API key stored in Titan's user secret store.",
        ),
        api_key_env: str | None = typer.Option(
            None,
            "--api-key-env",
            help="Optional environment variable containing the API key to store.",
        ),
        output_json: bool = typer.Option(
            False,
            "--json",
            help="Print a machine-readable JSON response.",
        ),
    ):
        """Create or update an AI connection for native clients."""
        try:
            connection_data = parse_json_object(connection_json, "--connection-json")
            secret_value = api_key
            if not secret_value and api_key_env:
                secret_value = os.getenv(api_key_env)

            payload = run_headless_operation(
                lambda: container.ai_connection_service().upsert_connection(
                    connection_id,
                    connection_data,
                    api_key=secret_value,
                )
            )
            output_presenter(output_json).write(payload)
        except typer.BadParameter:
            raise
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("set-default")
    def set_default_ai_connection(
        connection_id: str = typer.Argument(
            ...,
            help="AI connection ID to use by default.",
        ),
        output_json: bool = typer.Option(
            False,
            "--json",
            help="Print a machine-readable JSON response.",
        ),
    ):
        """Set the default AI connection used by Titan workflows."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_connection_service().set_default_connection(
                    connection_id
                )
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("models")
    def list_ai_models(
        connection_id: str = typer.Argument(..., help="AI connection ID."),
        output_json: bool = typer.Option(
            False,
            "--json",
            help="Print a machine-readable JSON response.",
        ),
    ):
        """List available models for a configured AI connection."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_connection_service().list_models(connection_id)
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("execution")
    def get_ai_execution_configuration(
        output_json: bool = typer.Option(
            False,
            "--json",
            help="Print a machine-readable JSON response.",
        ),
    ):
        """Read the persisted CLI default and per-task provider routing."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_execution_configuration_service().get_configuration()
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("set-default-cli")
    def set_default_ai_cli(
        cli_id: str = typer.Argument(..., help="Registered AI CLI ID."),
        output_json: bool = typer.Option(False, "--json"),
    ):
        """Persist the CLI used by all CLI-routed tasks."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_execution_configuration_service().set_default_cli(
                    cli_id
                )
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("clear-default-cli")
    def clear_default_ai_cli(
        output_json: bool = typer.Option(False, "--json"),
    ):
        """Remove the persisted default CLI."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_execution_configuration_service().clear_default_cli()
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("set-task-provider")
    def set_ai_task_provider(
        task_id: str = typer.Argument(..., help="Stable AI task ID."),
        provider: str = typer.Argument(..., help="AI provider type."),
        output_json: bool = typer.Option(False, "--json"),
    ):
        """Persist the provider kind used by one AI task."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_execution_configuration_service().set_task_provider(
                    task_id,
                    provider,
                )
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    @app.command("clear-task-provider")
    def clear_ai_task_provider(
        task_id: str = typer.Argument(..., help="Stable AI task ID."),
        output_json: bool = typer.Option(False, "--json"),
    ):
        """Restore one AI task to its workflow policy default."""
        try:
            payload = run_headless_operation(
                lambda: container.ai_execution_configuration_service().clear_task_provider(
                    task_id
                )
            )
            output_presenter(output_json).write(payload)
        except Exception as exc:
            fail_headless_command(exc, as_json=output_json)

    return app
