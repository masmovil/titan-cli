import asyncio
import errno
import json
import threading
import time

import pytest

import titan_cli.core.oauth.locks as oauth_locks
from titan_cli.core.oauth import (
    CollectingOAuthEventSink,
    OAuthAuthenticationRequired,
    OAuthAuthorizationError,
    OAuthEvent,
    OAuthLockManager,
    OAuthLockTimeout,
    OAuthManager,
    OAuthRequest,
    OAuthStorageError,
    OAuthTokenInvalidError,
    OAuthTokenRefreshError,
    OAuthTokenSet,
    OAuthTokenStore,
    QueuedOAuthEventSink,
    build_oauth_credential_key,
)
from titan_cli.core.secrets import ResolvedSecret


class FakeSecretManager:
    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.values = dict(initial or {})
        self.scoped_values: dict[tuple[str, str, str], str] = {
            ("user", "titan", key): value for key, value in self.values.items()
        }
        self.set_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def get(self, key: str, namespace: str = "titan") -> str | None:
        resolved = self.get_with_scope(key, namespace=namespace)
        return resolved.value if resolved else None

    def get_with_scope(
        self,
        key: str,
        namespace: str = "titan",
    ) -> ResolvedSecret | None:
        for scope in ("env", "project", "user"):
            scoped_key = (scope, namespace, key)
            if scoped_key in self.scoped_values:
                return ResolvedSecret(self.scoped_values[scoped_key], scope)
        return None

    def get_from_scope(
        self,
        key: str,
        namespace: str = "titan",
        scope: str = "user",
    ) -> str | None:
        return self.scoped_values.get((scope, namespace, key))

    def set(
        self,
        key: str,
        value: str,
        namespace: str = "titan",
        scope: str = "user",
    ) -> None:
        self.values[key] = value
        self.scoped_values[(scope, namespace, key)] = value
        self.set_calls.append((key, value, scope))

    def delete(self, key: str, namespace: str = "titan", scope: str = "user") -> None:
        self.scoped_values.pop((scope, namespace, key), None)
        if scope == "user":
            self.values.pop(key, None)
        self.delete_calls.append((key, scope))


class FailingSecretManager(FakeSecretManager):
    def set(
        self,
        key: str,
        value: str,
        namespace: str = "titan",
        scope: str = "user",
    ) -> None:
        self.set_calls.append((key, value, scope))
        raise RuntimeError("keyring unavailable")


class FailingDeleteSecretManager(FakeSecretManager):
    def delete(self, key: str, namespace: str = "titan", scope: str = "user") -> None:
        self.delete_calls.append((key, scope))
        raise RuntimeError("project secrets unavailable")


class SwallowingDeleteSecretManager(FakeSecretManager):
    def delete(self, key: str, namespace: str = "titan", scope: str = "user") -> None:
        self.delete_calls.append((key, scope))


def _manager(
    secrets: FakeSecretManager,
    tmp_path,
    *,
    providers=None,
) -> OAuthManager:
    return OAuthManager(
        secrets,
        providers=providers,
        lock_manager=OAuthLockManager(
            lock_dir=tmp_path,
            enable_file_locks=False,
        ),
    )


def _request(**overrides) -> OAuthRequest:
    defaults = {
        "provider": "google",
        "connection_id": "sample:demo",
        "scopes": ["resource.read"],
        "legacy_secret_keys": ["demo_legacy_access_token"],
        "access_token_env_var": "OAUTH_ACCESS_TOKEN",
        "subject": "demo",
    }
    defaults.update(overrides)
    return OAuthRequest(**defaults)


def _store_token_payload(
    secrets: FakeSecretManager,
    request: OAuthRequest,
    token_set: OAuthTokenSet,
    *,
    scope: str = "user",
) -> tuple[OAuthTokenStore, str]:
    store = OAuthTokenStore(secrets)
    secret_key = store.build_secret_key(request)
    payload = json.dumps(
        token_set.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    )
    secrets.values[secret_key] = payload
    secrets.scoped_values[(scope, "titan", secret_key)] = payload
    return store, secret_key


def _unsafe_oauth_token_set(**overrides) -> OAuthTokenSet:
    defaults = {
        "access_token": "",
        "refresh_token": None,
        "expires_at": None,
        "token_type": "Bearer",
        "scopes": (),
        "metadata": {},
    }
    defaults.update(overrides)
    token_set = object.__new__(OAuthTokenSet)
    for key, value in defaults.items():
        object.__setattr__(token_set, key, value)
    return token_set


def test_oauth_request_normalizes_scalar_scope_and_legacy_secret_key() -> None:
    request = OAuthRequest(
        provider="google",
        connection_id="sample:demo",
        scopes="openid",
        legacy_secret_keys="legacy_access_token",
    )

    assert request.scopes == ("openid",)
    assert request.legacy_secret_keys == ("legacy_access_token",)


def test_oauth_request_sorts_scopes_but_preserves_legacy_secret_key_order() -> None:
    request = OAuthRequest(
        provider="google",
        connection_id="sample:demo",
        scopes=["z.scope", "a.scope", "z.scope"],
        legacy_secret_keys=[
            " z_primary_access_token ",
            "a_fallback_access_token",
            "z_primary_access_token",
        ],
    )

    assert request.scopes == ("a.scope", "z.scope")
    assert request.legacy_secret_keys == (
        "z_primary_access_token",
        "a_fallback_access_token",
    )


def test_oauth_request_normalizes_storage_context() -> None:
    request = OAuthRequest(
        provider="google",
        connection_id="sample:demo",
        storage_context="  /workspace/ragnarok-ios  ",
    )

    assert request.storage_context == "/workspace/ragnarok-ios"


def test_oauth_storage_context_partitions_credential_key() -> None:
    global_request = _request(storage_context=None)
    ragnarok_request = _request(storage_context="/workspace/ragnarok-ios")
    other_project_request = _request(storage_context="/workspace/other-ios")

    global_key = build_oauth_credential_key(global_request)
    ragnarok_key = build_oauth_credential_key(ragnarok_request)
    other_project_key = build_oauth_credential_key(other_project_request)

    assert global_key != ragnarok_key
    assert ragnarok_key != other_project_key


