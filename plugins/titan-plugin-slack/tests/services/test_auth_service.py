from unittest.mock import MagicMock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_plugin_slack.clients import sdk as slack_sdk_module
from titan_plugin_slack.clients.services.auth_service import AuthService


def test_auth_service_returns_identity_fields() -> None:
    web_client = MagicMock()
    web_client.auth_test.return_value = {
        "ok": True,
        "user_id": "U123",
        "team_id": "T123",
        "team": "Acme",
        "url": "https://acme.slack.com",
        "bot_id": None,
    }

    service = AuthService(web_client)

    result = service.auth_test()

    assert isinstance(result, ClientSuccess)
    assert result.data.user_id == "U123"
    assert result.data.team_id == "T123"


def test_auth_service_raises_api_error_for_invalid_token(monkeypatch) -> None:
    class FakeSlackApiError(Exception):
        def __init__(self, message: str, response=None):
            super().__init__(message)
            self.response = response

    monkeypatch.setattr(slack_sdk_module, "SlackApiError", FakeSlackApiError)
    monkeypatch.setattr(
        "titan_plugin_slack.clients.services.auth_service.SlackApiError",
        FakeSlackApiError,
    )

    web_client = MagicMock()
    web_client.auth_test.side_effect = FakeSlackApiError(
        "invalid auth",
        response={"error": "invalid_auth"},
    )

    service = AuthService(web_client)

    result = service.auth_test()

    assert isinstance(result, ClientError)
    assert result.error_message == "Slack auth failed: invalid_auth"


def test_auth_service_raises_client_error_for_transport_failure() -> None:
    web_client = MagicMock()
    web_client.auth_test.side_effect = RuntimeError("network down")

    service = AuthService(web_client)

    result = service.auth_test()

    assert isinstance(result, ClientError)
    assert result.error_message == "Slack auth request failed: network down"
