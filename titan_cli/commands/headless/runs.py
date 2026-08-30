"""Headless workflow run commands."""

import json
import sys
import threading
from collections import deque
from queue import Empty, Queue
from typing import Any, Optional

import typer

from titan_cli.engine.runs import (
    StartWorkflowRequest,
    SubmitInteractionResponseRequest,
    SubmitPromptResponseRequest,
    RunSessionStatus,
    TERMINAL_SESSION_STATUSES,
)
from titan_cli.commands.headless.common import (
    fail_headless_command,
    parse_json_array,
    parse_json_object,
)
from titan_cli.core.logging import get_logger
from titan_cli.ports.protocol import CommandType
from titan_cli.ports.protocol import EngineCommand
from titan_cli.ports.protocol import EngineEvent
from titan_cli.runtime.container import TitanRuntimeContainer
from titan_cli.runtime.output import to_jsonable


def _protocol_logger():
    """Return the structured logger for headless V1 communications."""
    return get_logger("titan.headless.protocol")


def _event_log_fields(event: EngineEvent) -> dict[str, Any]:
    """Return safe structured log fields for an outbound protocol event."""
    fields: dict[str, Any] = {
        "run_id": event.run_id,
        "sequence": event.sequence,
        "event_type": str(event.type),
    }
    payload = event.payload or {}
    step = payload.get("step")
    if step is not None:
        fields["step_id"] = getattr(step, "step_id", None)
    output = payload.get("output")
    if output is not None:
        fields["output_format"] = getattr(output, "format", None)
        fields["output_title_present"] = bool(getattr(output, "title", None))
        fields["output_content_length"] = len(getattr(output, "content", "") or "")
    prompt = payload.get("prompt")
    if prompt is not None:
        fields["prompt_id"] = getattr(prompt, "prompt_id", None)
        fields["prompt_type"] = getattr(prompt, "prompt_type", None)
        fields["prompt_message_length"] = len(getattr(prompt, "message", "") or "")
    interaction = payload.get("interaction")
    if interaction is not None:
        fields["interaction_id"] = getattr(interaction, "interaction_id", None)
        fields["interaction_type"] = getattr(interaction, "interaction_type", None)
    return fields


def _command_log_fields(command: EngineCommand) -> dict[str, Any]:
    """Return safe structured log fields for an inbound protocol command."""
    payload = command.payload or {}
    value = payload.get("value")
    reason = payload.get("reason")
    fields: dict[str, Any] = {
        "run_id": command.run_id,
        "command_type": str(command.type),
        "prompt_id": payload.get("prompt_id"),
        "interaction_id": payload.get("interaction_id"),
        "response_type": payload.get("response_type"),
        "value_present": "value" in payload,
        "value_type": type(value).__name__ if value is not None else None,
        "value_length": len(value) if isinstance(value, str) else None,
        "reason_present": reason is not None,
        "reason_length": len(reason) if isinstance(reason, str) else None,
    }
    return fields


def _log_outbound_event(event: EngineEvent) -> None:
    """Log an outbound event without leaking protocol payload contents."""
    _protocol_logger().info("headless_protocol_event_emitted", **_event_log_fields(event))


def _log_inbound_command(command: EngineCommand) -> None:
    """Log an inbound command without logging sensitive values."""
    _protocol_logger().info("headless_protocol_command_received", **_command_log_fields(command))


def _log_protocol_state(event_name: str, **fields: Any) -> None:
    """Log non-payload communication lifecycle information."""
    _protocol_logger().info(event_name, **fields)


def _log_protocol_error(event_name: str, **fields: Any) -> None:
    """Log protocol and transport errors through Titan's logger."""
    _protocol_logger().error(event_name, **fields)


def build_app(container: TitanRuntimeContainer) -> typer.Typer:
    """Build headless workflow run commands."""
    app = typer.Typer(name="runs", help="Start and inspect workflow runs.")

    @app.command("start")
    def start_run(
        workflow_name: str = typer.Argument(..., help="Workflow name to run."),
        project_path: Optional[str] = typer.Option(
            None,
            "--project-path",
            help="Project directory used to resolve project workflows and plugin config.",
        ),
        params_json: Optional[str] = typer.Option(
            None,
            "--params-json",
            help="JSON object merged into the workflow context.",
        ),
        prompt_responses_json: Optional[str] = typer.Option(
            None,
            "--prompt-responses-json",
            help="JSON array of pre-seeded prompt responses for headless execution.",
        ),
        interaction_responses_json: Optional[str] = typer.Option(
            None,
            "--interaction-responses-json",
            help="JSON array of pre-seeded interaction responses for headless execution.",
        ),
        ai_cli: Optional[str] = typer.Option(
            None,
            "--ai-cli-id",
            help="CLI identifier to use for AI-backed steps in this run.",
        ),
        output_json: bool = typer.Option(
            False,
            "--json",
            help=(
                "Compatibility flag for headless clients. runs start always emits "
                "JSON Lines event-stream output."
            ),
        ),
        mode: str = typer.Option(
            "event_stream",
            "--mode",
            help="Headless protocol output mode. Only event_stream is supported in V1.",
        ),
    ):
        """Run a workflow through the headless V1 adapter binding."""
        try:
            request = StartWorkflowRequest(
                workflow_name=workflow_name,
                params=parse_json_object(params_json, "--params-json"),
                prompt_responses=parse_json_array(
                    prompt_responses_json,
                    "--prompt-responses-json",
                ),
                interaction_responses=parse_json_array(
                    interaction_responses_json,
                    "--interaction-responses-json",
                ),
                project_path=project_path,
                ai_cli=ai_cli,
                interaction_mode="headless",
            )
            _log_protocol_state(
                "headless_run_requested",
                workflow_name=workflow_name,
                mode=mode,
                output_json=output_json,
                project_path=project_path,
                ai_cli=ai_cli,
                preseeded_prompt_responses=len(request.prompt_responses),
                preseeded_interaction_responses=len(request.interaction_responses),
            )

            if mode != "event_stream":
                raise typer.BadParameter("--mode must be 'event_stream'")

            _run_event_stream_mode(container, request)
        except typer.BadParameter:
            raise
        except Exception as exc:
            fail_headless_command(exc, as_json=False)

    return app


