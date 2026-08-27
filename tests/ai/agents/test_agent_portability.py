"""
Every agent must run on either transport.

That guarantee does not come from any contract or base class - it comes from
agents only ever reaching `AIGenerator`. An agent that imports a concrete
transport can be handed one and only one thing, and the user's choice between a
remote connection and a local CLI stops meaning anything for it.

This is the check that keeps the rule true as agents get added, which is exactly
when it would otherwise be broken by accident.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Modules that mean "a specific transport". An agent needing any of these is an
# agent that has stopped being portable.
FORBIDDEN = ("titan_cli.ai.client", "titan_cli.ai.headless_generator", "titan_cli.external_cli")
FORBIDDEN_NAMES = ("AIClient", "HeadlessGenerator")


def _agent_modules() -> list[Path]:
    """Core agent infrastructure plus every agent shipped by a plugin."""
    found = list((REPO_ROOT / "titan_cli" / "ai" / "agents").rglob("*.py"))
    found += list((REPO_ROOT / "plugins").glob("*/*/agents/*.py"))
    return [path for path in found if path.name != "__pycache__"]


def _imports(path: Path) -> list[str]:
    """Every module and name imported by a file."""
    tree = ast.parse(path.read_text(), filename=str(path))
    names = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
            names.extend(alias.name for alias in node.names)

    return names


def _offenders(path: Path) -> list[str]:
    return [
        name
        for name in _imports(path)
        if any(name.startswith(module) for module in FORBIDDEN) or name in FORBIDDEN_NAMES
    ]


def test_there_are_agents_to_check():
    """A guard that silently checks nothing is worse than no guard."""
    modules = _agent_modules()

    assert len(modules) > 3
    assert any("pr_agent" in path.name for path in modules)


def test_the_guard_detects_a_real_violation():
    """
    Proves the check can fail.

    The router legitimately imports both transports - deciding between them is
    its job. If scanning it finds nothing, the detection is broken and every
    other assertion in this file is passing for the wrong reason.
    """
    router = REPO_ROOT / "titan_cli" / "ai" / "router" / "executor.py"

    assert _offenders(router), "the import scan found nothing where it should find transports"


@pytest.mark.parametrize("path", _agent_modules(), ids=lambda p: p.name)
def test_no_agent_imports_a_transport(path: Path):
    offenders = _offenders(path)

    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} imports {offenders}. An agent must depend only on "
        f"the AIGenerator protocol, or it can no longer run on whichever provider the user "
        f"configured."
    )
