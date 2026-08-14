"""
Plugin trust classification and static security scan.

Titan's secrets live behind the `core/security/` boundary, but every plugin
still runs in-process: nothing stops code from importing `keyring` on its
own. The scan below does not pretend to be a sandbox (that is the future
worker model) — it makes the access *visible*: a community plugin whose
source imports keyring, the private vault, or `SecretManager` gets flagged
at load time, so touching the user's credentials becomes demonstrable
intent instead of something that blends into the noise. It composes with
the channel system: a stable plugin is pinned to a commit SHA, so the
scanned source is immutable until the user explicitly updates it.
"""

import ast
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Optional

from .available import KNOWN_PLUGINS
from .community_sources import PluginChannel


class PluginTrust(StrEnum):
    """
    How much the origin of a plugin's code is vouched for.

    OFFICIAL: shipped by the Titan project itself (named in KNOWN_PLUGINS,
        installed as a regular package).
    VERIFIED: reserved — a future registry of third-party plugins reviewed
        by the Titan project. Nothing assigns it yet.
    COMMUNITY: third-party code (a repo-pinned stable install, or an
        installed package Titan does not recognize as official).
    LOCAL: a dev_local path on this machine — trusted by the user by
        definition (it is their working copy), but still scanned so an
        unnoticed secret-access edit shows up.
    """

    OFFICIAL = "official"
    VERIFIED = "verified"
    COMMUNITY = "community"
    LOCAL = "local"


_OFFICIAL_NAMES = frozenset(p["name"] for p in KNOWN_PLUGINS)


def classify_plugin(plugin_name: str, channel: Optional[PluginChannel]) -> PluginTrust:
    """
    Classify a plugin from its name and effective source channel.

    `channel` is None for plugins discovered via entry points (regular
    package installs); a source override in the project config makes it
    DEV_LOCAL or STABLE.
    """
    if channel == PluginChannel.DEV_LOCAL:
        return PluginTrust.LOCAL
    if channel == PluginChannel.STABLE:
        return PluginTrust.COMMUNITY
    if plugin_name in _OFFICIAL_NAMES:
        return PluginTrust.OFFICIAL
    return PluginTrust.COMMUNITY


@dataclass(frozen=True)
class TrustFinding:
    """One secret-access construct found in a plugin's source."""

    file: str  # path relative to the scanned source dir
    line: int
    code: str  # "keyring-import" | "vault-import" | "secret-manager" | "unparseable"
    detail: str


# Non-code directories, skipped at any depth.
_SKIPPED_DIRS = {".git", "__pycache__", ".venv", "venv"}

# Test directories are only skipped as TOP-LEVEL siblings of the package:
# skipping `tests` at any depth would let a plugin hide importable runtime
# code in `<pkg>/tests/` and never have it scanned.
_SKIPPED_TOP_LEVEL_DIRS = {"tests", "test"}

_VAULT_MODULE = "titan_cli.core.security._vault"


def _findings_for_module(module: Optional[str], node: ast.AST, rel: str) -> list[TrustFinding]:
    if not module:
        return []
    if module == "keyring" or module.startswith("keyring."):
        return [TrustFinding(rel, node.lineno, "keyring-import",
                             f"imports '{module}' (direct OS keyring access)")]
    if module == _VAULT_MODULE or module.startswith(f"{_VAULT_MODULE}."):
        return [TrustFinding(rel, node.lineno, "vault-import",
                             f"imports '{module}' (Titan's private vault)")]
    return []


def scan_plugin_source(source_dir: Path) -> list[TrustFinding]:
    """
    Statically scan a plugin source tree for secret-access constructs.

    Flags imports of `keyring`, imports of the private vault module, and any
    reference to the name `SecretManager`. Best-effort by design: obfuscated
    access (importlib, getattr chains) is out of scope — the goal is that
    *plain* access can never claim to be accidental. Unparseable files are
    reported as findings too, so a syntax error cannot hide code from the scan.
    """
    findings: list[TrustFinding] = []
    source_dir = Path(source_dir)

    for path in sorted(source_dir.rglob("*.py")):
        rel_parts = path.relative_to(source_dir).parts
        if any(part in _SKIPPED_DIRS for part in rel_parts):
            continue
        if rel_parts[0] in _SKIPPED_TOP_LEVEL_DIRS:
            continue
        rel = "/".join(rel_parts)

        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            findings.append(TrustFinding(rel, e.lineno or 0, "unparseable",
                                         f"could not parse file: {e.msg}"))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    findings.extend(_findings_for_module(alias.name, node, rel))
            elif isinstance(node, ast.ImportFrom):
                findings.extend(_findings_for_module(node.module, node, rel))
                if node.module and node.module.startswith("titan_cli"):
                    for alias in node.names:
                        if alias.name == "SecretManager":
                            findings.append(TrustFinding(
                                rel, node.lineno, "secret-manager",
                                f"imports SecretManager from '{node.module}'"))
                        # `from titan_cli.core.security import _vault` carries
                        # the vault module in `names`, not in `module`.
                        elif alias.name == "_vault":
                            findings.append(TrustFinding(
                                rel, node.lineno, "vault-import",
                                f"imports '_vault' from '{node.module}' (Titan's private vault)"))
            elif isinstance(node, ast.Name) and node.id == "SecretManager":
                findings.append(TrustFinding(
                    rel, node.lineno, "secret-manager",
                    "references SecretManager"))
            elif isinstance(node, ast.Attribute) and node.attr == "SecretManager":
                findings.append(TrustFinding(
                    rel, node.lineno, "secret-manager",
                    "references SecretManager"))

    return findings
