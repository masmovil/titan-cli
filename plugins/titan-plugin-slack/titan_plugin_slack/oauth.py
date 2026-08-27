"""Slack OAuth backend helpers for the Slack configuration flow."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event, Thread
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse
import secrets as secrets_module
import webbrowser

import requests

from titan_cli.core.logging import get_logger


AUTHORIZE_URL = "https://slack.com/oauth/v2_user/authorize"
TOKEN_URL = "https://slack.com/api/oauth.v2.user.access"
DEFAULT_SCOPES = [
    "users:read",
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:history",
    "mpim:history",
    "chat:write",
    "im:write",
    "mpim:write",
    "channels:write",
    "groups:write",
]

logger = get_logger(__name__)


CALLBACK_SUCCESS_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Titan Slack Connection</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f7fb;
        --panel: #ffffff;
        --border: #d8deea;
        --text: #182033;
        --muted: #5c667d;
        --accent: #4f46e5;
        --success: #15803d;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
        background: radial-gradient(circle at top, #eef2ff 0%, var(--bg) 55%);
        color: var(--text);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      .card {
        width: min(100%, 520px);
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 32px 28px;
        box-shadow: 0 18px 50px rgba(24, 32, 51, 0.10);
      }

      .eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(79, 70, 229, 0.10);
        color: var(--accent);
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.02em;
      }

      .title {
        margin: 18px 0 10px;
        font-size: 30px;
        line-height: 1.1;
      }

      .body {
        margin: 0;
        font-size: 16px;
        line-height: 1.6;
        color: var(--muted);
      }

      .status {
        margin-top: 22px;
        padding: 14px 16px;
        border-radius: 14px;
        background: rgba(21, 128, 61, 0.08);
        color: var(--success);
        font-weight: 600;
      }
    </style>
  </head>
  <body>
    <main class="card">
      <div class="eyebrow">Titan • Slack</div>
      <h1 class="title">Slack connection received</h1>
      <p class="body">
        Titan has received the OAuth callback successfully. You can now return to the CLI and continue.
      </p>
      <div class="status">You can close this tab.</div>
    </main>
  </body>
</html>
""".encode("utf-8")

CALLBACK_ERROR_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Titan Slack Connection</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f7fb;
        --panel: #ffffff;
        --border: #d8deea;
        --text: #182033;
        --muted: #5c667d;
        --accent: #4f46e5;
        --error: #b91c1c;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
        background: radial-gradient(circle at top, #eef2ff 0%, var(--bg) 55%);
        color: var(--text);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      .card {
        width: min(100%, 520px);
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 32px 28px;
        box-shadow: 0 18px 50px rgba(24, 32, 51, 0.10);
      }

      .eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(79, 70, 229, 0.10);
        color: var(--accent);
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.02em;
      }

      .title {
        margin: 18px 0 10px;
        font-size: 30px;
        line-height: 1.1;
      }

      .body {
        margin: 0;
        font-size: 16px;
        line-height: 1.6;
        color: var(--muted);
      }

      .status {
        margin-top: 22px;
        padding: 14px 16px;
        border-radius: 14px;
        background: rgba(185, 28, 28, 0.08);
        color: var(--error);
        font-weight: 600;
      }
    </style>
  </head>
  <body>
    <main class="card">
      <div class="eyebrow">Titan • Slack</div>
      <h1 class="title">Slack connection failed</h1>
      <p class="body">
        Titan could not complete the Slack OAuth callback. Return to the CLI to see the error details.
      </p>
      <div class="status">You can close this tab.</div>
    </main>
  </body>