def test_oauth_storage_context_partitions_user_scope_storage() -> None:
    secrets = FakeSecretManager()
    store = OAuthTokenStore(secrets)
    ragnarok_request = _request(storage_context="/workspace/ragnarok-ios")
    other_project_request = _request(storage_context="/workspace/other-ios")

    ragnarok_key = store.write(
        ragnarok_request,
        OAuthTokenSet(access_token="ragnarok-token"),
        scope="user",
    )
    other_project_key = store.write(
        other_project_request,
        OAuthTokenSet(access_token="other-token"),
        scope="user",
    )

    assert ragnarok_key != other_project_key
    assert json.loads(secrets.values[ragnarok_key])["access_token"] == "ragnarok-token"
    assert json.loads(secrets.values[other_project_key])["access_token"] == "other-token"


def test_oauth_token_set_normalizes_scalar_scope() -> None:
    token_set = OAuthTokenSet(access_token="access-token", scopes="openid")

    assert token_set.scopes == ("openid",)


def test_oauth_token_set_normalizes_string_expires_at() -> None:
    token_set = OAuthTokenSet(
        access_token="access-token",
        expires_at="9999999999",
    )

    assert token_set.expires_at == 9999999999
    assert token_set.is_valid(now=0, refresh_margin_seconds=0)


@pytest.mark.parametrize("access_token", ["", "   "])
def test_oauth_token_set_rejects_empty_access_token(access_token: str) -> None:
    with pytest.raises(ValueError, match="access_token"):
        OAuthTokenSet(access_token=access_token)


def test_oauth_token_set_rejects_non_string_access_token() -> None:
    with pytest.raises(ValueError, match="access_token"):
        OAuthTokenSet(access_token=123)


@pytest.mark.parametrize("token_type", [None, True, 123, object()])
def test_oauth_token_set_rejects_non_string_token_type(token_type: object) -> None:
    with pytest.raises(ValueError, match="token_type"):
        OAuthTokenSet(access_token="access-token", token_type=token_type)


@pytest.mark.parametrize("metadata", ["bad", [("source", "provider")], 123])
def test_oauth_token_set_rejects_non_mapping_metadata(metadata: object) -> None:
    with pytest.raises(ValueError, match="metadata"):
        OAuthTokenSet(access_token="access-token", metadata=metadata)


@pytest.mark.parametrize(
    "expires_at",
    [True, False, 123.45, "123.45", "", "   ", object()],
)
def test_oauth_token_set_rejects_invalid_expires_at(expires_at: object) -> None:
    with pytest.raises(ValueError, match="expires_at"):
        OAuthTokenSet(access_token="access-token", expires_at=expires_at)


def test_oauth_token_set_from_dict_rejects_non_string_refresh_token() -> None:
    with pytest.raises(ValueError, match="refresh_token"):
        OAuthTokenSet.from_dict(
            {
                "access_token": "access-token",
                "refresh_token": 123,
            }
        )


def test_oauth_token_set_from_dict_rejects_non_string_scope_element() -> None:
    with pytest.raises(ValueError, match=r"scopes\[1\]"):
        OAuthTokenSet.from_dict(
            {
                "access_token": "access-token",
                "scopes": ["openid", 123],
            }
        )


@pytest.mark.parametrize("token_type", [None, True, 123, object()])
def test_oauth_token_set_from_dict_rejects_non_string_token_type(
    token_type: object,
) -> None:
    with pytest.raises(ValueError, match="token_type"):
        OAuthTokenSet.from_dict(
            {
                "access_token": "access-token",
                "token_type": token_type,
            }
        )


@pytest.mark.parametrize("metadata", [None, "bad", [("source", "provider")], 123])
def test_oauth_token_set_from_dict_rejects_non_mapping_metadata(
    metadata: object,
) -> None:
    with pytest.raises(ValueError, match="metadata"):
        OAuthTokenSet.from_dict(
            {
                "access_token": "access-token",
                "metadata": metadata,
            }
        )


def test_oauth_token_set_from_dict_normalizes_string_expires_at() -> None:
    token_set = OAuthTokenSet.from_dict(
        {
            "access_token": "access-token",
            "expires_at": "9999999999",
        }
    )

    assert token_set.expires_at == 9999999999


@pytest.mark.parametrize("expires_at", [True, False, 123.45, "123.45"])
def test_oauth_token_set_from_dict_rejects_invalid_expires_at(
    expires_at: object,
) -> None:
    with pytest.raises(ValueError, match="expires_at"):
        OAuthTokenSet.from_dict(
            {
                "access_token": "access-token",
                "expires_at": expires_at,
            }
        )


@pytest.mark.parametrize("refresh_margin_seconds", [-1, 1.5, "300", True])
def test_oauth_manager_rejects_invalid_refresh_margin_seconds(
    refresh_margin_seconds: object,
) -> None:
    with pytest.raises(ValueError, match="refresh_margin_seconds"):
        OAuthManager(
            FakeSecretManager(),
            refresh_margin_seconds=refresh_margin_seconds,
        )


def test_oauth_manager_accepts_zero_refresh_margin_seconds() -> None:
    manager = OAuthManager(
        FakeSecretManager(),
        refresh_margin_seconds=0,
    )

    assert manager.refresh_margin_seconds == 0


def test_oauth_manager_prefers_environment_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OAUTH_ACCESS_TOKEN", "env-token")
    manager = _manager(
        FakeSecretManager({"demo_legacy_access_token": "legacy-token"}),
        tmp_path,
    )
    sink = CollectingOAuthEventSink()

    credential = asyncio.run(manager.get_credential(_request(), sink=sink))

    assert credential.access_token == "env-token"
    assert credential.source == "OAUTH_ACCESS_TOKEN"
    assert sink.events[-1].type == "oauth.resolve.succeeded"
    assert sink.events[-1].metadata == {"source": "OAUTH_ACCESS_TOKEN"}


