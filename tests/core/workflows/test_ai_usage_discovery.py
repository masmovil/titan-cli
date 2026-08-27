"""Tests for AIUsageDiscoveryService."""

from unittest.mock import MagicMock

from titan_cli.ai.router import AIProviderType, AITask, declare_ai_usage
from titan_cli.core.workflows.ai_usage_discovery import AIUsageDiscoveryService
from titan_cli.core.workflows.workflow_registry import ParsedWorkflow


@declare_ai_usage(task=AITask.COMMIT_MESSAGE, preferred=[AIProviderType.REMOTE], enforces=True)
def core_step():
    return None


@declare_ai_usage(task=AITask.PR_DESCRIPTION, preferred=[AIProviderType.REMOTE])
def plugin_step():
    return None


def undeclared_step():
    return None


def _workflow(name, steps):
    return ParsedWorkflow(name=name, description="", source="test", steps=steps, params={})


def _service(workflows, plugin_steps=None, core_steps=None):
    """A discovery service over an in-memory set of workflows and step callables."""
    registry = MagicMock()
    registry.discover.return_value = [MagicMock(name=name) for name in workflows]
    # MagicMock(name=...) sets the mock's repr, not an attribute - set it explicitly.
    for info, name in zip(registry.discover.return_value, workflows):
        info.name = name
    registry.get_workflow.side_effect = lambda name: workflows.get(name)

    plugin_registry = MagicMock()
    plugin = MagicMock()
    plugin.get_steps.return_value = plugin_steps or {}
    plugin_registry.get_plugin.side_effect = lambda name: plugin if plugin_steps else None

    return AIUsageDiscoveryService(
        workflow_registry=registry,
        plugin_registry=plugin_registry,
        core_steps=core_steps if core_steps is not None else {"core_step": core_step},
    )


def test_discovers_a_core_step_with_its_declared_policy():
    workflows = {
        "Commit": _workflow("Commit", [{"plugin": "core", "step": "core_step", "id": "gen"}])
    }

    usage = _service(workflows).discover_workflow("Commit")

    assert len(usage.steps) == 1
    found = usage.steps[0]
    assert found.policy.task == AITask.COMMIT_MESSAGE
    assert found.policy.preferred == [AIProviderType.REMOTE]
    assert found.enforces is True
    assert found.plugin == "core"
    assert found.step_id == "gen"


def test_discovers_a_real_plugin_step():
    workflows = {"PR": _workflow("PR", [{"plugin": "github", "step": "pr_step"}])}

    usage = _service(workflows, plugin_steps={"pr_step": plugin_step}).discover_workflow("PR")

    assert [s.policy.task for s in usage.steps] == [AITask.PR_DESCRIPTION]
    # A step that only declares must not claim it enforces.
    assert usage.steps[0].enforces is False


def test_step_without_a_declaration_is_ignored():
    workflows = {
        "Plain": _workflow("Plain", [{"plugin": "core", "step": "undeclared"}])
    }

    usage = _service(workflows, core_steps={"undeclared": undeclared_step}).discover_workflow("Plain")

    assert usage.steps == []


def test_unresolvable_step_is_ignored():
    workflows = {"Ghost": _workflow("Ghost", [{"plugin": "core", "step": "missing"}])}

    usage = _service(workflows, core_steps={}).discover_workflow("Ghost")

    assert usage.steps == []


def test_recurses_into_nested_workflows():
    workflows = {
        "Outer": _workflow("Outer", [{"workflow": "Inner"}]),
        "Inner": _workflow("Inner", [{"plugin": "core", "step": "core_step"}]),
    }

    usage = _service(workflows).discover_workflow("Outer")

    assert [s.policy.task for s in usage.steps] == [AITask.COMMIT_MESSAGE]
    # The step keeps the name of the workflow that actually declares it.
    assert usage.steps[0].workflow_name == "Inner"


def test_cycle_between_workflows_terminates():
    workflows = {
        "A": _workflow("A", [{"workflow": "B"}, {"plugin": "core", "step": "core_step"}]),
        "B": _workflow("B", [{"workflow": "A"}]),
    }

    usage = _service(workflows).discover_workflow("A")

    assert len(usage.steps) == 1


def test_diamond_reference_traverses_shared_workflow_once():
    """A nested workflow reachable via two paths must not duplicate its steps."""
    workflows = {
        "Top": _workflow("Top", [{"workflow": "Left"}, {"workflow": "Right"}]),
        "Left": _workflow("Left", [{"workflow": "Shared"}]),
        "Right": _workflow("Right", [{"workflow": "Shared"}]),
        "Shared": _workflow("Shared", [{"plugin": "core", "step": "core_step"}]),
    }

    usage = _service(workflows).discover_workflow("Top")

    assert len(usage.steps) == 1


def test_params_ai_block_in_yaml_is_ignored():
    """The declaration is the only source of a step's policy."""
    workflows = {
        "Commit": _workflow(
            "Commit",
            [
                {
                    "plugin": "core",
                    "step": "core_step",
                    "params": {"ai": {"task": "something_else", "preferred": ["cli_headless"]}},
                }
            ],
        )
    }

    usage = _service(workflows).discover_workflow("Commit")

    assert usage.steps[0].policy.task == AITask.COMMIT_MESSAGE
    assert usage.steps[0].policy.preferred == [AIProviderType.REMOTE]


def test_discover_all_skips_workflows_without_ai_steps():
    workflows = {
        "WithAI": _workflow("WithAI", [{"plugin": "core", "step": "core_step"}]),
        "WithoutAI": _workflow("WithoutAI", [{"plugin": "core", "step": "missing"}]),
    }

    usages = _service(workflows).discover_all()

    assert [u.workflow_name for u in usages] == ["WithAI"]


def test_unknown_workflow_returns_none():
    assert _service({}).discover_workflow("Nope") is None


def test_registry_failure_returns_none():
    service = _service({})
    service._workflow_registry.get_workflow.side_effect = RuntimeError("bad YAML")

    assert service.discover_workflow("Broken") is None
