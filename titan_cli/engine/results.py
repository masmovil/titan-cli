"""
Workflow result types for atomic steps.
"""

from typing import Any, Optional, Union
from dataclasses import dataclass


@dataclass(frozen=True)
class Success:
    """
    Step completed successfully.
    
    Attributes:
        message: Success message (optional)
        metadata: Metadata to auto-merge into ctx.data
    
    Examples:
        >>> return Success("User validated")
        >>> return Success("PR created", metadata={"pr_number": 123})
    """
    message: str = ""
    metadata: Optional[dict[str, Any]] = None

@dataclass(frozen=True)
class Error:
    """
    Step failed with an error.
    
    Attributes:
        message: Error message (required)
        code: Error code (default: 1)
        exception: Original exception if available
        recoverable: Whether error can be recovered from
    
    Examples:
        >>> return Error("GitHub not available")
        >>> return Error("API rate limit", code=429, recoverable=True)
        >>> return Error("Connection failed", exception=exc)
    """
    message: str
    code: int = 1
    exception: Optional[Exception] = None
    recoverable: bool = False


@dataclass(frozen=True)
class Skip:
    """
    Step was skipped (not applicable).

    Use when a step doesn't need to run:
    - Optional tool not configured
    - Condition not met
    - User chose to skip

    Attributes:
        message: Why the step was skipped (required)
        metadata: Metadata to auto-merge into ctx.data
        silent: If True, don't show warning message (for expected skips)

    Examples:
        >>> if not ctx.ai:
        >>>     return Skip("AI not configured")
        >>> return Skip("No changes detected", metadata={"clean": True})
        >>> return Skip("PR title already provided", silent=True)  # No warning shown
    """
    message: str
    metadata: Optional[dict[str, Any]] = None
    silent: bool = False


# Type alias for workflow results
WorkflowResult = Union[Success, Error, Skip]


# ============================================================================
# Helper functions for type checking
# ============================================================================

def is_success(result: WorkflowResult) -> bool:
    """Check if result is Success."""
    return isinstance(result, Success)


def is_error(result: WorkflowResult) -> bool:
    """Check if result is Error."""
    return isinstance(result, Error)


def is_skip(result: WorkflowResult) -> bool:
    """Check if result is Skip."""
    return isinstance(result, Skip)
