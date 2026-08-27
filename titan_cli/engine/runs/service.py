"""Workflow run service: owns run lifecycle, state, and event emission."""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path
from queue import Queue
from typing import Any, Optional

from titan_cli.core.config import TitanConfig
from titan_cli.core.security import create_broker_factory
from titan_cli.core.services.models import (
    WorkflowDetail,
    WorkflowStepSummary,
    WorkflowSummary,
)
from titan_cli.engine.builder import WorkflowContextBuilder
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import is_error
from titan_cli.engine.runs.event_stream import RunEventStream
from titan_cli.engine.runs.interaction_port import (
    InteractionRequestedError,
    PromptRequestedError,
    RunInteractionPort,
)
from titan_cli.engine.runs.interaction_validation import validate_interaction_response
from titan_cli.engine.runs.models import (
    StartWorkflowRequest,
    StartWorkflowResponse,
    SubmitInteractionResponseRequest,
    SubmitPromptResponseRequest,
    WorkflowRunState,
)
from titan_cli.engine.runs.projection import (
    build_run_result,
    count_workflow_steps,
    result_for_session,
)
from titan_cli.engine.runs.session import RunSession
from titan_cli.engine.runs.status import RunSessionStatus, TERMINAL_SESSION_STATUSES
from titan_cli.engine.runs.store import RunStore
from titan_cli.engine.workflow_executor import WorkflowExecutor
from titan_cli.ports.protocol import EngineEvent
from titan_cli.ports.protocol import EventType

_CONFIG_CWD_LOCK = threading.Lock()


