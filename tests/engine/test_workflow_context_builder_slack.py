from unittest.mock import MagicMock

from titan_cli.engine.builder import WorkflowContextBuilder


def test_with_slack_loads_client_from_plugin_registry() -> None:
    plugin_registry = MagicMock()
    slack_plugin = MagicMock()
    slack_client = MagicMock()

    plugin_registry.ensure_initialized.return_value = slack_plugin
    slack_plugin.is_available.return_value = True
    slack_plugin.get_client.return_value = slack_client

    ctx = WorkflowContextBuilder(
        plugin_registry=plugin_registry,
        ai_config=None,
    ).with_slack().build()

    assert ctx.slack is slack_client


def test_with_slack_uses_explicit_client() -> None:
    plugin_registry = MagicMock()
    slack_client = MagicMock()

    ctx = WorkflowContextBuilder(
        plugin_registry=plugin_registry,
        ai_config=None,
    ).with_slack(slack_client).build()

    assert ctx.slack is slack_client
