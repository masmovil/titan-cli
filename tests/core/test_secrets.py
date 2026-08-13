"""
The real SecretManager tests live in tests/core/security/test_vault.py —
titan_cli/core/secrets.py is now only a transitional re-export shim for the
importers pinned in tests/core/security/test_architecture.py.
"""

import typing

from titan_cli.core import secrets
from titan_cli.core.security import _vault


def test_shim_reexports_the_vault_class():
    assert secrets.SecretManager is _vault.SecretManager


def test_env_scope_no_longer_exists():
    assert typing.get_args(secrets.ScopeType) == ("project", "user")
