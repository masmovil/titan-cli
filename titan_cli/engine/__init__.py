"""
Titan CLI Workflow Engine

This module provides the execution engine for composing and running workflows
using the Atomic Steps Pattern.

Core components:
- WorkflowResult types (Success, Error, Skip)
- WorkflowContext for dependency injection
- WorkflowContextBuilder for fluent API
- BaseWorkflow for orchestration
"""

from .results import (
    WorkflowResult,
    Success,
    Error,
    Skip,
    is_success,
    is_error,
    is_skip,
)
from .context import WorkflowContext
from .builder import WorkflowContextBuilder
from .workflow import BaseWorkflow, StepFunction
from .ui_container import UIComponents # New import
from .views_container import UIViews # New import

__all__ = [
    # Result types
    "WorkflowResult",
    "Success",
    "Error",
    "Skip",
    # Helper functions
    "is_success",
    "is_error",
    "is_skip",
    # Context & builder
    "WorkflowContext",
    "WorkflowContextBuilder",
    # UI containers
    "UIComponents",
    "UIViews",
    # Workflow
    "BaseWorkflow",
    "StepFunction",
]
