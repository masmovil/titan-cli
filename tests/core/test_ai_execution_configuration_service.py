"""Typed application service for persisted AI execution configuration."""

import pytest

from titan_cli.core.services.ai_execution_configuration_service import (
    AIExecutionConfigurationService,
)


class StubConfig:
    def __init__(self) -> None:
        self.ai = {"default_cli": "codex"}
        self.preferences = {
            "tasks": {"code_review_findings": {"provider": "cli_headless"}}
        }

    def get_ai_connections_config(self):
        return self.ai

    def get_ai_preferences_config(self):
        return self.preferences

    def set_default_ai_cli(self, cli_id):
        self.ai["default_cli"] = cli_id

    def clear_default_ai_cli(self):
        self.ai.pop("default_cli", None)

    def upsert_task_ai_preference(self, task_id, preference):
        self.preferences["tasks"][task_id] = preference

    def delete_task_ai_preference(self, task_id):
        self.preferences["tasks"].pop(task_id, None)


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(
        "titan_cli.core.services.ai_execution_configuration_service.CLI_REGISTRY",
        {
            "claude": {"display_name": "Claude CLI"},
            "codex": {"display_name": "Codex CLI"},
        },
    )
    monkeypatch.setattr(
        "titan_cli.core.services.ai_execution_configuration_service.HEADLESS_ADAPTER_REGISTRY",
        {"claude": object()},
    )
    monkeypatch.setattr(
        "titan_cli.core.services.ai_execution_configuration_service.resolve_cli_executable",
        lambda cli_id: f"/usr/local/bin/{cli_id}" if cli_id == "claude" else None,
    )
    return AIExecutionConfigurationService(StubConfig())


def test_configuration_exposes_canonical_cli_and_task_preferences(service):
    payload = service.get_configuration()

    assert payload["default_cli"] == "codex"
    assert payload["task_preferences"] == [
        {"task_id": "code_review_findings", "provider": "cli_headless"}
    ]
    assert payload["clis"] == [
        {
            "id": "claude",
            "name": "Claude CLI",
            "command": "claude",
            "is_installed": True,
            "supports_headless": True,
            "supports_interactive": True,
        },
        {
            "id": "codex",
            "name": "Codex CLI",
            "command": "codex",
            "is_installed": False,
            "supports_headless": False,
            "supports_interactive": True,
        },
    ]
    assert payload["provider_types"] == [
        "remote",
        "cli_headless",
        "cli_interactive",
        "off",
    ]


def test_mutations_return_the_reloaded_canonical_snapshot(service):
    payload = service.set_default_cli("claude")
    assert payload["default_cli"] == "claude"

    payload = service.set_task_provider("commit_message", "off")
    assert {item["task_id"]: item["provider"] for item in payload["task_preferences"]} == {
        "code_review_findings": "cli_headless",
        "commit_message": "off",
    }

    payload = service.clear_task_provider("commit_message")
    assert [item["task_id"] for item in payload["task_preferences"]] == [
        "code_review_findings"
    ]

    payload = service.clear_default_cli()
    assert payload["default_cli"] is None


def test_mutations_reject_unknown_values(service):
    with pytest.raises(ValueError, match="Unknown AI CLI"):
        service.set_default_cli("unknown")

    with pytest.raises(ValueError, match="Unknown AI provider type"):
        service.set_task_provider("commit_message", "magic")

    with pytest.raises(ValueError, match="cannot be empty"):
        service.set_task_provider(" ", "off")