def _run_event_stream_mode(container: TitanRuntimeContainer, request: StartWorkflowRequest) -> None:
    """Run a workflow and expose the official V1 event stream over stdio."""
    service = container.workflow_run_service()
    session = service.create_run(request)
    last_sequence = 0
    _log_protocol_state(
        "headless_event_stream_started",
        run_id=session.run_id,
        workflow_name=request.workflow_name,
    )

    def _emit_event(event: EngineEvent) -> None:
        nonlocal last_sequence
        if event.sequence <= last_sequence:
            return
        _log_outbound_event(event)
        typer.echo(json.dumps(to_jsonable(event)))
        last_sequence = event.sequence

    def _emit_snapshot() -> None:
        for event in service.snapshot_events(session.run_id, after_sequence=last_sequence):
            _emit_event(event)

    event_queue = service.subscribe_events(session.run_id)
    command_queue: Queue[EngineCommand | BaseException] = Queue()

    def _read_commands() -> None:
        """Continuously receive inbound commands for the lifetime of the run."""
        while True:
            try:
                command_queue.put(_read_engine_command(session.run_id))
            except BaseException as exc:
                command_queue.put(exc)
                return

    command_reader = threading.Thread(
        target=_read_commands,
        name=f"titan-headless-stdin-{session.run_id}",
        daemon=True,
    )
    command_reader.start()
    pending_commands: deque[EngineCommand] = deque()
    stdin_error: Optional[BaseException] = None

    run_worker = threading.Thread(
        target=lambda: service.execute_run(session, request),
    )
    resume_worker: Optional[threading.Thread] = None
    _emit_snapshot()
    run_worker.start()

    def _start_resume_worker(operation, event_name: str) -> threading.Thread:
        resumed_worker = threading.Thread(target=operation)
        resumed_worker.start()
        _log_protocol_state(
            event_name,
            run_id=session.run_id,
            worker_ident=resumed_worker.ident,
        )
        return resumed_worker

    def _emit_live_events(timeout_seconds: float = 0.0) -> None:
        while True:
            try:
                event = event_queue.get(timeout=timeout_seconds)
            except Empty:
                break
            _emit_event(event)
            timeout_seconds = 0

    def _receive_commands() -> None:
        nonlocal stdin_error
        while True:
            try:
                item = command_queue.get_nowait()
            except Empty:
                return
            if isinstance(item, BaseException):
                stdin_error = item
                return
            pending_commands.append(item)

    def _take_next_command(run_state) -> Optional[EngineCommand]:
        """Take one ordered command when the current run state accepts it."""
        if not pending_commands:
            return None
        command = pending_commands[0]

        if command.type == CommandType.CANCEL_RUN:
            pending_commands.popleft()
            _log_inbound_command(command)
            return command

        if (
            command.type == CommandType.SUBMIT_PROMPT_RESPONSE
            and run_state.status == RunSessionStatus.WAITING_FOR_PROMPT
        ):
            pending_commands.popleft()
            _log_inbound_command(command)
            return command

        if (
            command.type == CommandType.SUBMIT_INTERACTION_RESPONSE
            and run_state.status == RunSessionStatus.WAITING_FOR_INTERACTION
        ):
            pending_commands.popleft()
            _log_inbound_command(command)
            return command

        return None

    try:
        while True:
            _receive_commands()
            if resume_worker is not None and resume_worker.is_alive():
                run_state = service.get_run(session.run_id)
                if run_state is not None and pending_commands and pending_commands[0].type == CommandType.CANCEL_RUN:
                    command = _take_next_command(run_state)
                    if command is not None:
                        reason = str(command.payload.get("reason") or "Run cancelled by user")
                        service.cancel_run(command.run_id, reason=reason)
                _emit_live_events(timeout_seconds=0.1)
                continue

            if run_worker.is_alive() or resume_worker is not None:
                _emit_live_events(timeout_seconds=0.1)
            else:
                _emit_live_events()

            run_state = service.get_run(session.run_id)
            if run_state is None:
                _log_protocol_error(
                    "headless_event_stream_missing_run_state",
                    run_id=session.run_id,
                )
                return

            if run_state.status in TERMINAL_SESSION_STATUSES:
                if resume_worker is not None:
                    resume_worker.join(timeout=5.0)
                    resume_worker = None
                run_worker.join(timeout=5.0)
                _emit_live_events()
                _emit_snapshot()
                _log_protocol_state(
                    "headless_event_stream_finished",
                    run_id=session.run_id,
                    session_status=str(run_state.status),
                )
                return

            if pending_commands and pending_commands[0].type == CommandType.CANCEL_RUN:
                command = _take_next_command(run_state)
                if command is not None:
                    reason = str(command.payload.get("reason") or "Run cancelled by user")
                    service.cancel_run(command.run_id, reason=reason)
                continue

            if resume_worker is not None and not resume_worker.is_alive():
                resume_worker.join(timeout=0)
                resume_worker = None
                continue

            if run_state.status in {
                RunSessionStatus.WAITING_FOR_PROMPT,
                RunSessionStatus.WAITING_FOR_INTERACTION,
            }:
                _log_protocol_state(
                    "headless_event_stream_waiting_for_input",
                    run_id=run_state.run_id,
                    prompt_id=(run_state.pending_prompt.prompt_id if run_state.pending_prompt else None),
                    prompt_type=(run_state.pending_prompt.prompt_type if run_state.pending_prompt else None),
                    interaction_id=(run_state.pending_interaction.interaction_id if run_state.pending_interaction else None),
                    interaction_type=(run_state.pending_interaction.interaction_type if run_state.pending_interaction else None),
                )
                command = _take_next_command(run_state)
                if command is None:
                    if stdin_error is not None:
                        _log_protocol_error(
                            "headless_protocol_stdin_unavailable",
                            run_id=run_state.run_id,
                            error_type=type(stdin_error).__name__,
                            error=str(stdin_error),
                        )
                        service.cancel_run(
                            run_state.run_id,
                            reason="Headless client disconnected while input was required",
                        )
                    continue

                if command.type == CommandType.SUBMIT_PROMPT_RESPONSE:
                    prompt_id = str(command.payload.get("prompt_id") or "")
                    resume_worker = _start_resume_worker(
                        lambda command=command, prompt_id=prompt_id: service.submit_prompt_response(
                            SubmitPromptResponseRequest(
                                run_id=command.run_id,
                                prompt_id=prompt_id,
                                value=command.payload.get("value"),
                            )
                        ),
                        "headless_event_stream_prompt_resume_started",
                    )
                    continue

                if command.type == CommandType.SUBMIT_INTERACTION_RESPONSE:
                    interaction_id = str(command.payload.get("interaction_id") or "")
                    response_type = str(command.payload.get("response_type") or "")
                    resume_worker = _start_resume_worker(
                        lambda command=command, interaction_id=interaction_id, response_type=response_type: service.submit_interaction_response(
                            SubmitInteractionResponseRequest(
                                run_id=command.run_id,
                                interaction_id=interaction_id,
                                response_type=response_type,
                                value=command.payload.get("value"),
                            )
                        ),
                        "headless_event_stream_interaction_resume_started",
                    )
                    continue
    finally:
        service.unsubscribe_events(session.run_id, event_queue)
        if resume_worker is not None:
            resume_worker.join(timeout=1.0)
        run_worker.join(timeout=1.0)
        _log_protocol_state(
            "headless_event_stream_worker_joined",
            run_id=session.run_id,
            worker_alive=run_worker.is_alive(),
            resume_worker_alive=(resume_worker.is_alive() if resume_worker is not None else False),
        )


