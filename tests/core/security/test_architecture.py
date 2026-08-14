"""
Architecture test for the secrets trust boundary.

Only `titan_cli/core/security/` may touch raw secret strings: `keyring`, the
private vault (`titan_cli.core.security._vault`), and the retired
`titan_cli.core.secrets` location are banned outright everywhere else. The
migration ratchet that used to live here has fully tightened — the shim and
its shrink-only allowlist are gone; these tests keep anyone from quietly
bringing either back.

Production code only — tests may construct SecretManager freely.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

SECURITY_PACKAGE = "titan_cli/core/security"
VAULT_MODULE = "titan_cli.core.security._vault"
LEGACY_MODULE = "titan_cli.core.secrets"

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
        if not f.startswith(SECURITY_PACKAGE)
    }
    assert offenders == set(), (
        f"The private vault ({VAULT_MODULE}) may only be imported inside "
        f"{SECURITY_PACKAGE}/. Offenders: {sorted(offenders)}."
    )


def test_vault_attribute_never_reached_outside_boundary():
    """
    Import bans don't stop `broker._vault.get(...)` — the broker instance
    carries a live vault reference. Reaching for a `_vault` attribute outside
    the boundary is the textual signature of that escape hatch, so ban it.
    """
    offenders = set()
    for path in _production_files():
        rel = _rel(path)
        if rel.startswith(SECURITY_PACKAGE):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "_vault":
                offenders.add(f"{rel}:{node.lineno}")
    assert offenders == set(), (
        f"`._vault` attribute access outside {SECURITY_PACKAGE}/ reads raw "
        f"secrets through the broker's private reference. Offenders: "
        f"{sorted(offenders)}."
    )


def test_retired_secrets_module_is_never_imported():
    """titan_cli.core.secrets was the pre-boundary home of SecretManager; the
    module is deleted and must not come back as an import target."""
    importers = _importers_of({LEGACY_MODULE})
    assert importers == set(), (
        f"titan_cli.core.secrets no longer exists — these files import it: "
        f"{sorted(importers)}. Use SecretBroker or a session factory from "
        f"titan_cli.core.security instead."
    )
