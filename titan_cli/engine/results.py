"""
Workflow result types for atomic steps.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowResult:
    """Base class for workflow step results."""
    message: str
    success: bool

    def is_success(self) -> bool:
        return self.success

    def is_error(self) -> bool:
        return not self.success and not isinstance(self, Skip)

    def is_skip(self) -> bool:
        return isinstance(self, Skip)


@dataclass(frozen=True)
class Success(WorkflowResult):
    """Step completed successfully."""

    def __init__(self, message: str):
        object.__setattr__(self, 'message', message)
        object.__setattr__(self, 'success', True)


@dataclass(frozen=True)
class Error(WorkflowResult):
    """Step failed, workflow should halt."""

    def __init__(self, message: str):
        object.__setattr__(self, 'message', message)
        object.__setattr__(self, 'success', False)


@dataclass(frozen=True)
class Skip(WorkflowResult):
    """Step skipped (not applicable)."""

    def __init__(self, message: str):
        object.__setattr__(self, 'message', message)
        object.__setattr__(self, 'success', True)  # Skip is not a failure
