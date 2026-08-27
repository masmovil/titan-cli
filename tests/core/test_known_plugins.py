from titan_cli.core.plugins.available import KNOWN_PLUGINS


def test_known_plugins_includes_slack() -> None:
    slack_plugin = next((plugin for plugin in KNOWN_PLUGINS if plugin["name"] == "slack"), None)

    assert slack_plugin is not None
    assert slack_plugin["package_name"] == "titan-plugin-slack"
    assert slack_plugin["dependencies"] == []