def test_oauth_manager_uses_stored_oauth_blob(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="stored-token",
            expires_at=int(time.time()) + 3600,
        ),
    )
    manager = OAuthManager(
        secrets,
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "stored-token"
    assert credential.source == "oauth-cache"


def test_oauth_manager_refreshes_token_inside_expiry_margin(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="almost-expired-token",
            refresh_token="refresh-token",
            expires_at=int(time.time()) + 120,
        ),
    )

    class RefreshProvider:
        async def refresh(self, request, token_set, sink):
            return OAuthTokenSet(
                access_token="fresh-token",
                refresh_token=token_set.refresh_token,
                expires_at=int(time.time()) + 3600,
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": RefreshProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
        refresh_margin_seconds=300,
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "fresh-token"
    assert credential.source == "oauth-refresh"


@pytest.mark.parametrize("storage_scope", ["env", "project"])
def test_oauth_manager_refresh_preserves_original_storage_scope(
    monkeypatch,
    tmp_path,
    storage_scope,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="almost-expired-token",
            refresh_token="refresh-token",
            expires_at=int(time.time()) + 120,
        ),
        scope=storage_scope,
    )

    class RefreshProvider:
        async def refresh(self, request, token_set, sink):
            return OAuthTokenSet(
                access_token="fresh-token",
                refresh_token=token_set.refresh_token,
                expires_at=int(time.time()) + 3600,
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": RefreshProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
        refresh_margin_seconds=300,
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "fresh-token"
    assert credential.source == "oauth-refresh"
    assert secrets.set_calls[-1][0] == secret_key
    assert secrets.set_calls[-1][2] == storage_scope
    stored_payload = json.loads(
        secrets.scoped_values[(storage_scope, "titan", secret_key)]
    )
    assert stored_payload["access_token"] == "fresh-token"


def test_oauth_manager_refresh_preserves_omitted_refresh_token(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="almost-expired-token",
            refresh_token="stable-refresh-token",
            expires_at=int(time.time()) + 120,
            scopes=("resource.read",),
            metadata={"subject": "demo-user"},
        ),
    )

    class RefreshProvider:
        async def refresh(self, request, token_set, sink):
            return OAuthTokenSet(
                access_token="fresh-token",
                expires_at=int(time.time()) + 3600,
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": RefreshProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
        refresh_margin_seconds=300,
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "fresh-token"
    assert credential.source == "oauth-refresh"
    stored_payload = json.loads(secrets.values[secret_key])
    assert stored_payload["refresh_token"] == "stable-refresh-token"
    assert stored_payload["scopes"] == ["resource.read"]
    assert stored_payload["metadata"] == {"subject": "demo-user"}


def test_oauth_manager_refresh_merges_metadata_with_refreshed_precedence(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="almost-expired-token",
            refresh_token="stable-refresh-token",
            expires_at=int(time.time()) + 120,
            metadata={
                "subject": "old-user",
                "tenant": "masmovil",
            },
        ),
    )

    class RefreshProvider:
        async def refresh(self, request, token_set, sink):
            return OAuthTokenSet(
                access_token="fresh-token",
                expires_at=int(time.time()) + 3600,
                metadata={
                    "subject": "new-user",
                    "issuer": "google",
                },
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": RefreshProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
        refresh_margin_seconds=300,
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "fresh-token"
    stored_payload = json.loads(secrets.values[secret_key])
    assert stored_payload["metadata"] == {
        "subject": "new-user",
        "tenant": "masmovil",
        "issuer": "google",
    }


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(
            lambda: _unsafe_oauth_token_set(access_token=""),
            id="empty-access-token",
        ),
        pytest.param(
            lambda: _unsafe_oauth_token_set(access_token="   "),
            id="blank-access-token",
        ),
        pytest.param(
            lambda: OAuthTokenSet(
                access_token="fresh-token",
                refresh_token="refresh-token",
                expires_at=int(time.time()) + 120,
            ),
            id="expires-inside-refresh-margin",
        ),
        pytest.param(lambda: object(), id="wrong-type"),
    ],
)
def test_oauth_manager_rejects_invalid_refresh_result_without_writing(
    monkeypatch,
    tmp_path,
    token_factory,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="almost-expired-token",
            refresh_token="refresh-token",
            expires_at=int(time.time()) + 120,
        ),
    )
    initial_set_call_count = len(secrets.set_calls)

    class RefreshProvider:
        async def refresh(self, request, token_set, sink):
            return token_factory()

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": RefreshProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
        refresh_margin_seconds=300,
    )

    with pytest.raises(OAuthTokenRefreshError):
        asyncio.run(manager.get_credential(request))

    assert len(secrets.set_calls) == initial_set_call_count


