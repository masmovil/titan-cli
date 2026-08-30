"""Architecture guardrails for workflow interaction portability."""

import ast
import inspect
from pathlib import Path

from titan_cli.engine.interaction.base import InteractionPort


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _workflow_step_files() -> list[Path]:
    files = list((REPOSITORY_ROOT / "titan_cli" / "engine" / "steps").rglob("*.py"))
    for plugin_root in (REPOSITORY_ROOT / "plugins").glob("*/"):
        files.extend(plugin_root.glob("**/steps/**/*.py"))
    return sorted(set(files))


def test_workflow_steps_only_call_declared_interaction_capabilities():
    declared = {name for name, value in inspect.getmembers(InteractionPort, callable)}
    undeclared: list[str] = []

    for path in _workflow_step_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Attribute):
                continue
            receiver = node.value
            if not isinstance(receiver.value, ast.Name) or receiver.value.id != "ctx":
                continue
            if receiver.attr not in {"interaction", "textual"}:
                continue
            if node.attr not in declared:
                undeclared.append(f"{path.relative_to(REPOSITORY_ROOT)}:{node.lineno} {node.attr}")

    assert undeclared == [], "Workflow steps use undeclared UI capabilities:\n" + "\n".join(undeclared)


def test_workflow_steps_do_not_import_or_mount_ui_toolkits():
    violations: list[str] = []

    for path in _workflow_step_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                modules = []

            for module in modules:
                if module == "textual" or module.startswith("textual.") or ".ui.tui" in module:
                    violations.append(
                        f"{path.relative_to(REPOSITORY_ROOT)}:{node.lineno} imports {module}"
                    )

            if (
                isinstance(node, ast.Attribute)
                and node.attr in {"mount", "app"}
                and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "ctx"
                and node.value.attr in {"interaction", "textual"}
            ):
                violations.append(
                    f"{path.relative_to(REPOSITORY_ROOT)}:{node.lineno} uses {node.value.attr}.{node.attr}"
                )

    assert violations == [], "Workflow steps depend on UI toolkit details:\n" + "\n".join(violations)
