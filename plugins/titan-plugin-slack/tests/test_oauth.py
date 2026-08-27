from urllib.parse import parse_qs, urlparse

import pytest
import requests

from titan_plugin_slack.oauth import SlackOAuthError, SlackOAuthFlow


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_build_authorize_url_contains_expected_oauth_values() -> None:
    flow = SlackOAuthFlow(client_id="123", redirect_port=8765)
    session = flow.create_session()

    url = flow.build_authorize_url(session)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "slack.com"
    assert parsed.path == "/oauth/v2_user/authorize"
    assert query["client_id"] == ["123"]
    assert query["state"] == [session.state]
    assert query["redirect_uri"] == ["http://127.0.0.1:8765/slack/callback"]
    assert query["scope"] == [
        "users:read,channels:read,channels:history,groups:read,groups:history,im:history,mpim:history,chat:write,im:write,mpim:write,channels:write,groups:write"
    ]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_challenge" in query


def test_exchange_code_returns_token_and_metadata() -> None:
    class FakeRequests:
        @staticmethod
        def post(url, data, timeout):
            return _FakeResponse(
                {
                    "ok": True,
                    "access_token": "xoxe.xoxp-token",
                    "refresh_token": "xoxe-refresh-token",
                    "expires_in": 43200,
                    "token_type": "Bearer",
                    "scope": "users:read,channels:read",
                    "team": {"id": "T123", "name": "Acme"},
                    "user_id": "U123",
                }
            )

    flow = SlackOAuthFlow(client_id="123", redirect_port=8765, requests_module=FakeRequests)

    result = flow.exchange_code("code-123", "verifier-123")

    assert result.access_token == "xoxe.xoxp-token"
    assert result.refresh_token == "xoxe-refresh-token"
    assert result.expires_in == 43200
    assert result.token_type == "Bearer"
    assert result.team_id == "T123"
    assert result.team_name == "Acme"
    assert result.authed_user_id == "U123"
    assert result.granted_scopes == ["users:read", "channels:read"]


def test_exchange_code_falls_back_to_authed_user_access_token() -> None:
    class FakeRequests:
        @staticmethod
        def post(url, data, timeout):
            return _FakeResponse(
                {
                    "ok": True,
                    "scope": "users:read,channels:read",
                    "team": {"id": "T123", "name": "Acme"},
                    "authed_user": {
                        "id": "U123",
                        "access_token": "xoxp-token",
                        "refresh_token": "xoxe-refresh-token",
                        "expires_in": 43200,
                        "token_type": "user",
                    },
                }
            )

    flow = SlackOAuthFlow(client_id="123", redirect_port=8765, requests_module=FakeRequests)

    result = flow.exchange_code("code-123", "verifier-123")

    assert result.access_token == "xoxp-token"
    assert result.refresh_token == "xoxe-refresh-token"
    assert result.expires_in == 43200
    assert result.token_type == "user"
    assert result.authed_user_id == "U123"


def test_exchange_code_raises_when_access_token_is_missing() -> None:
    class FakeRequests:
        @staticmethod
        def post(url, data, timeout):
            return _FakeResponse(
                {
                    "ok": True,
                    "scope": "users:read,channels:read",
                    "team": {"id": "T123", "name": "Acme"},
                    "authed_user": {"id": "U123"},
                }
            )

    flow = SlackOAuthFlow(client_id="123", redirect_port=8765, requests_module=FakeRequests)

    with pytest.raises(SlackOAuthError, match="did not include an access token"):
        flow.exchange_code("code-123", "verifier-123")


def test_refresh_access_token_returns_rotated_credentials() -> None:
    class FakeRequests:
        @staticmethod
        def post(url, data, timeout):
            assert data["grant_type"] == "refresh_token"
            assert data["refresh_token"] == "xoxe-refresh-token"
            return _FakeResponse(
                {
                    "ok": True,
                    "access_token": "xoxe.xoxp-new-token",
                    "refresh_token": "xoxe-new-refresh-token",
                    "expires_in": 43200,
                    "token_type": "Bearer",
                    "scope": "users:read,channels:read",
                    "team": {"id": "T123", "name": "Acme"},
                }
            )

    flow = SlackOAuthFlow(client_id="123", redirect_port=8765, requests_module=FakeRequests)

    result = flow.refresh_access_token("xoxe-refresh-token")

    assert result.access_token == "xoxe.xoxp-new-token"
    assert result.refresh_token == "xoxe-new-refresh-token"
    assert result.expires_in == 43200


def test_exchange_code_raises_on_slack_error() -> None:
    class FakeRequests:
        @staticmethod
        def post(url, data, timeout):
            return _FakeResponse({"ok": False, "error": "invalid_code"})

    flow = SlackOAuthFlow(client_id="123", requests_module=FakeRequests)

    try:
        flow.exchange_code("bad-code", "verifier-123")
    except SlackOAuthError as exc:
        assert "invalid_code" in str(exc)
    else:
        raise AssertionError("Expected SlackOAuthError")
