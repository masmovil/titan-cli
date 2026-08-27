from unittest.mock import MagicMock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_plugin_slack.clients.services.message_service import MessageService


def test_post_message_returns_posted_message() -> None:
    web_client = MagicMock()
    web_client.chat_postMessage.return_value = {
        "ok": True,
        "channel": "D123",
        "ts": "123.456",
        "message": {"text": "Hello there", "thread_ts": None},
    }

    service = MessageService(web_client)

    result = service.post_message("D123", "Hello there")

    assert isinstance(result, ClientSuccess)
    assert result.data.channel == "D123"
    assert result.data.ts == "123.456"
    assert result.data.text == "Hello there"


def test_post_message_returns_client_error_on_api_failure() -> None:
    web_client = MagicMock()
    web_client.chat_postMessage.return_value = {"ok": False, "error": "missing_scope"}

    service = MessageService(web_client)

    result = service.post_message("D123", "Hello there")

    assert isinstance(result, ClientError)
    assert result.error_message == "Slack post_message failed: missing_scope"
