"""
AI execution routing layer.

Unified decision + execution layer for AI requests across remote providers
(AIClient/LiteLLM), headless CLI adapters, and interactive CLIs. It is a
cross-cutting policy engine, not a plugin's external-service client, so it does
not follow the plugin 5-layer pattern - but its results mirror ClientResult's
success/error shape so pattern-matching habits transfer.

`AIExecutor` is the entry point steps use (`ctx.ai_router`); the availability
checker, resolver and declaration decorator are its parts.
"""

from .availability import AIAvailabilityChecker, AIProviderAvailability
from .declaration import declare_ai_usage, declared_ai_usage_enforces, get_declared_ai_policy
from .enums import AIProviderType, AITask
from .executor import AIExecutor
from .models import (
    AIExecutionError,
    AIExecutionResult,
    AIExecutionSuccess,
    AIRouteDecision,
    AIRoutePolicy,
)
from .resolver import AIRouteNeedsInput, AIRouteResolution, AIRouteResolver

__all__ = [
    "AITask",
    "AIProviderType",
    "AIRoutePolicy",
    "AIRouteDecision",
    "AIExecutionSuccess",
    "AIExecutionError",
    "AIExecutionResult",
    "AIExecutor",
    "AIAvailabilityChecker",
    "AIProviderAvailability",
    "AIRouteResolver",
    "AIRouteNeedsInput",
    "AIRouteResolution",
    "declare_ai_usage",
    "get_declared_ai_policy",
    "declared_ai_usage_enforces",
]
