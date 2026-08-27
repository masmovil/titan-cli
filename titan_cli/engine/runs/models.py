"""Run-scoped request and response models for the workflow run engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from titan_cli.engine.runs.status import RunSessionStatus
from titan_cli.ports.protocol import EngineEvent
from titan_cli.ports.protocol import InteractionRequest
from titan_cli.ports.protocol import PromptRequest
from titan_cli.ports.protocol import RunResult


@dataclass(slots=True)
class PromptResponse:
    """Response submitted by a client for a pending prompt."""

    prompt_id: str
    value: Any


@dataclass(slots=True)
class StartWorkflowRequest:
    """Request to start a workflow run."""

    workflow_name: str
    params: dict[str, Any] = field(default_factory=dict)
    prompt_responses: list[Any] = field(default_factory=list)
    project_path: Optional[str] = None
    interaction_mode: str = "headless"


@dataclass(slots=True)
class SubmitPromptResponseRequest:
    """Request to answer a pending workflow prompt."""

    run_id: str
    prompt_id: str
    value: Any


@dataclass(slots=True)
class SubmitInteractionResponseRequest:
    """Request to answer a pending workflow interaction."""

    run_id: str
    interaction_id: str
    response_type: str
    value: Any = None


@dataclass(slots=True)
class StartWorkflowResponse:
    """Initial response returned when a workflow run starts."""

    run_id: str
    status: RunSessionStatus
    events: list[EngineEvent] = field(default_factory=list)
    pending_prompt: Optional[PromptRequest] = None
    pending_interaction: Optional[InteractionRequest] = None
    result: Optional[RunResult] = None


@dataclass(slots=True)
class WorkflowRunState:
    """Serializable snapshot of a workflow run."""

    run_id: str
    workflow_name: str
    status: RunSessionStatus
    result_message: Optional[str] = None
    events: list[EngineEvent] = field(default_factory=list)
    pending_prompt: Optional[PromptRequest] = None
    pending_interaction: Optional[InteractionRequest] = None
    prompt_history: list[PromptResponse] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    result: Optional[RunResult] = None
