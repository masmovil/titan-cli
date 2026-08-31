"""OAuth coordination primitives for Titan plugins."""

from .events import (
    CollectingOAuthEventSink,
    NullOAuthEventSink,
    OAuthEvent,
    OAuthEventSink,
    QueuedOAuthEventSink,
)
from .exceptions import (
    OAuthAuthenticationRequired,
    OAuthAuthorizationError,
    OAuthError,
    OAuthLockTimeout,
    OAuthProviderNotFound,
    OAuthStorageError,
    OAuthTokenInvalidError,
    OAuthTokenRefreshError,
)
from .locks import OAuthHeldLock, OAuthLockManager
from .manager import OAuthManager, OAuthProvider
from .models import (
    OAuthCredential,
    OAuthRequest,
    OAuthTokenSet,
    build_oauth_credential_key,
)
from .storage import OAuthTokenStore

__all__ = [
    "CollectingOAuthEventSink",
    "NullOAuthEventSink",
    "OAuthAuthenticationRequired",
    "OAuthAuthorizationError",
    "OAuthCredential",
    "OAuthError",
    "OAuthEvent",
    "OAuthEventSink",
    "OAuthHeldLock",
    "OAuthLockManager",
    "OAuthManager",
    "OAuthProvider",
    "OAuthProviderNotFound",
    "OAuthRequest",
    "OAuthStorageError",
    "OAuthTokenInvalidError",
    "OAuthTokenRefreshError",
    "OAuthTokenSet",
    "OAuthTokenStore",
    "OAuthLockTimeout",
    "QueuedOAuthEventSink",
    "build_oauth_credential_key",
]
