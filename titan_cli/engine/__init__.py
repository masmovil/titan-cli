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

from .results import WorkflowResult, Success, Error, Skip
from .context import WorkflowContext
from .builder import WorkflowContextBuilder
from .workflow import BaseWorkflow, StepFunction

__all__ = [
    "WorkflowResult",
    "Success",
    "Error",
    "Skip",
    "WorkflowContext",
    "WorkflowContextBuilder",
    "BaseWorkflow",
    "StepFunction",
]
