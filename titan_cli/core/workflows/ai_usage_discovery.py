"""
Discovery service for steps that declare AI usage across registered workflows.

Scans every workflow the `WorkflowRegistry` knows about, resolves each step's
`(plugin, step)` reference to its actual callable using the same resolution
rules `WorkflowExecutor` applies at runtime (core/project/user virtual
plugins vs. real plugin registrations), and reads back any policy attached
via `declare_ai_usage`. A workflow step can override specific fields of a
step's default policy via a `params.ai:` block in its own YAML entry.

Lives in `core.workflows` rather than `titan_cli.ai.router` because it
depends on both `WorkflowRegistry` and `PluginRegistry` - the router package
sits below those in the dependency graph and must not import them back.
"""

from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Set

from titan_cli.ai.router.declaration import declared_ai_usage_enforces, get_declared_ai_policy
from titan_cli.ai.router.enums import AIProviderType
from titan_cli.ai.router.models import AIRoutePolicy
from titan_cli.core.plugins.plugin_registry import PluginRegistry

from .workflow_registry import ParsedWorkflow, WorkflowRegistry


@dataclass
class DiscoveredAIStep:
    """One workflow step found to declare AI usage."""

    workflow_name: str
    step_id: str
    step_name: str
    plugin: str
    step: str
    policy: AIRoutePolicy
    enforces: bool
    overridden: bool


@dataclass
class DiscoveredWorkflowAIUsage:
    """All AI-declaring steps found within a single workflow (including nested workflows)."""

    workflow_name: str
    steps: List[DiscoveredAIStep]


class AIUsageDiscoveryService:
    """Finds every step, in every registered workflow, that declares AI usage."""

    def __init__(
        self,
        workflow_registry: WorkflowRegistry,
        plugin_registry: PluginRegistry,
        core_steps: Dict[str, Callable],
    ):
        self._workflow_registry = workflow_registry
        self._plugin_registry = plugin_registry
        self._core_steps = core_steps

    def discover_all(self) -> List[DiscoveredWorkflowAIUsage]:
        """Discover AI-declaring steps across every workflow the registry can list."""
        results: List[DiscoveredWorkflowAIUsage] = []
        for info in self._workflow_registry.discover():
            usage = self.discover_workflow(info.name)
            if usage and usage.steps:
                results.append(usage)
        return results

    def discover_workflow(self, workflow_name: str) -> Optional[DiscoveredWorkflowAIUsage]:
        """Discover AI-declaring steps within a single workflow, by name."""
        try:
            workflow = self._workflow_registry.get_workflow(workflow_name)
        except Exception:
            return None
        if not workflow:
            return None

        steps = self._discover_steps(workflow, seen_workflows={workflow_name})
        return DiscoveredWorkflowAIUsage(workflow_name=workflow.name, steps=steps)

    def _discover_steps(self, workflow: ParsedWorkflow, seen_workflows: Set[str]) -> List[DiscoveredAIStep]:
        discovered: List[DiscoveredAIStep] = []

        for step_data in workflow.steps:
            plugin = step_data.get("plugin")
            step_name = step_data.get("step")
            nested_workflow_name = step_data.get("workflow")

            if nested_workflow_name:
                if nested_workflow_name in seen_workflows:
                    continue
                try:
                    nested_workflow = self._workflow_registry.get_workflow(nested_workflow_name)
                except Exception:
                    nested_workflow = None
                if nested_workflow:
                    discovered.extend(
                        self._discover_steps(nested_workflow, seen_workflows | {nested_workflow_name})
                    )
                continue

            if not plugin or not step_name:
                continue

            func = self._resolve_step_func(plugin, step_name)
            if func is None:
                continue

            policy = get_declared_ai_policy(func)
            if policy is None:
                continue

            overridden = False
            step_params = step_data.get("params")
            ai_override = step_params.get("ai") if isinstance(step_params, dict) else None
            if isinstance(ai_override, dict):
                policy = self._apply_override(policy, ai_override)
                overridden = True

            discovered.append(
                DiscoveredAIStep(
                    workflow_name=workflow.name,
                    step_id=step_data.get("id") or f"{plugin}_{step_name}",
                    step_name=step_data.get("name") or step_data.get("id") or step_name,
                    plugin=plugin,
                    step=step_name,
                    policy=policy,
                    enforces=declared_ai_usage_enforces(func),
                    overridden=overridden,
                )
            )

        return discovered

    def _resolve_step_func(self, plugin: str, step_name: str) -> Optional[Callable]:
        if plugin == "core":
            return self._core_steps.get(step_name)
        if plugin == "project":
            return self._workflow_registry.get_project_step(step_name)
        if plugin == "user":
            return self._workflow_registry.get_user_step(step_name)

        plugin_instance = self._plugin_registry.get_plugin(plugin)
        if not plugin_instance:
            return None
        return plugin_instance.get_steps().get(step_name)

    def _apply_override(self, policy: AIRoutePolicy, override: dict) -> AIRoutePolicy:
        """Return a copy of `policy` with fields replaced by a per-invocation `params.ai:` override."""
        kwargs = {}
        if "task" in override:
            kwargs["task"] = override["task"]
        if "preferred" in override:
            kwargs["preferred"] = [AIProviderType(p) for p in override["preferred"]]
        return replace(policy, **kwargs)


__all__ = [
    "AIUsageDiscoveryService",
    "DiscoveredAIStep",
    "DiscoveredWorkflowAIUsage",
]
