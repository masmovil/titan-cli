"""Run semantics for the workflow engine (sessions, events, projection, service)."""

from titan_cli.engine.runs.event_stream import RunEventStream
from titan_cli.engine.runs.interaction_port import (
    InteractionRequestedError,
    PromptRequestedError,
    RunInteractionPort,
)
from titan_cli.engine.runs.models import (
    PromptResponse,
    StartWorkflowRequest,
    StartWorkflowResponse,
    SubmitInteractionResponseRequest,
    SubmitPromptResponseRequest,
    WorkflowRunState,
)
from titan_cli.engine.runs.projection import build_run_result, result_for_session
from titan_cli.engine.runs.service import WorkflowRunService
from titan_cli.engine.runs.session import RunSession
from titan_cli.engine.runs.status import RunSessionStatus, TERMINAL_SESSION_STATUSES
from titan_cli.engine.runs.store import RunStore

__all__ = [
    "InteractionRequestedError",
    "PromptRequestedError",
    "PromptResponse",
    "RunEventStream",
    "RunInteractionPort",
    "RunSession",
    "RunSessionStatus",
    "RunStore",
    "StartWorkflowRequest",
    "StartWorkflowResponse",
    "SubmitInteractionResponseRequest",
    "SubmitPromptResponseRequest",
    "TERMINAL_SESSION_STATUSES",
    "WorkflowRunService",
    "WorkflowRunState",
    "build_run_result",
    "result_for_session",
]
