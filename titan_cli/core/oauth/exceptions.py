"""Exceptions raised by Titan's OAuth coordination layer."""


class OAuthError(Exception):
    """Base exception for OAuth coordination failures."""


class OAuthAuthenticationRequired(OAuthError):
    """Raised when no usable credential is available."""


class OAuthAuthorizationError(OAuthError):
    """Raised when an OAuth provider cannot authorize a new credential."""


class OAuthProviderNotFound(OAuthError):
    """Raised when a request needs an OAuth provider that is not registered."""


class OAuthStorageError(OAuthError):
    """Raised when OAuth credential storage cannot be read or written."""


class OAuthTokenRefreshError(OAuthError):
    """Raised when an OAuth provider cannot refresh an expired credential."""


class OAuthTokenInvalidError(OAuthTokenRefreshError):
    """Raised when a stored OAuth refresh token is explicitly invalid."""


class OAuthLockTimeout(OAuthError):
    """Raised when a credential lock cannot be acquired in time."""