def _read_engine_command(run_id: str) -> EngineCommand:
    """Read a single inbound V1 command from stdin as JSON."""
    line = sys.stdin.readline()
    if not line:
        raise ValueError("stdin closed while waiting for an inbound EngineCommand")

    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        _log_protocol_error(
            "headless_protocol_command_parse_failed",
            run_id=run_id,
            error=str(exc),
            raw_length=len(line),
        )
        raise ValueError(f"stdin must contain valid JSON Lines commands: {exc.msg}") from exc

    if not isinstance(payload, dict):
        _log_protocol_error(
            "headless_protocol_command_invalid_shape",
            run_id=run_id,
            payload_type=type(payload).__name__,
        )
        raise ValueError("stdin command must be a JSON object")

    command_run_id = str(payload.get("run_id") or run_id)
    command_type = payload.get("type")
    if command_type not in {
        CommandType.SUBMIT_PROMPT_RESPONSE,
        CommandType.SUBMIT_INTERACTION_RESPONSE,
        CommandType.CANCEL_RUN,
    }:
        _log_protocol_error(
            "headless_protocol_command_invalid_type",
            run_id=command_run_id,
            command_type=command_type,
        )
        raise ValueError(
            "stdin command type must be 'submit_prompt_response', 'submit_interaction_response' or 'cancel_run'"
        )

    return EngineCommand(
        type=CommandType(command_type),
        run_id=command_run_id,
        payload=dict(payload.get("payload") or {}),
    )
