"""
WorkflowContext - Dependency injection container for workflows.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from titan_cli.core.secrets import SecretManager
from .ui_container import UIComponents
from .views_container import UIViews


@dataclass
class WorkflowContext:
    """
    Context container for workflow execution.

    Provides:
    - Dependency injection (clients, services)
    - Shared data storage between steps
    - UI components (organized by level)
    - Access to secrets

    UI Architecture:
        ctx.ui.text      # Basic components (Rich wrappers)
        ctx.ui.panel
        ctx.ui.table
        ctx.ui.spacer

        ctx.views.prompts  # Composed views
        ctx.views.menu
    """

    # Core dependencies
    secrets: SecretManager

    # UI (two-level architecture)
    ui: Optional[UIComponents] = None
    views: Optional[UIViews] = None

    # Plugin registry
    plugin_manager: Optional[Any] = None

    # Service clients (populated by builder)
    ai: Optional[Any] = None
    git: Optional[Any] = None
    github: Optional[Any] = None
    jira: Optional[Any] = None

    # Workflow metadata (set by executor)
    workflow_name: Optional[str] = None
    current_step: Optional[int] = None
    total_steps: Optional[int] = None

    # Shared data storage between steps
    data: Dict[str, Any] = field(default_factory=dict)

    # Internal state for workflow execution
    _workflow_stack: List[str] = field(default_factory=list)

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
