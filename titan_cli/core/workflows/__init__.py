# titan_cli/core/workflows/__init__.py
"""
Workflow management system.

Similar to plugins system, but for workflows:
- WorkflowRegistry: Discover and manage workflows
- WorkflowSource: Load from multiple sources (project, user, system, plugins)
"""

from .workflow_registry import WorkflowRegistry, ParsedWorkflow
from .workflow_sources import WorkflowInfo
from .workflow_exceptions import WorkflowNotFoundError, WorkflowExecutionError
from .project_step_source import ProjectStepSource

__all__ = [
    "WorkflowRegistry",
    "WorkflowInfo",
    "ParsedWorkflow",
    "WorkflowNotFoundError",
    "WorkflowExecutionError",
    "ProjectStepSource",
]
