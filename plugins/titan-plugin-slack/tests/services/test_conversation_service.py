from unittest.mock import MagicMock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_plugin_slack.clients.services.conversation_service import ConversationService


def test_read_conversation_maps_messages_and_pagination() -> None:
    web_client = MagicMock()
    web_client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {
                "ts": "123.456",
                "text": "Hello",
                "user": "U123",
                "thread_ts": "123.456",
                "reply_count": 2,
                "subtype": None,
            },
            {
                "ts": "123.789",
                "text": "World",
                "user": "U456",
                "reply_count": 0,
            },
        ],
        "has_more": True,
        "response_metadata": {"next_cursor": "cursor-789"},
    }

    service = ConversationService(web_client)

    result = service.read_conversation("C123", limit=10)

    assert isinstance(result, ClientSuccess)
    messages, next_cursor, has_more = result.data
    assert next_cursor == "cursor-789"
    assert has_more is True
    assert len(messages) == 2
    assert messages[0].ts == "123.456"
    assert messages[0].thread_ts == "123.456"
    assert messages[0].reply_count == 2
    assert messages[1].text == "World"


def test_read_conversation_raises_api_error() -> None:
    web_client = MagicMock()
    web_client.conversations_history.return_value = {
        "ok": False,
        "error": "channel_not_found",
    }

    service = ConversationService(web_client)

    result = service.read_conversation("C404")

    assert isinstance(result, ClientError)
    assert result.error_message == "Slack read_channel failed: channel_not_found"


def test_open_direct_message_returns_conversation() -> None:
    web_client = MagicMock()
    web_client.conversations_open.return_value = {
        "ok": True,
        "channel": {
            "id": "D123",
            "is_im": True,
            "user": "U123",
            "context_team_id": "T123",
        },
    }

    service = ConversationService(web_client)

    result = service.open_direct_message("U123")

    assert isinstance(result, ClientSuccess)
    assert result.data.id == "D123"
    assert result.data.user_id == "U123"
    assert result.data.team_id == "T123"


def test_open_direct_message_returns_client_error() -> None:
    web_client = MagicMock()
    web_client.conversations_open.return_value = {"ok": False, "error": "missing_scope"}

    service = ConversationService(web_client)

    result = service.open_direct_message("U123")

    assert isinstance(result, ClientError)
    assert result.error_message == "Slack open_direct_message failed: missing_scope"
