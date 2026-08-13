"""
Architecture test for the secrets trust boundary (harness: secrets_hardening,
sec-004).

Only `titan_cli/core/security/` may touch raw secret strings. Concretely:

- `keyring` and the private vault (`titan_cli.core.security._vault`) may not
  be imported anywhere else, from day one. The transitional
  `titan_cli/core/secrets.py` shim is the single sanctioned `_vault` importer.
- The legacy `SecretManager` (via `titan_cli.core.secrets`) is governed by a
  SHRINK-ONLY allowlist: this test fails if a NEW module starts importing it,
  AND it fails if an allowlisted module no longer does (so the list can only
  get shorter). When the list empties, delete the allowlist, the shim, and
  keep the outright ban.

Production code only — tests may construct SecretManager freely.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

SECURITY_PACKAGE = "titan_cli/core/security"
VAULT_MODULE = "titan_cli.core.security._vault"
LEGACY_MODULE = "titan_cli.core.secrets"

# The one module allowed to import the private vault: the transitional
# re-export shim. Deleted together with the allowlist below.
VAULT_IMPORT_EXCEPTIONS = {
    "titan_cli/core/secrets.py",
}

# Legacy SecretManager importers, pinned 2026-08-13. SHRINK ONLY: never add
# an entry. Each migration feature deletes its own lines —
# sec-006: ai/client.py, ai/router/*, github_client.py, engine/builder.py
#          (the builder only keeps it to feed the AI chain until then)
# sec-007: core/config.py, ui/tui/*, every plugin.py
LEGACY_IMPORTER_ALLOWLIST = {
    "plugins/titan-plugin-git/titan_plugin_git/plugin.py",
    "plugins/titan-plugin-github/titan_plugin_github/clients/github_client.py",
    "plugins/titan-plugin-github/titan_plugin_github/plugin.py",
    "plugins/titan-plugin-jira/titan_plugin_jira/plugin.py",
    "plugins/titan-plugin-slack/titan_plugin_slack/plugin.py",
    "titan_cli/ai/client.py",
    "titan_cli/ai/router/availability.py",
    "titan_cli/ai/router/executor.py",
    "titan_cli/core/config.py",
    "titan_cli/engine/builder.py",
    "titan_cli/ui/tui/__init__.py",
    "titan_cli/ui/tui/screens/ai_config.py",
    "titan_cli/ui/tui/screens/ai_config_wizard.py",
}


def _production_files():
    """Every production .py file: titan_cli/ plus each plugin's package dir."""
    files = list((REPO_ROOT / "titan_cli").rglob("*.py"))
    for plugin_dir in (REPO_ROOT / "plugins").glob("titan-plugin-*"):
        for package_dir in plugin_dir.glob("titan_plugin_*"):
            if package_dir.is_dir():
                files.extend(package_dir.rglob("*.py"))
    return files


def _module_name(path: Path) -> str:
    """Dotted module name for resolving relative imports."""
    rel = path.relative_to(REPO_ROOT)
    if rel.parts[0] == "plugins":
        # plugins/titan-plugin-x/titan_plugin_x/... -> package rooted at part 2
        rel = Path(*rel.parts[2:])
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path: Path):
    """Yield absolute dotted module names imported by the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module = _module_name(path)
    package_parts = module.split(".")[:-1] if not _is_package_init(path) else module.split(".")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    yield node.module
                    for alias in node.names:
                        yield f"{node.module}.{alias.name}"
            else:
                base = package_parts[: len(package_parts) - node.level + 1]
                prefix = ".".join(base)
                resolved = f"{prefix}.{node.module}" if node.module else prefix
                yield resolved
                for alias in node.names:
                    yield f"{resolved}.{alias.name}"


def _is_package_init(path: Path) -> bool:
    return path.name == "__init__.py"


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _importers_of(target_prefixes):
    importers = set()
    for path in _production_files():
        for imported in _imported_modules(path):
            if any(imported == t or imported.startswith(f"{t}.") for t in target_prefixes):
                importers.add(_rel(path))
                break
    return importers


def test_keyring_only_imported_inside_security_boundary():
    offenders = {
        f for f in _importers_of({"keyring"})
        if not f.startswith(SECURITY_PACKAGE)
    }
    assert offenders == set(), (
        f"keyring may only be imported inside {SECURITY_PACKAGE}/. "
        f"Offenders: {sorted(offenders)}. Use the SecretBroker / session "
        f"factories instead of talking to the keyring directly."
    )


def test_vault_only_imported_inside_security_boundary():
    offenders = {
        f for f in _importers_of({VAULT_MODULE})
        if not f.startswith(SECURITY_PACKAGE) and f not in VAULT_IMPORT_EXCEPTIONS
    }
    assert offenders == set(), (
        f"The private vault ({VAULT_MODULE}) may only be imported inside "
        f"{SECURITY_PACKAGE}/ plus the transitional shim. "
        f"Offenders: {sorted(offenders)}."
    )


def test_legacy_secret_manager_importers_ratchet():
    importers = {
        f for f in _importers_of({LEGACY_MODULE})
        if not f.startswith(SECURITY_PACKAGE)
    }

    new_importers = importers - LEGACY_IMPORTER_ALLOWLIST
    assert new_importers == set(), (
        f"New importer(s) of the legacy SecretManager: {sorted(new_importers)}. "
        f"The allowlist only shrinks — new code must use SecretBroker or a "
        f"session factory from titan_cli.core.security."
    )

    cleaned = LEGACY_IMPORTER_ALLOWLIST - importers
    assert cleaned == set(), (
        f"These modules no longer import the legacy SecretManager — remove "
        f"them from LEGACY_IMPORTER_ALLOWLIST so the ratchet tightens: "
        f"{sorted(cleaned)}. If the list is now empty, delete the allowlist "
        f"and the titan_cli/core/secrets.py shim entirely."
    )
