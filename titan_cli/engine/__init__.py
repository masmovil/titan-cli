"""
Titan CLI Workflow Engine

This module provides the execution engine for composing and running workflows
using the Atomic Steps Pattern.

Core components:
- WorkflowResult types (Success, Error, Skip, Exit)
- WorkflowContext for dependency injection
- WorkflowContextBuilder for fluent API
- WorkflowExecutor for executing YAML workflows (see workflow_executor.py)
"""

from .results import (
    WorkflowResult,
    Success,
    Error,
    Skip,
    Exit,
    is_success,
    is_error,
    is_skip,
    is_exit,
)
from .context import WorkflowContext
from .builder import WorkflowContextBuilder
from .option_item import OptionItem

__all__ = [
    # Result types
    "WorkflowResult",
    "Success",
    "Error",
    "Skip",
    "Exit",
    # Helper functions
    "is_success",
    "is_error",
    "is_skip",
    "is_exit",
    # Context & builder
    "WorkflowContext",
    "WorkflowContextBuilder",
    # Prompt option list
    "OptionItem",
]
