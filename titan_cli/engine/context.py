"""Workflow execution context with backwards-compatible UI bindings."""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from titan_cli.engine.interaction.headless import HeadlessInteractionPort
from titan_cli.engine.interaction.textual import TextualInteractionPort

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

    # Legacy Textual TUI components (for compatibility during refactor)
    textual: Optional[Any] = None
    interaction: Optional[Any] = None

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
    docker: Optional[Any] = None

    # Workflow metadata (set by executor)
    workflow_name: Optional[str] = None
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    current_step_id: Optional[str] = None
    current_step_name: Optional[str] = None
    current_step_plugin: Optional[str] = None
    current_step_kind: Optional[str] = None

    # Shared data storage between steps
    data: Dict[str, Any] = field(default_factory=dict)

    # Internal state for workflow execution
    _workflow_stack: List[str] = field(default_factory=list)

    def __setattr__(self, name: str, value: Any) -> None:
        """Keep legacy `textual` and newer `interaction` bindings in sync."""
        object.__setattr__(self, name, value)

        if name == "textual" and value is not None:
            interaction = getattr(self, "interaction", None)
            if interaction is None or isinstance(interaction, HeadlessInteractionPort):
                object.__setattr__(self, "interaction", TextualInteractionPort(value))
        elif name == "interaction" and value is not None and getattr(self, "textual", None) is None:
            legacy = getattr(value, "legacy", None)
            if legacy is not None:
                object.__setattr__(self, "textual", legacy)

    def __post_init__(self) -> None:
        """Normalize legacy and new interaction wiring."""
        if self.interaction is None:
            if self.textual is not None:
                self.interaction = TextualInteractionPort(self.textual)
            else:
                self.interaction = HeadlessInteractionPort()
        elif self.textual is None and hasattr(self.interaction, "legacy"):
            self.textual = self.interaction.legacy

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
