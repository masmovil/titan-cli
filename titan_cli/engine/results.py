"""
Workflow result types for atomic steps.
"""

from typing import Any, Optional, Union
from dataclasses import dataclass


def _reject_secret_metadata(result_type: str, metadata: Optional[dict]) -> None:
    """
    Result metadata is auto-merged into ctx.data and may end up in logs, so a
    raw secret string in it is a leak the moment the step returns. Raising at
    construction points the traceback at the offending step. Opaque carriers
    (SensitiveValue, SecretRef) are allowed — they are the sanctioned way for
    sensitive material to travel.
    """
    if not metadata:
        return
    # Imported here: engine must stay importable without dragging the whole
    # security package (and its keyring backend) in at module-import time.
    from titan_cli.core.security import SecretLeakError, find_secret_in

    found = find_secret_in(metadata)
    if found:
        raise SecretLeakError(
            f"{result_type} metadata carries a secret value at '{found}'. "
            "Metadata is merged into ctx.data and may be logged; wrap derived "
            "sensitive material in SensitiveValue or keep it out of the result."
        )


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

    def __post_init__(self):
        _reject_secret_metadata("Success", self.metadata)

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

    Examples:
        >>> if not ctx.ai:
        >>>     return Skip("AI not configured")
        >>> return Skip("No changes detected", metadata={"clean": True})
        >>> return Skip("PR title already provided")
    """
    message: str
    metadata: Optional[dict[str, Any]] = None

    def __post_init__(self):
        _reject_secret_metadata("Skip", self.metadata)


@dataclass(frozen=True)
class Exit:
    """
    Exit the entire workflow early (not an error).

    Use when the workflow should stop because it's not needed:
    - No changes to commit
    - Nothing to do
    - Preconditions not met

    This exits the ENTIRE workflow, not just the current step.

    Attributes:
        message: Why the workflow is exiting (required)
        metadata: Metadata to auto-merge into ctx.data

    Examples:
        >>> if not has_changes:
        >>>     return Exit("No changes to commit")
        >>> return Exit("Already up to date", metadata={"status": "clean"})
    """
    message: str
    metadata: Optional[dict[str, Any]] = None

    def __post_init__(self):
        _reject_secret_metadata("Exit", self.metadata)


# Type alias for workflow results
WorkflowResult = Union[Success, Error, Skip, Exit]


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


def is_exit(result: WorkflowResult) -> bool:
    """Check if result is Exit."""
    return isinstance(result, Exit)
