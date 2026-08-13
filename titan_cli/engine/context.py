"""
WorkflowContext - Dependency injection container for workflows.
"""

import warnings
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class WorkflowContext:
    """
    Context container for workflow execution.

    Provides:
    - Dependency injection (clients, services)
    - Shared data storage between steps
    - Textual TUI components
    - Namespace-scoped secret management (`secret_broker`)

    UI Architecture:
        ctx.textual.text     # Textual TUI components
        ctx.textual.panel
        ctx.textual.spacer
        ctx.textual.prompts
    """

    # Namespace-scoped secrets API for the current step, assigned per step by
    # the executor. A step can store/check/delete secrets in its own
    # namespace; there is deliberately no way to read a value back.
    secret_broker: Optional[Any] = None

    # Textual TUI components (for TUI mode)
    textual: Optional[Any] = None

    # Plugin registry
    plugin_manager: Optional[Any] = None

    # TitanConfig instance (for steps that need to persist user preferences)
    titan_config: Optional[Any] = None

    # Service clients (populated by builder)
    ai: Optional[Any] = None
    # AIExecutor - resolves and runs AI calls on the provider the user chose per task
    ai_router: Optional[Any] = None
    git: Optional[Any] = None
    github: Optional[Any] = None
    github_managers: Optional[Any] = None
    jira: Optional[Any] = None
    slack: Optional[Any] = None

    # Workflow metadata (set by executor)
    workflow_name: Optional[str] = None
    current_step: Optional[int] = None
    total_steps: Optional[int] = None

    # Shared data storage between steps
    data: Dict[str, Any] = field(default_factory=dict)

    # Internal state for workflow execution
    _workflow_stack: List[str] = field(default_factory=list)

    # Backing store for the deprecated `secrets` property below. Populated by
    # the builder; both go away once external workflow repos stop reading it.
    _legacy_secrets: Optional[Any] = None

    @property
    def secrets(self) -> Optional[Any]:
        """
        Deprecated: the full SecretManager is being removed from the workflow
        API. Use `ctx.secret_broker` (store/check/delete) instead; code that
        needs a secret's value must go through a use-primitive or session
        factory so the value never crosses into step code. This property
        exists only while external workflow repos migrate, and is deleted
        before the next release — no published version ships it.
        """
        warnings.warn(
            "ctx.secrets is deprecated and will be removed: use "
            "ctx.secret_broker (or a session factory) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._legacy_secrets

    def set(self, key: str, value: Any) -> None:
        """Set shared data."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get shared data."""
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if key exists in shared data."""
        return key in self.data

    def enter_workflow(self, workflow_name: str):
        """
        Track entering a workflow execution to prevent circular dependencies.
        """
        if workflow_name in self._workflow_stack:
            raise ValueError(
                f"Circular workflow dependency detected: {' -> '.join(self._workflow_stack)} -> {workflow_name}"
            )
        self._workflow_stack.append(workflow_name)

    def exit_workflow(self, workflow_name: str):
        """
        Track exiting a workflow execution.
        """
        if self._workflow_stack and self._workflow_stack[-1] == workflow_name:
            self._workflow_stack.pop()
