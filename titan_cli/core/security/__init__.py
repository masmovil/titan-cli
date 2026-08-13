"""
Titan's single trust boundary for secrets.

Only code inside this package may touch raw secret strings, the OS keyring,
or the private vault. Everything outside works with opaque `SecretRef`
handles and a `SecretBroker` that deliberately has no read API: a secret can
be stored, checked for existence, deleted, or *used* — never returned.

The boundary is enforced by an architecture test
(tests/core/security/test_architecture.py), not just by convention.
"""

from .broker import (
    SecretBroker,
    SecretBrokerFactory,
    SecretRef,
    create_broker_factory,
    derive_namespace,
)
from .execution import SecureCommandResult
from .redaction import redact, register_secret
from .sessions import AuthScheme, create_ai_provider, create_authenticated_session

__all__ = [
    "AuthScheme",
    "SecretBroker",
    "SecretBrokerFactory",
    "SecretRef",
    "SecureCommandResult",
    "create_ai_provider",
    "create_authenticated_session",
    "create_broker_factory",
    "derive_namespace",
    "redact",
    "register_secret",
]
