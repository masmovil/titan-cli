"""Internal run session state enums."""

from enum import StrEnum


class RunSessionStatus(StrEnum):
    """Lifecycle states for the in-process run session."""

    CREATED = "created"
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_PROMPT = "waiting_for_prompt"
    WAITING_FOR_INTERACTION = "waiting_for_interaction"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_SESSION_STATUSES = frozenset(
    {
        RunSessionStatus.COMPLETED,
        RunSessionStatus.FAILED,
        RunSessionStatus.CANCELLED,
    }
)
