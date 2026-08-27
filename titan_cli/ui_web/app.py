"""FastAPI application for the local Titan web adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from queue import Empty
from queue import Queue
import threading
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from titan_cli.engine.runs import (
    StartWorkflowRequest,
    SubmitInteractionResponseRequest,
    SubmitPromptResponseRequest,
    TERMINAL_SESSION_STATUSES,
)
from titan_cli.ports.protocol import CommandType
from titan_cli.ports.protocol import EngineCommand
from titan_cli.ports.protocol import EngineEvent
from titan_cli.ports.protocol import EventType
from titan_cli.runtime.container import TitanRuntimeContainer
from titan_cli.runtime.output import to_jsonable
from titan_cli.ui_web.session_manager import BrowserSessionManager


STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(container: TitanRuntimeContainer) -> FastAPI:
    """Create the local web adapter application."""
    app = FastAPI(title="Titan UI", docs_url=None, redoc_url=None)
    session_manager = BrowserSessionManager()

    app.state.container = container
    app.state.session_manager = session_manager

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(
                status_code=503,
                detail="Titan UI frontend build not found. Run 'npm install && npm run build' in web_ui/.",
            )
        return FileResponse(index_path)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        service = container.workflow_run_service()
        session_id: str | None = None
        active_run_id: str | None = None
        event_queue: Queue[EngineEvent] | None = None
        relay_task: asyncio.Task[None] | None = None
        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")

                if message_type == "open_session":
                    session = session_manager.open_session()
                    session_id = session.session_id
                    await websocket.send_json(
                        {
                            "type": "session_opened",
                            "payload": {
                                "session_id": session.session_id,
                                "adapter": "local_web",
                                "transport": "websocket",
                            },
                        }
                    )
                    continue

                if message_type == "start_run":
                    if session_id is None:
                        await websocket.send_json(_session_error("Session must be opened before starting a run."))
                        continue
                    if relay_task is not None and relay_task.done():
                        if event_queue is not None and active_run_id is not None:
                            service.unsubscribe_events(active_run_id, event_queue)
                        relay_task = None
                        event_queue = None
                        active_run_id = None
                        session_manager.set_active_run(session_id, None)
                    if event_queue is not None:
                        await websocket.send_json(_session_error("Only one active run is supported per browser session."))
                        continue

                    payload = _payload(message)
                    request = StartWorkflowRequest(
                        workflow_name=str(payload.get("workflow_name") or "").strip(),
                        project_path=_optional_string(payload.get("project_path")),
                        params=_payload_dict(payload.get("params")),
                        interaction_mode="headless",
                    )
                    if not request.workflow_name:
                        await websocket.send_json(_session_error("workflow_name is required."))
                        continue

                    run_session = service.create_run(request)
                    active_run_id = run_session.run_id
                    session_manager.set_active_run(session_id, run_session.run_id)
                    event_queue = service.subscribe_events(run_session.run_id)
                    relay_task = asyncio.create_task(
                        _relay_run_events(
                            websocket=websocket,
                            service=service,
                            run_id=run_session.run_id,
                            event_queue=event_queue,
                        )
                    )

                    worker = threading.Thread(
                        target=lambda: service.execute_run(run_session, request),
                        daemon=True,
                    )
                    worker.start()

                    await websocket.send_json(
                        {
                            "type": "run_bootstrapped",
                            "payload": {
                                "session_id": session_id,
                                "run_id": run_session.run_id,
                                "workflow_name": request.workflow_name,
                                "project_path": request.project_path,
                            },
                        }
                    )
                    continue

                if message_type == "runtime_command":
                    if session_id is None:
                        await websocket.send_json(_session_error("Session must be opened before sending commands."))
                        continue

                    command_payload = message.get("command")
                    if not isinstance(command_payload, dict):
                        await websocket.send_json(_session_error("runtime_command requires a command object."))
                        continue

                    command = _parse_runtime_command(command_payload)
                    if command is None:
                        await websocket.send_json(_session_error("Unsupported runtime command payload."))
                        continue

                    await _handle_runtime_command(service, command)
                    continue

                await websocket.send_json(
                    _session_error(f"Unsupported message type: {message_type!r}")
                )
        except WebSocketDisconnect:
            return
        finally:
            if relay_task is not None:
                relay_task.cancel()
            if session_id is not None and active_run_id is not None:
                session_manager.set_active_run(session_id, None)
            if event_queue is not None and active_run_id is not None:
                service.unsubscribe_events(active_run_id, event_queue)
            if session_id is not None:
                session_manager.set_active_run(session_id, None)

    return app


def _payload(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload")
    return payload if isinstance(payload, dict) else {}


def _payload_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _session_error(message: str) -> dict[str, Any]:
    return {
        "type": "session_error",
        "payload": {
            "message": message,
        },
    }


def _parse_runtime_command(payload: dict[str, Any]) -> EngineCommand | None:
    command_type = payload.get("type")
    run_id = payload.get("run_id")
    if not isinstance(command_type, str) or not isinstance(run_id, str):
        return None

    try:
        parsed_type = CommandType(command_type)
    except ValueError:
        return None

    command_payload = payload.get("payload")
    if not isinstance(command_payload, dict):
        command_payload = {}

    return EngineCommand(
        type=parsed_type,
        run_id=run_id,
        payload=command_payload,
    )


async def _handle_runtime_command(service, command: EngineCommand) -> None:
    if command.type == CommandType.SUBMIT_PROMPT_RESPONSE:
        await asyncio.to_thread(
            service.submit_prompt_response,
            SubmitPromptResponseRequest(
                run_id=command.run_id,
                prompt_id=str(command.payload.get("prompt_id") or ""),
                value=command.payload.get("value"),
            ),
        )
        return

    if command.type == CommandType.SUBMIT_INTERACTION_RESPONSE:
        await asyncio.to_thread(
            service.submit_interaction_response,
            SubmitInteractionResponseRequest(
                run_id=command.run_id,
                interaction_id=str(command.payload.get("interaction_id") or ""),
                response_type=str(command.payload.get("response_type") or ""),
                value=command.payload.get("value"),
            ),
        )
        return

    if command.type == CommandType.CANCEL_RUN:
        await asyncio.to_thread(
            service.cancel_run,
            command.run_id,
            str(command.payload.get("reason") or "Run cancelled by user"),
        )


async def _relay_run_events(
    *,
    websocket: WebSocket,
    service,
    run_id: str,
    event_queue: Queue[EngineEvent],
) -> None:
    last_sequence = 0

    for event in service.snapshot_events(run_id, after_sequence=last_sequence):
        await websocket.send_json({"type": "runtime_event", "event": to_jsonable(event)})
        last_sequence = event.sequence
        if event.type == EventType.RUN_RESULT_EMITTED:
            return

    while True:
        try:
            event = await asyncio.to_thread(event_queue.get, True, 0.1)
        except Empty:
            run_state = service.get_run(run_id)
            if run_state is None:
                return
            if run_state.status in TERMINAL_SESSION_STATUSES:
                for event in service.snapshot_events(run_id, after_sequence=last_sequence):
                    await websocket.send_json(
                        {"type": "runtime_event", "event": to_jsonable(event)}
                    )
                    last_sequence = event.sequence
                return
            continue

        if event.sequence <= last_sequence:
            continue

        await websocket.send_json({"type": "runtime_event", "event": to_jsonable(event)})
        last_sequence = event.sequence
        if event.type == EventType.RUN_RESULT_EMITTED:
            return
