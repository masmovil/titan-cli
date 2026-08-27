from unittest.mock import MagicMock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_plugin_slack.clients.services.directory_service import DirectoryService
from titan_plugin_slack.models import UISlackChannel, UISlackUser


def test_list_users_maps_members_and_cursor() -> None:
    web_client = MagicMock()
    web_client.users_list.return_value = {
        "ok": True,
        "members": [
            {
                "id": "U123",
                "name": "alex",
                "real_name": "Alex",
                "is_bot": False,
                "deleted": False,
            },
            {
                "id": "U456",
                "name": "bot-user",
                "profile": {"real_name": "Bot User"},
                "is_bot": True,
                "deleted": True,
            },
        ],
        "response_metadata": {"next_cursor": "cursor-123"},
    }

    service = DirectoryService(web_client)

    result = service.list_users(limit=50)

    assert isinstance(result, ClientSuccess)
    users, next_cursor = result.data
    assert next_cursor == "cursor-123"
    assert len(users) == 2
    assert users[0].id == "U123"
    assert users[0].real_name == "Alex"
    assert users[0].is_active is True
    assert users[1].is_bot is True
    assert users[1].real_name == "Bot User"
    assert users[1].is_active is False


def test_list_users_raises_api_error() -> None:
    web_client = MagicMock()
    web_client.users_list.return_value = {"ok": False, "error": "missing_scope"}

    service = DirectoryService(web_client)

    result = service.list_users()

    assert isinstance(result, ClientError)
    assert result.error_message == "Slack list_users failed: missing_scope"


def test_list_public_channels_maps_channels_and_cursor() -> None:
    web_client = MagicMock()
    web_client.conversations_list.return_value = {
        "ok": True,
        "channels": [
            {"id": "C123", "name": "general", "is_channel": True, "is_private": False},
            {"id": "C456", "name": "announcements", "is_channel": True, "is_private": False},
        ],
        "response_metadata": {"next_cursor": "cursor-456"},
    }

    service = DirectoryService(web_client)

    result = service.list_public_channels(limit=25)

    assert isinstance(result, ClientSuccess)
    channels, next_cursor = result.data
    assert next_cursor == "cursor-456"
    assert len(channels) == 2
    assert channels[0].id == "C123"
    assert channels[0].name == "general"
    assert channels[1].is_private is False


def test_list_public_channels_raises_api_error() -> None:
    web_client = MagicMock()
    web_client.conversations_list.return_value = {
        "ok": False,
        "error": "missing_scope",
    }

    service = DirectoryService(web_client)

    result = service.list_public_channels()

    assert isinstance(result, ClientError)
    assert result.error_message == "Slack list_public_channels failed: missing_scope"


def test_search_users_scans_multiple_pages_until_match() -> None:
    web_client = MagicMock()
    service = DirectoryService(web_client)
    service.list_users = MagicMock(
        side_effect=[
            ClientSuccess(
                data=([
                    UISlackUser(id="U1", name="sam", real_name="Sam One"),
                ], "cursor-1")
            ),
            ClientSuccess(
                data=([
                    UISlackUser(id="U2", name="alex", real_name="Alex Smith"),
                ], None)
            ),
        ]
    )

    result = service.search_users("alex", max_matches=10, page_size=100, max_pages=5)

    assert isinstance(result, ClientSuccess)
    matches = result.data
    assert [user.id for user in matches] == ["U2"]


def test_search_public_channels_scans_multiple_pages_until_match() -> None:
    web_client = MagicMock()
    service = DirectoryService(web_client)
    service.list_public_channels = MagicMock(
        side_effect=[
            ClientSuccess(
                data=([
                    UISlackChannel(id="C1", name="general"),
                ], "cursor-1")
            ),
            ClientSuccess(
                data=([
                    UISlackChannel(id="C2", name="eng-backend"),
                ], None)
            ),
        ]
    )

    result = service.search_public_channels("eng", max_matches=10, page_size=100, max_pages=5)

    assert isinstance(result, ClientSuccess)
    matches = result.data
    assert [channel.id for channel in matches] == ["C2"]


def test_search_users_reuses_cached_pages_across_searches() -> None:
    web_client = MagicMock()
    service = DirectoryService(web_client)
    service.list_users = MagicMock(
        side_effect=[
            ClientSuccess(
                data=([UISlackUser(id="U1", name="sam", real_name="Sam One")], "cursor-1")
            ),
            ClientSuccess(
                data=([UISlackUser(id="U2", name="alex", real_name="Alex Smith")], None)
            ),
        ]
    )

    first = service.search_users("alex", max_matches=10, page_size=100, max_pages=5)
    assert [user.id for user in first.data] == ["U2"]
    assert service.list_users.call_count == 2

    second = service.search_users("sam", max_matches=10, page_size=100, max_pages=5)

    assert isinstance(second, ClientSuccess)
    assert [user.id for user in second.data] == ["U1"]
    assert service.list_users.call_count == 2, "second search must not re-scan already fetched pages"


def test_search_channels_reuses_cached_pages_across_searches() -> None:
    web_client = MagicMock()
    web_client.conversations_list.side_effect = [
        {
            "ok": True,
            "channels": [{"id": "C1", "name": "general"}],
            "response_metadata": {"next_cursor": "cursor-1"},
        },
        {
            "ok": True,
            "channels": [{"id": "C2", "name": "eng-backend"}],
            "response_metadata": {"next_cursor": None},
        },
    ]
    service = DirectoryService(web_client)

    first = service.search_channels("eng", max_matches=10, page_size=100, max_pages=5)
    assert [channel.id for channel in first.data] == ["C2"]
    assert web_client.conversations_list.call_count == 2

    second = service.search_channels("general", max_matches=10, page_size=100, max_pages=5)

    assert isinstance(second, ClientSuccess)
    assert [channel.id for channel in second.data] == ["C1"]
    assert web_client.conversations_list.call_count == 2, (
        "second search must not re-scan already fetched pages"
    )


def test_search_users_refreshes_cache_after_ttl_expires() -> None:
    web_client = MagicMock()
    service = DirectoryService(web_client, cache_ttl_seconds=0)
    service.list_users = MagicMock(
        side_effect=[
            ClientSuccess(data=([UISlackUser(id="U1", name="sam", real_name="Sam One")], None)),
            ClientSuccess(data=([UISlackUser(id="U1", name="sam", real_name="Sam One")], None)),
        ]
    )

    service.search_users("sam", max_matches=10, page_size=100, max_pages=5)
    service.search_users("sam", max_matches=10, page_size=100, max_pages=5)

    assert service.list_users.call_count == 2, "an expired cache must trigger a fresh scan"


def test_search_users_returns_error_without_caching_partial_results() -> None:
    web_client = MagicMock()
    service = DirectoryService(web_client)
    service.list_users = MagicMock(
        return_value=ClientError(error_message="Slack list_users failed: ratelimited")
    )

    result = service.search_users("alex", max_matches=10, page_size=100, max_pages=5)

    assert isinstance(result, ClientError)
