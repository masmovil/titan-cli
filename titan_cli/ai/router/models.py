"""
Data models for the AI execution routing layer.

Policy/decision/result shapes. `AIExecutionResult` mirrors `ClientResult`'s
success/error shape (titan_cli/core/result.py) so existing
ClientSuccess/ClientError pattern-matching habits transfer, but it is its own
type, not a subclass or alias of ClientResult.
"""

from dataclasses import dataclass, field
from typing import Generic, List, Optional, TypeVar

from .enums import AIProviderType

T = TypeVar("T")


@dataclass
class AIRoutePolicy:
    """
    A step's declared routing policy.

    `task` is a plain string (not `AITask`) so community plugins can use their
    own task identifiers as routing/preference-persistence keys - see `AITask`
    in `enums.py` for the recommended vocabulary official plugins should
    reuse. `task` is never sent to the model; only the prompt is.

    `preferred` carries two meanings at once, deliberately: it is the order
    provider types are tried in when the user has not configured anything, and
    it is the set of provider types this step's code can actually execute.
    Preference UIs only offer the user what a step declares here, so never
    declare a provider type the step cannot drive.
    """

    task: str
    preferred: List[AIProviderType] = field(default_factory=list)


@dataclass
class AIRouteDecision:
    """The provider the router resolved a request to, and why."""

    provider: AIProviderType
    cli: Optional[str] = None
    connection_id: Optional[str] = None
    reason: str = ""


@dataclass
class AIExecutionSuccess(Generic[T]):
    """Successful AI execution result. Mirrors `ClientSuccess`'s shape."""

    decision: AIRouteDecision
    data: T
    message: str = ""


@dataclass
class AIExecutionError:
    """
    Failed AI execution result. Mirrors `ClientError`'s shape.

    `decision` may still be set (e.g. a provider was chosen but its
    execution failed, as opposed to no compatible provider being found).
    """

    error_message: str
    error_code: Optional[str] = None
    log_level: str = "error"
    details: Optional[dict] = None
    decision: Optional[AIRouteDecision] = None


# Usage: AIExecutionResult[str], AIExecutionResult[HeadlessResponse], etc.
AIExecutionResult = AIExecutionSuccess[T] | AIExecutionError


__all__ = [
    "AIRoutePolicy",
    "AIRouteDecision",
    "AIExecutionSuccess",
    "AIExecutionError",
    "AIExecutionResult",
]
