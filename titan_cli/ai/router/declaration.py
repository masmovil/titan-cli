"""
Self-declaration mechanism for steps that use AI.

`declare_ai_usage` is a decorator any step function - official or
community/third-party plugin - can attach to itself to announce "this step
uses AI" without registering anywhere central. A discovery service can later
scan registered workflows, resolve each step to its callable, and read this
attribute back off the function object. The execution façade reads the same
attribute when a step passes its own function as `policy=`.

This declaration is the CONTRACT for any AI-using step:

- `task` names the kind of work, and is the key users configure a provider
  for. Reuse an `AITask` member when one fits; otherwise pick a stable string.
- `executes` lists the provider types the step's code can actually run. It is
  what preference UIs offer the user for this task - never declare a type the
  code can't drive, and never drive a type that isn't declared.
- `preferred` is the default try-order when the user configured nothing. It
  must be a subset of `executes`; when omitted it defaults to `executes` in
  the given order. A step whose "can run" and "should default to" differ
  (e.g. it can use a headless CLI but a remote connection is the sensible
  default) declares both.
- `enforces` states whether the step's code actually routes through
  `ctx.ai_router` at runtime. Declaring without enforcing is allowed (the
  step becomes visible in configuration UIs with a "may not honor this"
  warning) but enforcing is what makes the user's choice real.

Declaring usage (`ai_policy`) is informational only. Whether the step's
runtime behavior actually respects the resolved provider is the separate
`enforces` claim - a step can declare without enforcing.
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
    executes: Optional[List[AIProviderType]] = None,
    preferred: Optional[List[AIProviderType]] = None,
    enforces: bool = False,
) -> Callable[[StepFunc], StepFunc]:
    """
    Attach an `AIRoutePolicy` to a step function so discovery can find it.

    Args:
        task: Routing/preference-persistence key. Reuse an `AITask` member
            for official plugins; community plugins may pass their own string.
        executes: Provider types this step's code can actually run. This is
            the set preference UIs offer the user for the task. Defaults to
            `preferred` when omitted, so a step whose default order and
            executable set coincide declares just one list.
        preferred: Provider types to try first, in order, when the user has
            not configured a preference for this task. Must be a subset of
            `executes`; defaults to `executes` in the given order.
        enforces: Set True only if the step's own code actually routes through
            `ctx.ai_router` at runtime, not just informational
            self-declaration. Defaults to False so undeclared/unmigrated steps
            never overstate what they guarantee.

    Raises:
        ValueError: If `preferred` names a provider type missing from
            `executes` - a step must never default to something it can't run.

    Returns:
        A decorator that stashes the policy on the function and returns it
        unchanged (no wrapping - the function still runs exactly as before).
    """
    executes_list = list(executes) if executes is not None else list(preferred or [])
    preferred_list = list(preferred) if preferred is not None else list(executes_list)

    invalid = [p for p in preferred_list if p not in executes_list]
    if invalid:
        raise ValueError(
            f"declare_ai_usage(task={task!r}): preferred contains provider types "
            f"not in executes: {[str(p) for p in invalid]}. A step must never "
            f"default to a provider type its code can't run."
        )

    def decorator(func: StepFunc) -> StepFunc:
        setattr(
            func,
            AI_POLICY_ATTR,
            AIRoutePolicy(task=task, executes=executes_list, preferred=preferred_list),
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