</html>
""".encode("utf-8")


class SlackOAuthError(Exception):
    """Raised when the Slack OAuth flow fails."""


@dataclass
class SlackOAuthResult:
    """Successful OAuth exchange result."""

    access_token: str
    refresh_token: str | None
    expires_in: int | None
    token_type: str | None
    granted_scopes: list[str]
    team_id: str | None
    team_name: str | None
    authed_user_id: str | None


@dataclass
class SlackOAuthSession:
    """In-memory OAuth session state for a single PKCE flow."""

    state: str
    code_verifier: str


class SlackOAuthFlow:
    """Backend flow for Slack OAuth-based personal connections."""

    def __init__(
        self,
        client_id: str,
        redirect_port: int = 8765,
        scopes: list[str] | None = None,
        timeout: int = 180,
        browser_opener: Callable[[str], bool] | None = None,
        requests_module=requests,
    ):
        self.client_id = client_id
        self.redirect_port = redirect_port
        self.scopes = scopes or list(DEFAULT_SCOPES)
        self.timeout = timeout
        self.browser_opener = browser_opener or webbrowser.open
        self.requests = requests_module

    @property
    def redirect_uri(self) -> str:
        """Return the localhost redirect URI used for callback handling."""
        return f"http://127.0.0.1:{self.redirect_port}/slack/callback"

    @staticmethod
    def _build_code_challenge(code_verifier: str) -> str:
        """Build a PKCE code challenge from a verifier."""
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def create_session(self) -> SlackOAuthSession:
        """Create a new OAuth session with state and PKCE verifier."""
        return SlackOAuthSession(
            state=secrets_module.token_urlsafe(24),
            code_verifier=secrets_module.token_urlsafe(48),
        )

    def build_authorize_url(self, session: SlackOAuthSession) -> str:
        """Build the Slack OAuth authorize URL."""
        query = urlencode(
            {
                "client_id": self.client_id,
                "scope": ",".join(self.scopes),
                "redirect_uri": self.redirect_uri,
                "state": session.state,
                "code_challenge": self._build_code_challenge(session.code_verifier),
                "code_challenge_method": "S256",
            }
        )
        authorize_url = f"{AUTHORIZE_URL}?{query}"
        logger.info(
            "slack_oauth_authorize_url_built",
            redirect_uri=self.redirect_uri,
            scopes=self.scopes,
        )
        return authorize_url

    def exchange_code(self, code: str, code_verifier: str) -> SlackOAuthResult:
        """Exchange a Slack OAuth code for a user access token."""
        logger.info(
            "slack_oauth_exchange_started",
            redirect_uri=self.redirect_uri,
        )
        response = self.requests.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if not payload.get("ok", False):
            logger.error(
                "slack_oauth_exchange_failed",
                error=payload.get("error", "unknown_error"),
                payload=payload,
            )
            raise SlackOAuthError(
                f"Slack OAuth token exchange failed: {payload.get('error', 'unknown_error')}"
            )

        return self._build_oauth_result(payload)

    def refresh_access_token(self, refresh_token: str) -> SlackOAuthResult:
        """Refresh a Slack PKCE access token."""
        logger.info("slack_oauth_refresh_started", redirect_uri=self.redirect_uri)
        response = self.requests.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if not payload.get("ok", False):
            logger.error(
                "slack_oauth_refresh_failed",
                error=payload.get("error", "unknown_error"),
                payload=payload,
            )
            raise SlackOAuthError(
                f"Slack OAuth refresh failed: {payload.get('error', 'unknown_error')}"
            )

        return self._build_oauth_result(payload)

    @staticmethod
    def _build_oauth_result(payload: dict) -> SlackOAuthResult:
        authed_user = payload.get("authed_user")
        authed_user_data = authed_user if isinstance(authed_user, dict) else None

        access_token = payload.get("access_token") or (
            authed_user_data.get("access_token") if authed_user_data else None
        )
        if not access_token:
            raise SlackOAuthError(
                "Slack OAuth response did not include an access token."
            )

        refresh_token = payload.get("refresh_token") or (
            authed_user_data.get("refresh_token") if authed_user_data else None
        )
        expires_in = payload.get("expires_in")
        if expires_in is None and authed_user_data:
            expires_in = authed_user_data.get("expires_in")
        token_type = payload.get("token_type") or (
            authed_user_data.get("token_type") if authed_user_data else None
        )

        scope_string = payload.get("scope") or (
            authed_user_data.get("scope") if authed_user_data else ""
        )
        granted_scopes = [scope.strip() for scope in scope_string.split(",") if scope.strip()]

        team = payload.get("team") or {}
        logger.info(
            "slack_oauth_exchange_succeeded",
            team_id=team.get("id"),
            team_name=team.get("name"),
            authed_user_id=(authed_user_data.get("id") if authed_user_data else payload.get("user_id")),
            granted_scopes=granted_scopes,
            has_refresh_token=bool(refresh_token),
            expires_in=expires_in,
        )
        return SlackOAuthResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_type=token_type,
            granted_scopes=granted_scopes,
            team_id=team.get("id"),
            team_name=team.get("name"),
            authed_user_id=(authed_user_data.get("id") if authed_user_data else payload.get("user_id")),
        )

    def _start_callback_server(
        self, expected_state: str
    ) -> tuple[HTTPServer, Thread, Event, dict[str, str]]:
        """Bind and start the local OAuth callback listener before the browser opens."""
        callback_event = Event()
        callback_data: dict[str, str] = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # type: ignore[override]
                parsed = urlparse(self.path)
                if parsed.path != "/slack/callback":
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not found")
                    return

                query = parse_qs(parsed.query)
                callback_data["code"] = query.get("code", [""])[0]
                callback_data["state"] = query.get("state", [""])[0]
                callback_data["error"] = query.get("error", [""])[0]
                logger.info(
                    "slack_oauth_callback_received",
                    has_code=bool(callback_data["code"]),
                    has_error=bool(callback_data["error"]),
                )
                callback_succeeded = (
                    not callback_data["error"]
                    and callback_data["state"] == expected_state
                    and bool(callback_data["code"])
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    CALLBACK_SUCCESS_HTML if callback_succeeded else CALLBACK_ERROR_HTML
                )
                callback_event.set()

            def log_message(self, format, *args):  # noqa: A003
                return

        server = HTTPServer(("127.0.0.1", self.redirect_port), CallbackHandler)

        def serve_once() -> None:
            try:
                while not callback_event.is_set():
                    server.handle_request()
            finally:
                server.server_close()

        thread = Thread(target=serve_once, daemon=True)
        thread.start()
        logger.info(
            "slack_oauth_callback_listener_started",
            redirect_uri=self.redirect_uri,
        )
        return server, thread, callback_event, callback_data

    def _wait_for_callback(
        self,
        expected_state: str,
        server: HTTPServer,
        thread: Thread,
        callback_event: Event,
        callback_data: dict[str, str],
    ) -> str:
        """Wait for the already-running local OAuth callback listener to receive the code."""
        logger.info(
            "slack_oauth_callback_wait_started",
            redirect_uri=self.redirect_uri,
            timeout=self.timeout,
        )
        callback_event.wait(self.timeout)
        server.server_close()
        thread.join(timeout=1)

        if not callback_event.is_set():
            logger.error("slack_oauth_callback_timeout", redirect_uri=self.redirect_uri)
            raise SlackOAuthError("Slack OAuth callback timed out.")

        if callback_data.get("error"):
            logger.error(
                "slack_oauth_callback_error",
                error=callback_data["error"],
            )
            raise SlackOAuthError(f"Slack OAuth authorization failed: {callback_data['error']}")

        if callback_data.get("state") != expected_state:
            logger.error("slack_oauth_state_mismatch")
            raise SlackOAuthError("Slack OAuth state mismatch.")

        code = callback_data.get("code")
        if not code:
            logger.error("slack_oauth_callback_missing_code")
            raise SlackOAuthError("Slack OAuth callback did not include an authorization code.")

        return code

    def run(self) -> SlackOAuthResult:
        """Run the complete OAuth flow and return the resulting token data."""
        session = self.create_session()
        authorize_url = self.build_authorize_url(session)

        server, thread, callback_event, callback_data = self._start_callback_server(session.state)

        try:
            browser_started = self.browser_opener(authorize_url)
        except Exception:
            server.server_close()
            logger.error("slack_oauth_browser_open_failed")
            raise

        if browser_started is False:
            server.server_close()
            logger.error("slack_oauth_browser_open_failed")
            raise SlackOAuthError("Failed to open a browser for Slack OAuth.")

        code = self._wait_for_callback(session.state, server, thread, callback_event, callback_data)
        return self.exchange_code(code, session.code_verifier)
