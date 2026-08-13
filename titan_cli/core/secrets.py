# Transitional re-export. The real implementation moved inside the security
# boundary (titan_cli/core/security/_vault.py); this module exists only so
# not-yet-migrated code keeps importing SecretManager from its old location.
# Every remaining importer is pinned in the shrink-only allowlist of
# tests/core/security/test_architecture.py; when that list empties, this file
# is deleted with it.
from titan_cli.core.security._vault import ScopeType, SecretManager

__all__ = ["ScopeType", "SecretManager"]
