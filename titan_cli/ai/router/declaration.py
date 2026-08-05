"""
Self-declaration mechanism for steps that use AI.

`declare_ai_usage` is a decorator any step function - official or
community/third-party plugin - can attach to itself to announce "this step
uses AI" without registering anywhere central. A discovery service can later
scan registered workflows, resolve each step to its callable, and read this
attribute back off the function object. The execution façade reads the same
attribute when a step passes its own function as `policy=`.

Declaring usage (`ai_policy`) is informational only. Whether the step's
runtime behavior actually respects the resolved provider - i.e. whether it
routes through `ctx.ai_router` - is a separate claim, tracked via `enforces`.
A step can declare without enforcing.
"""

from typing import Callable, List, Optional, TypeVar

from .enums import AIProviderType
from .models import AIRoutePolicy

StepFunc = TypeVar("StepFunc", bound=Callable)

# Attribute names used to stash the declaration on the function object.
AI_POLICY_ATTR = "ai_policy"
AI_ENFORCES_ATTR = "ai_enforces"


def declare_ai_usage(
    task: str,
    preferred: Optional[List[AIProviderType]] = None,
    enforces: bool = False,
) -> Callable[[StepFunc], StepFunc]:
    """
    Attach an `AIRoutePolicy` to a step function so discovery can find it.

    Args:
        task: Routing/preference-persistence key. Reuse an `AITask` member
            for official plugins; community plugins may pass their own string.
        preferred: Provider types to try first, in order, when the user has
            not configured a preference for this task. This list is also the
            set of provider types the step's code can execute - preference UIs
            offer the user nothing outside it - so only declare what the step
            can actually drive.
        enforces: Set True only if the step's own code actually routes through
            `ctx.ai_router` at runtime, not just informational
            self-declaration. Defaults to False so undeclared/unmigrated steps
            never overstate what they guarantee.

    Returns:
        A decorator that stashes the policy on the function and returns it
        unchanged (no wrapping - the function still runs exactly as before).
    """

    def decorator(func: StepFunc) -> StepFunc:
        setattr(
            func,
            AI_POLICY_ATTR,
            AIRoutePolicy(task=task, preferred=preferred or []),
        )
        setattr(func, AI_ENFORCES_ATTR, enforces)
        return func

    return decorator


def get_declared_ai_policy(func: Callable) -> Optional[AIRoutePolicy]:
    """Read back a step function's declared `AIRoutePolicy`, if any."""
    return getattr(func, AI_POLICY_ATTR, None)


def declared_ai_usage_enforces(func: Callable) -> bool:
    """Whether a step's own code actually enforces its declared policy."""
    return bool(getattr(func, AI_ENFORCES_ATTR, False))


__all__ = [
    "declare_ai_usage",
    "get_declared_ai_policy",
    "declared_ai_usage_enforces",
]