def test_oauth_manager_refreshes_before_legacy_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager({"demo_legacy_access_token": "legacy-token"})
    request = _request()
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="expired-oauth-token",
            refresh_token="refresh-token",
            expires_at=1,
        ),
    )

    class RefreshProvider:
        async def refresh(self, request, token_set, sink):
            return OAuthTokenSet(
                access_token="fresh-token",
                refresh_token=token_set.refresh_token,
                expires_at=int(time.time()) + 3600,
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": RefreshProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "fresh-token"
    assert credential.source == "oauth-refresh"


def test_oauth_manager_reads_legacy_secret_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    manager = _manager(
        FakeSecretManager({"demo_legacy_access_token": " legacy-token "}),
        tmp_path,
    )

    credential = asyncio.run(manager.get_credential(_request()))

    assert credential.access_token == "legacy-token"
    assert credential.source == "keyring:demo_legacy_access_token"


@pytest.mark.parametrize(
    ("scope", "expected_source"),
    [
        ("env", "env:DEMO_LEGACY_ACCESS_TOKEN"),
        ("project", "project:demo_legacy_access_token"),
    ],
)
def test_oauth_manager_reports_legacy_secret_source_scope(
    monkeypatch,
    tmp_path,
    scope,
    expected_source,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    secrets.scoped_values[
        (scope, "titan", "demo_legacy_access_token")
    ] = " legacy-token "
    sink = CollectingOAuthEventSink()
    manager = _manager(secrets, tmp_path)

    credential = asyncio.run(manager.get_credential(_request(), sink=sink))

    assert credential.access_token == "legacy-token"
    assert credential.source == expected_source
    assert sink.events[-1].type == "oauth.resolve.succeeded"
    assert dict(sink.events[-1].metadata) == {"source": expected_source}


def test_oauth_manager_respects_legacy_secret_key_precedence(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    request = _request(
        legacy_secret_keys=[
            "z_primary_access_token",
            "a_fallback_access_token",
        ],
    )
    manager = _manager(
        FakeSecretManager(
            {
                "z_primary_access_token": "primary-token",
                "a_fallback_access_token": "fallback-token",
            }
        ),
        tmp_path,
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "primary-token"
    assert credential.source == "keyring:z_primary_access_token"


def test_oauth_manager_interactive_uses_legacy_before_authorization(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)

    class AuthorizingProvider:
        def __init__(self) -> None:
            self.authorize_calls = 0

        async def refresh(self, request, token_set, sink):
            raise AssertionError("refresh should not run")

        async def authorize(self, request, sink):
            self.authorize_calls += 1
            return OAuthTokenSet(access_token="browser-token")

    provider = AuthorizingProvider()
    manager = _manager(
        FakeSecretManager({"demo_legacy_access_token": " legacy-token "}),
        tmp_path,
        providers={"google": provider},
    )

    credential = asyncio.run(manager.get_credential(_request(interactive=True)))

    assert credential.access_token == "legacy-token"
    assert credential.source == "keyring:demo_legacy_access_token"
    assert provider.authorize_calls == 0


def test_oauth_manager_refresh_failure_checks_legacy_before_authorization(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager({"demo_legacy_access_token": " legacy-token "})
    request = _request(interactive=True)
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="expired-oauth-token",
            refresh_token="refresh-token",
            expires_at=1,
        ),
    )

    class RefreshThenAuthorizeProvider:
        def __init__(self) -> None:
            self.refresh_calls = 0
            self.authorize_calls = 0

        async def refresh(self, request, token_set, sink):
            self.refresh_calls += 1
            raise RuntimeError("temporary refresh failure")

        async def authorize(self, request, sink):
            self.authorize_calls += 1
            return OAuthTokenSet(access_token="browser-token")

    provider = RefreshThenAuthorizeProvider()
    manager = OAuthManager(
        secrets,
        providers={"google": provider},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "legacy-token"
    assert credential.source == "keyring:demo_legacy_access_token"
    assert provider.refresh_calls == 1
    assert provider.authorize_calls == 0


@pytest.mark.parametrize(
    "failure_factory",
    [
        pytest.param(
            lambda: OAuthTokenInvalidError("refresh token revoked"),
            id="invalid-token",
        ),
        pytest.param(
            lambda: OAuthTokenRefreshError("provider unavailable"),
            id="oauth-refresh-error",
        ),
        pytest.param(
            lambda: RuntimeError("temporary refresh failure"),
            id="unexpected-error",
        ),
    ],
)
def test_oauth_manager_noninteractive_refresh_failure_uses_legacy_secret(
    monkeypatch,
    tmp_path,
    failure_factory,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager({"demo_legacy_access_token": " legacy-token "})
    request = _request(interactive=False)
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="expired-oauth-token",
            refresh_token="refresh-token",
            expires_at=1,
        ),
    )

    class BrokenProvider:
        async def refresh(self, request, token_set, sink):
            raise failure_factory()

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": BrokenProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "legacy-token"
    assert credential.source == "keyring:demo_legacy_access_token"


@pytest.mark.parametrize("storage_scope", ["user", "env", "project"])
def test_oauth_manager_noninteractive_invalid_token_deletes_before_legacy_fallback(
    monkeypatch,
    tmp_path,
    storage_scope,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager({"demo_legacy_access_token": " legacy-token "})
    request = _request(interactive=False)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-oauth-token",
            refresh_token="revoked-refresh-token",
            expires_at=1,
        ),
        scope=storage_scope,
    )

    class InvalidTokenProvider:
        async def refresh(self, request, token_set, sink):
            raise OAuthTokenInvalidError("refresh token revoked")

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    manager = OAuthManager(
        secrets,
        providers={"google": InvalidTokenProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "legacy-token"
    assert credential.source == "keyring:demo_legacy_access_token"
    assert secrets.delete_calls[-1] == (old_secret_key, storage_scope)
    assert (storage_scope, "titan", old_secret_key) not in secrets.scoped_values


def test_oauth_manager_noninteractive_invalid_token_deletes_before_error(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request(interactive=False)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-oauth-token",
            refresh_token="revoked-refresh-token",
            expires_at=1,
        ),
        scope="project",
    )

    class InvalidTokenProvider:
        async def refresh(self, request, token_set, sink):
            raise OAuthTokenInvalidError("refresh token revoked")

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    sink = CollectingOAuthEventSink()
    manager = OAuthManager(
        secrets,
        providers={"google": InvalidTokenProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    with pytest.raises(OAuthTokenInvalidError):
        asyncio.run(manager.get_credential(request, sink=sink))

    assert secrets.delete_calls[-1] == (old_secret_key, "project")
    assert ("project", "titan", old_secret_key) not in secrets.scoped_values
    assert [event.type for event in sink.events] == [
        "oauth.resolve.started",
        "oauth.lock.acquired",
        "oauth.refresh.started",
        "oauth.refresh.failed",
        "oauth.refresh.stale_deleted",
    ]


def test_oauth_manager_invalid_token_delete_failure_emits_storage_failure(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FailingDeleteSecretManager(
        {"demo_legacy_access_token": " legacy-token "},
    )
    request = _request(interactive=False)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-oauth-token",
            refresh_token="revoked-refresh-token",
            expires_at=1,
        ),
        scope="project",
    )

    class InvalidTokenProvider:
        async def refresh(self, request, token_set, sink):
            raise OAuthTokenInvalidError("refresh token revoked")

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    sink = CollectingOAuthEventSink()
    manager = OAuthManager(
        secrets,
        providers={"google": InvalidTokenProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    with pytest.raises(OAuthStorageError) as exc_info:
        asyncio.run(manager.get_credential(request, sink=sink))

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert secrets.delete_calls[-1] == (old_secret_key, "project")
    assert ("project", "titan", old_secret_key) in secrets.scoped_values
    assert [
        (event.type, event.message, dict(event.metadata)) for event in sink.events
    ] == [
        ("oauth.resolve.started", "Resolving OAuth credential.", {}),
        ("oauth.lock.acquired", "OAuth credential lock acquired.", {}),
        ("oauth.refresh.started", "Refreshing OAuth credential.", {}),
        ("oauth.refresh.failed", "OAuth refresh failed.", {}),
        (
            "oauth.refresh.failed",
            "Stale OAuth credential could not be deleted.",
            {"phase": "storage"},
        ),
    ]
    assert "oauth.refresh.stale_deleted" not in [event.type for event in sink.events]


def test_oauth_manager_invalid_token_delete_must_remove_before_stale_deleted(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = SwallowingDeleteSecretManager(
        {"demo_legacy_access_token": " legacy-token "},
    )
    request = _request(interactive=False)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-oauth-token",
            refresh_token="revoked-refresh-token",
            expires_at=1,
        ),
        scope="user",
    )

    class InvalidTokenProvider:
        async def refresh(self, request, token_set, sink):
            raise OAuthTokenInvalidError("refresh token revoked")

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    sink = CollectingOAuthEventSink()
    manager = OAuthManager(
        secrets,
        providers={"google": InvalidTokenProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    with pytest.raises(OAuthStorageError, match="was not deleted"):
        asyncio.run(manager.get_credential(request, sink=sink))

    assert secrets.delete_calls[-1] == (old_secret_key, "user")
    assert ("user", "titan", old_secret_key) in secrets.scoped_values
    assert [event.type for event in sink.events] == [
        "oauth.resolve.started",
        "oauth.lock.acquired",
        "oauth.refresh.started",
        "oauth.refresh.failed",
        "oauth.refresh.failed",
    ]
    assert dict(sink.events[-1].metadata) == {"phase": "storage"}


def test_oauth_manager_raises_when_no_credential(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    manager = _manager(FakeSecretManager(), tmp_path)

    with pytest.raises(OAuthAuthenticationRequired):
        asyncio.run(manager.get_credential(_request()))


def test_oauth_manager_wraps_authorization_errors(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)

    class BrokenProvider:
        async def refresh(self, request, token_set, sink):
            raise AssertionError("refresh should not run")

        async def authorize(self, request, sink):
            raise RuntimeError("browser failed")

    manager = _manager(
        FakeSecretManager(),
        tmp_path,
        providers={"google": BrokenProvider()},
    )
    request = _request(interactive=True)

    with pytest.raises(OAuthAuthorizationError, match="browser failed"):
        asyncio.run(manager.get_credential(request))


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(
            lambda: _unsafe_oauth_token_set(access_token=""),
            id="empty-access-token",
        ),
        pytest.param(
            lambda: _unsafe_oauth_token_set(access_token="   "),
            id="blank-access-token",
        ),
        pytest.param(
            lambda: OAuthTokenSet(
                access_token="login-token",
                refresh_token="refresh-token",
                expires_at=int(time.time()) + 120,
            ),
            id="expires-inside-refresh-margin",
        ),
        pytest.param(lambda: object(), id="wrong-type"),
    ],
)
def test_oauth_manager_rejects_invalid_authorization_result_without_writing(
    monkeypatch,
    tmp_path,
    token_factory,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)

    class InvalidAuthorizingProvider:
        async def refresh(self, request, token_set, sink):
            raise AssertionError("refresh should not run")

        async def authorize(self, request, sink):
            return token_factory()

    secrets = FakeSecretManager()
    manager = _manager(
        secrets,
        tmp_path,
        providers={"google": InvalidAuthorizingProvider()},
    )

    with pytest.raises(OAuthAuthorizationError):
        asyncio.run(manager.get_credential(_request(interactive=True)))

    assert secrets.set_calls == []


def test_oauth_manager_refreshes_only_once_under_concurrency(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="expired-token",
            refresh_token="refresh-token",
            expires_at=1,
        ),
    )

    class RefreshProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def refresh(self, request, token_set, sink):
            self.calls += 1
            await asyncio.sleep(0.02)
            return OAuthTokenSet(
                access_token=f"fresh-token-{self.calls}",
                refresh_token=token_set.refresh_token,
                expires_at=int(time.time()) + 3600,
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    provider = RefreshProvider()
    manager = OAuthManager(
        secrets,
        providers={"google": provider},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    async def resolve_many():
        return await asyncio.gather(
            *(manager.get_credential(request) for _ in range(8))
        )

    credentials = asyncio.run(resolve_many())

    assert provider.calls == 1
    assert {credential.access_token for credential in credentials} == {"fresh-token-1"}


def test_oauth_manager_refreshes_once_across_managers_with_file_locks(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request()
    store = OAuthTokenStore(secrets)
    store.write(
        request,
        OAuthTokenSet(
            access_token="expired-token",
            refresh_token="refresh-token",
            expires_at=1,
        ),
    )

    class RefreshProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def refresh(self, request, token_set, sink):
            self.calls += 1
            await asyncio.sleep(0.05)
            return OAuthTokenSet(
                access_token=f"fresh-token-{self.calls}",
                refresh_token=token_set.refresh_token,
                expires_at=int(time.time()) + 3600,
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    provider = RefreshProvider()
    lock_dir = tmp_path / "locks"
    manager_one = OAuthManager(
        secrets,
        providers={"google": provider},
        token_store=OAuthTokenStore(secrets),
        lock_manager=OAuthLockManager(lock_dir=lock_dir, enable_file_locks=True),
    )
    manager_two = OAuthManager(
        secrets,
        providers={"google": provider},
        token_store=OAuthTokenStore(secrets),
        lock_manager=OAuthLockManager(lock_dir=lock_dir, enable_file_locks=True),
    )

    async def resolve_with_separate_managers():
        return await asyncio.gather(
            manager_one.get_credential(request),
            manager_two.get_credential(request),
        )

    credentials = asyncio.run(resolve_with_separate_managers())

    assert provider.calls == 1
    assert {credential.access_token for credential in credentials} == {"fresh-token-1"}
    assert {credential.source for credential in credentials} == {
        "oauth-cache",
        "oauth-refresh",
    }


def test_oauth_manager_interactive_authorizes_after_refresh_failure(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request(interactive=True)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-token",
            refresh_token="old-refresh-token",
            expires_at=1,
        ),
    )

    class ReauthorizingProvider:
        def __init__(self) -> None:
            self.refresh_calls = 0
            self.authorize_calls = 0

        async def refresh(self, request, token_set, sink):
            self.refresh_calls += 1
            raise RuntimeError("refresh token revoked")

        async def authorize(self, request, sink):
            self.authorize_calls += 1
            return OAuthTokenSet(
                access_token="new-login-token",
                refresh_token="new-refresh-token",
                expires_at=int(time.time()) + 3600,
            )

    provider = ReauthorizingProvider()
    sink = CollectingOAuthEventSink()
    manager = OAuthManager(
        secrets,
        providers={"google": provider},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request, sink=sink))

    assert credential.access_token == "new-login-token"
    assert credential.source == "oauth-login"
    assert provider.refresh_calls == 1
    assert provider.authorize_calls == 1
    stored_payload = json.loads(secrets.values[old_secret_key])
    assert stored_payload["refresh_token"] == "new-refresh-token"
    assert "oauth.refresh.stale_deleted" not in [event.type for event in sink.events]
    assert secrets.delete_calls == []


@pytest.mark.parametrize("storage_scope", ["env", "project"])
def test_oauth_manager_relogin_preserves_scope_for_token_without_refresh_token(
    monkeypatch,
    tmp_path,
    storage_scope,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request(interactive=True)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-token",
            expires_at=1,
        ),
        scope=storage_scope,
    )

    class ReauthorizingProvider:
        async def refresh(self, request, token_set, sink):
            raise AssertionError("refresh should not run without refresh_token")

        async def authorize(self, request, sink):
            return OAuthTokenSet(
                access_token="new-login-token",
                refresh_token="new-refresh-token",
                expires_at=int(time.time()) + 3600,
            )

    manager = OAuthManager(
        secrets,
        providers={"google": ReauthorizingProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "new-login-token"
    assert secrets.set_calls[-1][0] == old_secret_key
    assert secrets.set_calls[-1][2] == storage_scope
    assert ("user", "titan", old_secret_key) not in secrets.scoped_values
    stored_payload = json.loads(
        secrets.scoped_values[(storage_scope, "titan", old_secret_key)]
    )
    assert stored_payload["access_token"] == "new-login-token"


def test_oauth_manager_keeps_stored_token_when_refresh_and_relogin_fail(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request(interactive=True)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-token",
            refresh_token="old-refresh-token",
            expires_at=1,
        ),
    )
    old_payload = secrets.scoped_values[("user", "titan", old_secret_key)]

    class BrokenReauthorizingProvider:
        async def refresh(self, request, token_set, sink):
            raise RuntimeError("temporary network failure")

        async def authorize(self, request, sink):
            raise OAuthAuthorizationError("user cancelled")

    manager = OAuthManager(
        secrets,
        providers={"google": BrokenReauthorizingProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    with pytest.raises(OAuthAuthorizationError, match="user cancelled"):
        asyncio.run(manager.get_credential(request))

    assert secrets.delete_calls == []
    assert secrets.scoped_values[("user", "titan", old_secret_key)] == old_payload


@pytest.mark.parametrize("storage_scope", ["env", "project"])
def test_oauth_manager_deletes_explicitly_invalid_token_before_relogin(
    monkeypatch,
    tmp_path,
    storage_scope,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FakeSecretManager()
    request = _request(interactive=True)
    store = OAuthTokenStore(secrets)
    old_secret_key = store.write(
        request,
        OAuthTokenSet(
            access_token="expired-token",
            refresh_token="old-refresh-token",
            expires_at=1,
        ),
        scope=storage_scope,
    )

    class ReauthorizingProvider:
        async def refresh(self, request, token_set, sink):
            raise OAuthTokenInvalidError("refresh token revoked")

        async def authorize(self, request, sink):
            return OAuthTokenSet(
                access_token="new-login-token",
                refresh_token="new-refresh-token",
                expires_at=int(time.time()) + 3600,
            )

    manager = OAuthManager(
        secrets,
        providers={"google": ReauthorizingProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    credential = asyncio.run(manager.get_credential(request))

    assert credential.access_token == "new-login-token"
    assert secrets.delete_calls[-1] == (old_secret_key, storage_scope)
    assert secrets.set_calls[-1][0] == old_secret_key
    assert secrets.set_calls[-1][2] == storage_scope
    assert ("user", "titan", old_secret_key) not in secrets.scoped_values
    stored_payload = json.loads(
        secrets.scoped_values[(storage_scope, "titan", old_secret_key)]
    )
    assert stored_payload["refresh_token"] == "new-refresh-token"


def test_oauth_manager_saves_one_json_blob(tmp_path) -> None:
    secrets = FakeSecretManager()
    manager = _manager(secrets, tmp_path)
    request = _request()

    secret_key = manager.save_token_set_blocking(
        request,
        OAuthTokenSet(access_token="manual-token"),
    )

    assert secret_key.startswith("oauth_google_")
    stored_payload = json.loads(secrets.values[secret_key])
    assert stored_payload["access_token"] == "manual-token"
    assert [call[0] for call in secrets.set_calls] == [secret_key]


def test_oauth_manager_save_token_set_write_failure_emits_storage_failure(
    tmp_path,
) -> None:
    secrets = FailingSecretManager()
    manager = _manager(secrets, tmp_path)
    sink = CollectingOAuthEventSink()

    with pytest.raises(OAuthStorageError) as exc_info:
        manager.save_token_set_blocking(
            _request(),
            OAuthTokenSet(access_token="manual-token"),
            sink=sink,
        )

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert [event.type for event in sink.events] == ["oauth.storage.failed"]
    assert dict(sink.events[0].metadata) == {"phase": "storage"}


def test_oauth_manager_save_token_set_rejects_invalid_scope_without_saved_event(
    tmp_path,
) -> None:
    secrets = FakeSecretManager()
    manager = _manager(secrets, tmp_path)
    sink = CollectingOAuthEventSink()

    with pytest.raises(OAuthStorageError) as exc_info:
        manager.save_token_set_blocking(
            _request(),
            OAuthTokenSet(access_token="manual-token"),
            scope="invalid",
            sink=sink,
        )

    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "OAuth storage scope must be one of" in str(exc_info.value.__cause__)
    assert secrets.set_calls == []
    assert [event.type for event in sink.events] == ["oauth.storage.failed"]
    assert dict(sink.events[0].metadata) == {"phase": "storage"}


def test_oauth_manager_refresh_write_failure_emits_refresh_failure(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FailingSecretManager()
    request = _request()
    store, _secret_key = _store_token_payload(
        secrets,
        request,
        OAuthTokenSet(
            access_token="expired-token",
            refresh_token="refresh-token",
            expires_at=1,
        ),
    )

    class RefreshProvider:
        async def refresh(self, request, token_set, sink):
            return OAuthTokenSet(
                access_token="fresh-token",
                refresh_token=token_set.refresh_token,
                expires_at=int(time.time()) + 3600,
            )

        async def authorize(self, request, sink):
            raise AssertionError("authorize should not run")

    sink = CollectingOAuthEventSink()
    manager = OAuthManager(
        secrets,
        providers={"google": RefreshProvider()},
        token_store=store,
        lock_manager=OAuthLockManager(lock_dir=tmp_path, enable_file_locks=False),
    )

    with pytest.raises(OAuthStorageError) as exc_info:
        asyncio.run(manager.get_credential(request, sink=sink))

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert [event.type for event in sink.events] == [
        "oauth.resolve.started",
        "oauth.lock.acquired",
        "oauth.refresh.started",
        "oauth.refresh.failed",
    ]
    assert dict(sink.events[-1].metadata) == {"phase": "storage"}


def test_oauth_manager_authorization_write_failure_emits_authorize_failure(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OAUTH_ACCESS_TOKEN", raising=False)
    secrets = FailingSecretManager()

    class AuthorizingProvider:
        async def refresh(self, request, token_set, sink):
            raise AssertionError("refresh should not run")

        async def authorize(self, request, sink):
            return OAuthTokenSet(
                access_token="login-token",
                refresh_token="refresh-token",
                expires_at=int(time.time()) + 3600,
            )

    sink = CollectingOAuthEventSink()
    manager = _manager(
        secrets,
        tmp_path,
        providers={"google": AuthorizingProvider()},
    )

    with pytest.raises(OAuthStorageError) as exc_info:
        asyncio.run(manager.get_credential(_request(interactive=True), sink=sink))

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert [event.type for event in sink.events] == [
        "oauth.resolve.started",
        "oauth.lock.acquired",
        "oauth.authorize.started",
        "oauth.authorize.failed",
    ]
    assert dict(sink.events[-1].metadata) == {"phase": "storage"}


def test_oauth_token_store_wraps_json_serialization_errors() -> None:
    store = OAuthTokenStore(FakeSecretManager())
    token_set = OAuthTokenSet(
        access_token="manual-token",
        metadata={"bad": object()},
    )

    with pytest.raises(OAuthStorageError) as exc_info:
        store.write(_request(), token_set)

    assert isinstance(exc_info.value.__cause__, TypeError)


def test_oauth_token_store_wraps_secret_write_errors() -> None:
    store = OAuthTokenStore(FailingSecretManager())

    with pytest.raises(OAuthStorageError) as exc_info:
        store.write(_request(), OAuthTokenSet(access_token="manual-token"))

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_oauth_token_store_wraps_secret_delete_errors() -> None:
    store = OAuthTokenStore(FailingDeleteSecretManager())

    with pytest.raises(OAuthStorageError) as exc_info:
        store.delete(_request(), scope="project")

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_oauth_token_store_requires_delete_postcondition() -> None:
    secrets = SwallowingDeleteSecretManager()
    store = OAuthTokenStore(secrets)
    request = _request()
    secret_key = store.write(
        request,
        OAuthTokenSet(access_token="manual-token"),
        scope="user",
    )

    with pytest.raises(OAuthStorageError, match="was not deleted"):
        store.delete(request, scope="user")

    assert secrets.delete_calls[-1] == (secret_key, "user")
    assert ("user", "titan", secret_key) in secrets.scoped_values


def test_oauth_token_store_wraps_invalid_scope_without_writing() -> None:
    secrets = FakeSecretManager()
    store = OAuthTokenStore(secrets)

    with pytest.raises(OAuthStorageError) as exc_info:
        store.write(
            _request(),
            OAuthTokenSet(access_token="manual-token"),
            scope="invalid",
        )

    assert isinstance(exc_info.value.__cause__, ValueError)
    assert secrets.set_calls == []


def test_oauth_lock_async_acquire_cancellation_does_not_leak_lock(tmp_path) -> None:
    async def exercise_cancelled_acquire() -> None:
        manager = OAuthLockManager(
            lock_dir=tmp_path,
            enable_file_locks=False,
            poll_interval_seconds=0.01,
        )
        held_lock = manager.acquire_blocking("sample:demo", timeout_seconds=1)
        pending_acquire = asyncio.create_task(
            manager.acquire("sample:demo", timeout_seconds=1)
        )

        await asyncio.sleep(0.05)
        pending_acquire.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_acquire

        held_lock.release()
        await asyncio.sleep(0.05)
        next_lock = await manager.acquire("sample:demo", timeout_seconds=0.2)
        next_lock.release()

    asyncio.run(exercise_cancelled_acquire())


def test_oauth_lock_file_lock_uses_remaining_timeout(
    monkeypatch,
    tmp_path,
) -> None:
    captured_timeouts = []

    class FakeFileLock:
        def __init__(
            self,
            path,
            *,
            timeout_seconds,
            poll_interval_seconds,
        ) -> None:
            captured_timeouts.append(timeout_seconds)

        def acquire(self, cancel_event=None) -> None:
            return None

        def release(self) -> None:
            return None

    monkeypatch.setattr(oauth_locks, "_FileLock", FakeFileLock)
    manager = OAuthLockManager(
        lock_dir=tmp_path,
        enable_file_locks=True,
        poll_interval_seconds=0.01,
    )
    thread_lock = manager._get_thread_lock("sample:demo")
    thread_lock.acquire()

    def release_thread_lock() -> None:
        time.sleep(0.05)
        thread_lock.release()

    releaser = threading.Thread(target=release_thread_lock)
    releaser.start()
    held_lock = manager.acquire_blocking("sample:demo", timeout_seconds=0.5)
    held_lock.release()
    releaser.join()

    assert captured_timeouts
    assert 0 < captured_timeouts[0] < 0.5


def test_file_lock_timeout_zero_attempts_uncontended_lock_once(tmp_path) -> None:
    lock = oauth_locks._FileLock(
        tmp_path / "oauth.lock",
        timeout_seconds=0,
        poll_interval_seconds=0.1,
    )
    attempts = 0

    def try_acquire_once() -> None:
        nonlocal attempts
        attempts += 1

    lock._try_acquire_once = try_acquire_once

    lock.acquire()

    assert attempts == 1
    lock.release()


def test_file_lock_timeout_zero_times_out_after_contended_attempt(tmp_path) -> None:
    lock = oauth_locks._FileLock(
        tmp_path / "oauth.lock",
        timeout_seconds=0,
        poll_interval_seconds=0.1,
    )
    attempts = 0

    def try_acquire_once() -> None:
        nonlocal attempts
        attempts += 1
        raise BlockingIOError(errno.EAGAIN, "resource temporarily unavailable")

    lock._try_acquire_once = try_acquire_once

    started_at = time.monotonic()
    with pytest.raises(OAuthLockTimeout):
        lock.acquire()
    elapsed = time.monotonic() - started_at

    assert attempts == 1
    assert elapsed < 0.05
    assert lock._handle is None


def test_file_lock_retries_lock_contention_error(tmp_path) -> None:
    lock = oauth_locks._FileLock(
        tmp_path / "oauth.lock",
        timeout_seconds=1,
        poll_interval_seconds=0,
    )
    attempts = 0
    original_try_acquire_once = lock._try_acquire_once

    def try_acquire_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise BlockingIOError(errno.EAGAIN, "resource temporarily unavailable")
        original_try_acquire_once()

    lock._try_acquire_once = try_acquire_once

    lock.acquire()

    assert attempts == 2
    lock.release()


def test_file_lock_timeout_is_hard_bound_when_poll_interval_exceeds_timeout(
    tmp_path,
) -> None:
    lock = oauth_locks._FileLock(
        tmp_path / "oauth.lock",
        timeout_seconds=0.01,
        poll_interval_seconds=0.1,
    )
    attempts = 0

    def try_acquire_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise BlockingIOError(errno.EAGAIN, "resource temporarily unavailable")

    lock._try_acquire_once = try_acquire_once

    with pytest.raises(OAuthLockTimeout):
        lock.acquire()

    assert attempts == 1
    assert lock._handle is None


def test_file_lock_windows_byte_initialization_does_not_grow_file(
    monkeypatch,
    tmp_path,
) -> None:
    lock_path = tmp_path / "oauth.lock"
    lock = oauth_locks._FileLock(
        lock_path,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )
    monkeypatch.setattr(oauth_locks.os, "name", "nt")

    lock._handle = open(lock_path, "a+")
    try:
        lock._ensure_windows_lock_byte()
        lock._ensure_windows_lock_byte()
    finally:
        lock._close_handle()

    assert lock_path.read_text() == "0"


def test_file_lock_propagates_non_contention_oserror(tmp_path) -> None:
    lock = oauth_locks._FileLock(
        tmp_path / "oauth.lock",
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    def try_acquire_once() -> None:
        raise OSError(errno.ENOSPC, "no space left on device")

    lock._try_acquire_once = try_acquire_once

    with pytest.raises(OSError) as exc_info:
        lock.acquire()

    assert exc_info.value.errno == errno.ENOSPC
    assert lock._handle is None


def test_queued_oauth_event_sink_drains_events() -> None:
    sink = QueuedOAuthEventSink()

    sink.emit(OAuthEvent(type="oauth.resolve.started", operation_id="op-1"))
    sink.emit(OAuthEvent(type="oauth.resolve.succeeded", operation_id="op-1"))

    assert [event.type for event in sink.drain()] == [
        "oauth.resolve.started",
        "oauth.resolve.succeeded",
    ]
    assert sink.get(block=False) is None


def test_queued_oauth_event_sink_nonblocking_get_ignores_timeout() -> None:
    sink = QueuedOAuthEventSink()

    assert sink.get(block=False, timeout=1) is None

    event = OAuthEvent(type="oauth.resolve.started", operation_id="op-1")
    sink.emit(event)

    assert sink.get(block=False, timeout=1) == event


def test_oauth_event_metadata_is_immutable_snapshot() -> None:
    metadata = {
        "source": "oauth-cache",
        "nested": {"safe": "value"},
        "items": ["first"],
    }

    event = OAuthEvent(
        type="oauth.resolve.succeeded",
        operation_id="op-1",
        metadata=metadata,
    )
    metadata["source"] = "mutated"
    metadata["token"] = "secret"
    metadata["nested"]["safe"] = "mutated"
    metadata["items"].append("second")

    assert event.metadata == {
        "source": "oauth-cache",
    }
    assert "token" not in event.metadata
    assert "nested" not in event.metadata
    assert "items" not in event.metadata
    with pytest.raises(TypeError):
        event.metadata["token"] = "secret"


def test_oauth_event_metadata_redacts_sensitive_fields_and_drops_unknowns() -> None:
    event = OAuthEvent(
        type="oauth.provider.debug",
        operation_id="op-1",
        metadata={
            "access_token": "raw-access-token",
            "authorization": "Bearer raw-access-token",
            "client_secret": "raw-client-secret",
            "nested": {
                "refresh_token": "raw-refresh-token",
                "safe": "value",
            },
            "items": [
                {
                    "token": "raw-list-token",
                    "label": "kept",
                }
            ],
            "tuple_items": (
                {
                    "id_token": "raw-id-token",
                    "audience": "kept",
                },
            ),
            "set_items": frozenset({"safe"}),
        },
    )

    assert event.metadata["access_token"] == "<redacted>"
    assert event.metadata["authorization"] == "<redacted>"
    assert event.metadata["client_secret"] == "<redacted>"
    assert "nested" not in event.metadata
    assert "items" not in event.metadata
    assert "tuple_items" not in event.metadata
    assert "set_items" not in event.metadata


def test_oauth_event_sanitizes_external_message_and_authorization_metadata() -> None:
    raw_token = "raw-access-token"

    event = OAuthEvent(
        type="oauth.provider.debug",
        operation_id="op-1",
        message=raw_token,
        metadata={
            "authorization": raw_token,
            "debug": raw_token,
            "source": raw_token,
        },
    )

    assert event.message == "<redacted>"
    assert event.metadata["authorization"] == "<redacted>"
    assert event.metadata["source"] == "<redacted>"
    assert "debug" not in event.metadata


def test_oauth_event_preserves_safe_lifecycle_message_and_metadata() -> None:
    event = OAuthEvent(
        type="oauth.resolve.succeeded",
        operation_id="op-1",
        message="OAuth credential resolved.",
        metadata={
            "source": "OAUTH_ACCESS_TOKEN",
            "phase": "storage",
            "secret_key": "oauth_google_demo_access_token",
        },
    )

    assert event.message == "OAuth credential resolved."
    assert event.metadata == {
        "source": "OAUTH_ACCESS_TOKEN",
        "phase": "storage",
        "secret_key": "oauth_google_demo_access_token",
    }


def test_queued_oauth_event_sink_drops_new_events_when_full() -> None:
    sink = QueuedOAuthEventSink(maxsize=1)

    sink.emit(OAuthEvent(type="oauth.resolve.started", operation_id="op-1"))
    sink.emit(OAuthEvent(type="oauth.resolve.succeeded", operation_id="op-1"))

    assert [event.type for event in sink.drain()] == ["oauth.resolve.started"]
    assert sink.dropped_count == 1


def test_oauth_manager_queue_overflow_does_not_abort_resolution(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("OAUTH_ACCESS_TOKEN", "env-token")
    manager = _manager(FakeSecretManager(), tmp_path)
    sink = QueuedOAuthEventSink(maxsize=1)

    credential = asyncio.run(manager.get_credential(_request(), sink=sink))

    assert credential.access_token == "env-token"
    assert sink.dropped_count >= 1