class WorkflowRunService:
    """Owns workflow run lifecycle, state, and event emission."""

    def __init__(
        self,
        config: TitanConfig,
        run_store: Optional[RunStore] = None,
        run_event_stream: Optional[RunEventStream] = None,
    ) -> None:
        self._config = config
        self._run_store = run_store or RunStore()
        self._run_event_stream = run_event_stream or RunEventStream(self._run_store)

    def list_workflows(self, project_path: Optional[str] = None) -> list[WorkflowSummary]:
        """Return available workflows from the active registry."""
        config = self._config_for_project_path(project_path)
        summaries: list[WorkflowSummary] = []
        for workflow in config.workflows.discover():
            summaries.append(
                WorkflowSummary(
                    name=workflow.name,
                    description=workflow.description,
                    source=workflow.source,
                )
            )
        return summaries

    def describe_workflow(
        self,
        workflow_name: str,
        project_path: Optional[str] = None,
    ) -> WorkflowDetail | None:
        """Return resolved workflow metadata, including inherited and hook steps."""
        config = self._config_for_project_path(project_path)
        workflow = config.workflows.get_workflow(workflow_name)
        if workflow is None:
            return None

        return WorkflowDetail(
            name=workflow.name,
            description=workflow.description,
            source=workflow.source,
            params=dict(workflow.params),
            steps=[self._step_summary_from_dict(step) for step in workflow.steps],
        )

    def start_workflow(self, request: StartWorkflowRequest) -> StartWorkflowResponse:
        """Create and execute a workflow run."""
        session = self.create_run(request)
        self._execute_run(session, request)
        return StartWorkflowResponse(
            run_id=session.run_id,
            status=session.status,
            events=list(session.events),
            pending_prompt=session.pending_prompt,
            pending_interaction=session.pending_interaction,
            result=result_for_session(session),
        )

    def create_run(self, request: StartWorkflowRequest) -> RunSession:
        """Create and persist a run session before execution starts."""
        session = RunSession(
            run_id=str(uuid.uuid4()),
            workflow_name=request.workflow_name,
            status=RunSessionStatus.CREATED,
            metadata={
                "params": request.params,
                "prompt_responses": list(request.prompt_responses),
                "project_path": request.project_path,
                "interaction_mode": request.interaction_mode,
            },
        )
        self._run_store.save(session)
        return session

    def execute_run(self, session: RunSession, request: StartWorkflowRequest) -> None:
        """Execute a previously created run session."""
        self._execute_run(session, request)

    def get_run(self, run_id: str) -> WorkflowRunState | None:
        """Return the current state for a run id."""
        session = self._run_store.get(run_id)
        if not session:
            return None
        return WorkflowRunState(
            run_id=session.run_id,
            workflow_name=session.workflow_name,
            status=session.status,
            result_message=session.result_message,
            events=list(session.events),
            pending_prompt=session.pending_prompt,
            pending_interaction=session.pending_interaction,
            prompt_history=list(session.prompt_history),
            metadata=dict(session.metadata),
            result=result_for_session(session),
        )

    def snapshot_events(self, run_id: str, after_sequence: int = 0) -> list[EngineEvent]:
        """Return persisted run events after the given sequence."""
        return self._run_event_stream.snapshot(run_id, after_sequence=after_sequence)

    def subscribe_events(self, run_id: str):
        """Subscribe to live events for the given run id."""
        return self._run_event_stream.subscribe(run_id)

    def unsubscribe_events(self, run_id: str, queue: Queue[EngineEvent]) -> None:
        """Remove a live event subscription for the given run id."""
        self._run_event_stream.unsubscribe(run_id, queue)

    def submit_prompt_response(
        self,
        request: SubmitPromptResponseRequest,
    ) -> WorkflowRunState | None:
        """Store a response for a pending prompt and resume execution."""
        session = self._run_store.get(request.run_id)
        if not session or not session.pending_prompt:
            return self.get_run(request.run_id)

        if session.pending_prompt.prompt_id != request.prompt_id:
            return self.get_run(request.run_id)

        session.record_prompt_answer(session.pending_prompt, request.value)
        session.metadata.setdefault("prompt_responses", [])
        session.metadata["prompt_responses"].append(request.value)
        session.pending_interaction = None
        session.status = RunSessionStatus.RESUMING
        self._run_store.save(session)
        resume_step_index = int(session.metadata.get("resume_step_index") or 1)
        self._execute_run(
            session,
            self._request_from_session(session),
            start_step_index=max(resume_step_index - 1, 0),
            emit_run_started=False,
            resuming=True,
            queued_prompt_responses=[request.value],
            resume_step_id=session.metadata.get("resume_step_id"),
        )
        self._run_store.save(session)
        return self.get_run(request.run_id)

    def submit_interaction_response(
        self,
        request: SubmitInteractionResponseRequest,
    ) -> WorkflowRunState | None:
        """Store a response for a pending interaction and resume execution."""
        session = self._run_store.get(request.run_id)
        if not session or not session.pending_interaction:
            return self.get_run(request.run_id)

        if session.pending_interaction.interaction_id != request.interaction_id:
            return self.get_run(request.run_id)

        try:
            response = validate_interaction_response(
                session.pending_interaction,
                request.response_type,
                request.value,
            )
        except ValueError as exc:
            session.pending_prompt = None
            session.pending_interaction = None
            session.status = RunSessionStatus.FAILED
            session.result_message = str(exc)
            self._finish_run(
                session,
                EventType.RUN_FAILED,
                {
                    "message": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            self._run_store.save(session)
            return self.get_run(request.run_id)

        session.record_interaction_answer(session.pending_interaction, response)
        session.pending_prompt = None
        session.status = RunSessionStatus.RESUMING
        self._run_store.save(session)
        resume_step_index = int(session.metadata.get("resume_step_index") or 1)
        self._execute_run(
            session,
            self._request_from_session(session),
            start_step_index=max(resume_step_index - 1, 0),
            emit_run_started=False,
            resuming=True,
            queued_interaction_responses=[response],
            resume_step_id=session.metadata.get("resume_step_id"),
        )
        self._run_store.save(session)
        return self.get_run(request.run_id)

    def cancel_run(self, run_id: str, reason: str = "Run cancelled by user") -> WorkflowRunState | None:
        """Mark a run as cancelled and emit the terminal V1 event."""
        session = self._run_store.get(run_id)
        if not session:
            return None
        if session.status in TERMINAL_SESSION_STATUSES:
            return self.get_run(run_id)

        session.metadata["cancel_requested"] = reason

        if session.status in {
            RunSessionStatus.WAITING_FOR_PROMPT,
            RunSessionStatus.WAITING_FOR_INTERACTION,
        }:
            session.pending_prompt = None
            session.pending_interaction = None
            session.status = RunSessionStatus.CANCELLED
            session.result_message = reason
            self._finish_run(
                session,
                EventType.RUN_CANCELLED,
                {"message": reason},
            )

        self._run_store.save(session)
        return self.get_run(run_id)

    def _append_event(
        self,
        session: RunSession,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> EngineEvent:
        """Append, persist, and publish a run event."""
        event = EngineEvent(
            type=event_type,
            run_id=session.run_id,
            sequence=len(session.events) + 1,
            payload=payload,
        )
        session.events.append(event)
        self._run_store.save(session)
        self._run_event_stream.publish(event)
        return event

    def _finish_run(
        self,
        session: RunSession,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> None:
        """Emit the terminal run event followed by the run_result_emitted snapshot.

        The terminal snapshot is owned by the runtime so every adapter receives
        run_result_emitted through the regular event stream instead of
        synthesizing it at the binding layer.
        """
        self._append_event(session, event_type, payload)
        self._append_event(
            session,
            EventType.RUN_RESULT_EMITTED,
            {"run_result": build_run_result(session)},
        )

    def _build_context(
        self,
        session: RunSession,
        request: StartWorkflowRequest,
        config: TitanConfig,
        queued_prompt_responses: Optional[list[object]] = None,
        queued_interaction_responses: Optional[list[dict[str, object]]] = None,
        resume_step_id: Optional[str] = None,
    ) -> WorkflowContext:
        """Build execution context mirroring the current TUI flow."""
        workspace_path = Path(request.project_path) if request.project_path else config.project_root
        ctx_builder = WorkflowContextBuilder(
            plugin_registry=config.registry,
            ai_config=config.config.ai,
        )
        ctx_builder.with_ai()
        ctx_builder.with_ai_router()

        for plugin_name in config.registry.list_installed():
            plugin = config.registry.get_plugin(plugin_name)
            if not plugin:
                continue

            if hasattr(ctx_builder, f"with_{plugin_name}"):
                try:
                    client = plugin.get_client()
                    getattr(ctx_builder, f"with_{plugin_name}")(client)
                except Exception:
                    pass

            try:
                managers = plugin.get_workflow_managers(project_root=workspace_path)
                if managers is not None:
                    ctx_builder.with_plugin_managers(plugin_name, managers)
            except Exception:
                pass

        ctx = ctx_builder.build()
        interaction_port = RunInteractionPort(
            self,
            session,
            ctx,
            queued_prompt_responses=(
                list(queued_prompt_responses)
                if queued_prompt_responses is not None
                else list(request.prompt_responses)
            ),
            queued_interaction_responses=(
                list(queued_interaction_responses)
                if queued_interaction_responses is not None
                else []
            ),
            resume_step_id=resume_step_id,
        )
        object.__setattr__(ctx, "interaction", interaction_port)
        object.__setattr__(ctx, "textual", interaction_port)
        ctx.data.update(request.params)
        ctx.data.update(dict(session.metadata.get("ctx_data", {})))
        ctx.data.setdefault("project_root", str(workspace_path))
        ctx.data.setdefault("cwd", str(workspace_path))
        return ctx

    def _request_from_session(self, session: RunSession) -> StartWorkflowRequest:
        """Rebuild the execution request from persisted run session metadata."""
        return StartWorkflowRequest(
            workflow_name=session.workflow_name,
            params=dict(session.metadata.get("params", {})),
            prompt_responses=list(session.metadata.get("prompt_responses", [])),
            project_path=session.metadata.get("project_path"),
            interaction_mode=session.metadata.get("interaction_mode", "headless"),
        )

    def _execute_run(
        self,
        session: RunSession,
        request: StartWorkflowRequest,
        *,
        start_step_index: int = 0,
        emit_run_started: bool = True,
        resuming: bool = False,
        queued_prompt_responses: Optional[list[object]] = None,
        queued_interaction_responses: Optional[list[dict[str, object]]] = None,
        resume_step_id: Optional[str] = None,
    ) -> None:
        """Execute a workflow synchronously and update run state."""
        session.pending_prompt = None
        session.pending_interaction = None
        config = self._config_for_project_path(request.project_path)
        workspace_path = Path(request.project_path) if request.project_path else config.project_root
        broker_factory = create_broker_factory(project_path=workspace_path)
        workflow = config.workflows.get_workflow(request.workflow_name)

        session.status = (
            RunSessionStatus.RESUMING if resuming else RunSessionStatus.RUNNING
        )
        if emit_run_started:
            self._append_event(
                session,
                EventType.RUN_STARTED,
                {
                    "workflow_name": request.workflow_name,
                    "workflow_title": workflow.description if workflow else request.workflow_name,
                    "project_path": request.project_path or str(config.project_root),
                    "total_steps": count_workflow_steps(workflow),
                },
            )

        if workflow is None:
            session.status = RunSessionStatus.FAILED
            session.result_message = f"Workflow '{request.workflow_name}' not found."
            self._finish_run(
                session,
                EventType.RUN_FAILED,
                {"message": session.result_message},
            )
            return

        ctx: WorkflowContext | None = None
        try:
            ctx = self._build_context(
                session,
                request,
                config,
                queued_prompt_responses=queued_prompt_responses,
                queued_interaction_responses=queued_interaction_responses,
                resume_step_id=resume_step_id,
            )
            executor = WorkflowExecutor(
                plugin_registry=config.registry,
                workflow_registry=config.workflows,
                broker_factory=broker_factory,
            )
            result = executor.execute(
                workflow,
                ctx,
                params_override=request.params,
                start_step_index=start_step_index,
            )
            session.metadata.update(ctx.data)
            session.metadata.pop("resume_step_index", None)
            session.metadata.pop("resume_step_id", None)
            session.metadata.pop("resume_step_name", None)
            session.metadata.pop("ctx_data", None)

            cancel_reason = session.metadata.get("cancel_requested")
            if cancel_reason:
                session.status = RunSessionStatus.CANCELLED
                session.result_message = str(cancel_reason)
                self._finish_run(
                    session,
                    EventType.RUN_CANCELLED,
                    {"message": str(cancel_reason)},
                )
                return

            if is_error(result):
                session.status = RunSessionStatus.FAILED
                session.result_message = result.message
                self._finish_run(
                    session,
                    EventType.RUN_FAILED,
                    {"message": result.message},
                )
                return

            session.status = RunSessionStatus.COMPLETED
            session.result_message = result.message
            self._finish_run(
                session,
                EventType.RUN_COMPLETED,
                {
                    "message": result.message,
                    "metadata": result.metadata or {},
                },
            )
        except PromptRequestedError as prompt_exc:
            session.status = RunSessionStatus.WAITING_FOR_PROMPT
            session.pending_prompt = prompt_exc.prompt
            session.pending_interaction = None
            session.result_message = prompt_exc.prompt.message
            if ctx is not None:
                session.metadata["ctx_data"] = dict(ctx.data)
                session.metadata["resume_step_index"] = ctx.current_step
                session.metadata["resume_step_id"] = ctx.current_step_id
                session.metadata["resume_step_name"] = ctx.current_step_name
            self._run_store.save(session)
        except InteractionRequestedError as interaction_exc:
            session.status = RunSessionStatus.WAITING_FOR_INTERACTION
            session.pending_interaction = interaction_exc.interaction
            session.pending_prompt = None
            session.result_message = interaction_exc.interaction.message
            if ctx is not None:
                session.metadata["ctx_data"] = dict(ctx.data)
                session.metadata["resume_step_index"] = ctx.current_step
                session.metadata["resume_step_id"] = ctx.current_step_id
                session.metadata["resume_step_name"] = ctx.current_step_name
            self._run_store.save(session)
        except Exception as exc:
            session.status = RunSessionStatus.FAILED
            session.result_message = str(exc)
            self._finish_run(
                session,
                EventType.RUN_FAILED,
                {
                    "message": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

    def _config_for_project_path(self, project_path: Optional[str]) -> TitanConfig:
        """Create a workspace-specific config when a project path is provided."""
        if not project_path:
            return self._config

        workspace_path = Path(project_path).expanduser().resolve()
        registry = self._config.registry.__class__()

        with _CONFIG_CWD_LOCK:
            previous_cwd = Path.cwd()
            try:
                os.chdir(workspace_path)
                return TitanConfig(registry=registry)
            finally:
                os.chdir(previous_cwd)

    def _step_summary_from_dict(self, step: dict) -> WorkflowStepSummary:
        """Normalize resolved workflow step dictionaries for native clients."""
        return WorkflowStepSummary(
            id=step.get("id"),
            name=step.get("name"),
            plugin=step.get("plugin"),
            step=step.get("step"),
            command=step.get("command"),
            workflow=step.get("workflow"),
            hook=step.get("hook"),
            requires=list(step.get("requires") or []),
            on_error=step.get("on_error", "fail"),
            params=dict(step.get("params") or {}),
        )
