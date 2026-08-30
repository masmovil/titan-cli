"""Titan protocol dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional


class EventType(StrEnum):
    """Supported outbound event names for the V1 protocol."""

    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    OUTPUT_EMITTED = "output_emitted"
    PROMPT_REQUESTED = "prompt_requested"
    PROMPT_ANSWERED = "prompt_answered"
    INTERACTION_REQUESTED = "interaction_requested"
    INTERACTION_ANSWERED = "interaction_answered"
    STEP_FINISHED = "step_finished"
    STEP_FAILED = "step_failed"
    STEP_SKIPPED = "step_skipped"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    RUN_RESULT_EMITTED = "run_result_emitted"


class CommandType(StrEnum):
    """Supported inbound command names for the V1 protocol."""

    SUBMIT_PROMPT_RESPONSE = "submit_prompt_response"
    SUBMIT_INTERACTION_RESPONSE = "submit_interaction_response"
    CANCEL_RUN = "cancel_run"


class PromptType(StrEnum):
    """Prompt kinds defined by the V1 protocol."""

    CONFIRM = "confirm"
    TEXT = "text"
    MULTILINE = "multiline"
    SELECT_ONE = "select_one"
    MULTI_SELECT = "multi_select"
    SECRET = "secret"


class InteractionType(StrEnum):
    """Interaction kinds defined by the first rich interaction slice."""

    OPTION_LIST = "option_list"
    ITEM_REVIEW = "item_review"
    ACTION_LIST = "action_list"
    EDITABLE_TEXT = "editable_text"
    BATCH_PROGRESS = "batch_progress"
    EXTERNAL_CLI_SESSION = "external_cli_session"


class OutputFormat(StrEnum):
    """Semantic output formats defined by the V1 protocol."""

    TEXT = "text"
    MARKDOWN = "markdown"
    TABLE = "table"
    DIFF = "diff"
    PROGRESS = "progress"
    STRUCTURED_SUMMARY = "structured_summary"
    JSON = "json"


class DiffPresentationType(StrEnum):
    """Diff presentation variants shared across adapters."""

    SUMMARY = "summary"
    FOCUSED_HUNK = "focused_hunk"
    FULL_PATCH = "full_patch"


class ContentBlockType(StrEnum):
    """Reusable semantic content block types shared by outputs and interactions."""

    TEXT = "text"
    MARKDOWN = "markdown"
    DIFF = "diff"
    STRUCTURED_SUMMARY = "structured_summary"


class ContentBlockVariant(StrEnum):
    """Visual-semantic variant shared by reusable content blocks."""

    DEFAULT = "default"
    SUCCESS = "success"
    MUTED = "muted"
    WARNING = "warning"
    ERROR = "error"


class RunStatus(StrEnum):
    """Terminal run states supported by V1."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStepStatus(StrEnum):
    """Terminal step states supported by V1."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class StepRef:
    """Shared step identity used across step-scoped protocol messages."""

    step_id: str
    step_name: str
    step_index: int


@dataclass(slots=True)
class OutputPayload:
    """Semantic output emitted by the engine."""

    format: OutputFormat
    content: str
    title: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptOption:
    """Option used by selection-oriented prompt types."""

    id: str
    label: str
    value: Any = None
    description: Optional[str] = None


@dataclass(slots=True)
class InteractionOption:
    """Option used by richer interaction surfaces."""

    id: str
    label: str
    value: Any = None
    description: Optional[str] = None
    badges: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InteractionAction:
    """Action available from an interaction surface."""

    id: str
    label: str
    description: Optional[str] = None
    variant: str = "default"


@dataclass(slots=True)
class ContentBlock:
    """Reusable semantic content block renderable by any adapter."""

    type: ContentBlockType
    content: str
    title: Optional[str] = None
    variant: ContentBlockVariant = ContentBlockVariant.DEFAULT
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ItemReviewItem:
    """Single reviewable item shown inside the item-review interaction."""

    id: str
    title: str
    status: Optional[str] = None
    content_blocks: list[ContentBlock] = field(default_factory=list)
    editable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ItemReviewEditState:
    """Optional editing affordance shared by item-review items."""

    enabled: bool
    label: Optional[str] = None
    initial_value: Optional[str] = None


@dataclass(slots=True)
class ItemReviewState:
    """Structured state for the first portable item-review interaction slice."""

    review_id: str
    items: list[ItemReviewItem] = field(default_factory=list)
    initial_index: int = 0
    allowed_actions: list[str] = field(default_factory=list)
    edit: Optional[ItemReviewEditState] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ItemReviewDecision:
    """Decision made by the adapter for one reviewed item."""

    item_id: str
    action: str
    content: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ItemReviewResponsePayload:
    """Final aggregated response returned after an item-review session."""

    items: list[ItemReviewDecision] = field(default_factory=list)
    exit_requested: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InteractionRequest:
    """Structured rich interaction request exposed through the protocol."""

    interaction_id: str
    interaction_type: InteractionType
    message: Optional[str] = None
    state: dict[str, Any] = field(default_factory=dict)
    actions: list[InteractionAction] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptRequest:
    """Structured prompt request exposed through the V1 protocol."""

    prompt_id: str
    prompt_type: PromptType
    message: str
    default: Any = None
    required: bool = True
    options: list[PromptOption] = field(default_factory=list)


@dataclass(slots=True)
class EngineEvent:
    """Outbound event emitted by a live workflow run."""

    type: EventType
    run_id: str
    sequence: int
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class EngineCommand:
    """Inbound command sent by an adapter to a live workflow run."""

    type: CommandType
    run_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class RunStepResult:
    """Terminal summary for a single step in a run result."""

    id: str
    title: str
    status: RunStepStatus
    plugin: Optional[str] = None
    error: Optional[str] = None
    outputs: list[OutputPayload] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunResult:
    """Terminal-only run snapshot returned by the V1 protocol."""

    run_id: str
    workflow_name: str
    status: RunStatus
    steps: list[RunStepResult] = field(default_factory=list)
    result: Optional[OutputPayload] = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
