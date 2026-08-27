from queue import Queue
from types import SimpleNamespace

from fastapi.testclient import TestClient

from titan_cli.engine.runs.models import StartWorkflowRequest
from titan_cli.engine.runs.models import WorkflowRunState
from titan_cli.engine.runs.status import RunSessionStatus
from titan_cli.ports.protocol import EngineEvent
from titan_cli.ports.protocol import EventType
from titan_cli.ports.protocol import OutputFormat
from titan_cli.ports.protocol import OutputPayload
from titan_cli.ports.protocol import RunResult
from titan_cli.ports.protocol import RunStatus
from titan_cli.runtime.container import TitanRuntimeContainer
from titan_cli.ui_web.app import create_app


def test_ui_shell_served() -> None:
    client = TestClient(create_app(TitanRuntimeContainer()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Titan UI" in response.text
    assert '<div id="root"></div>' in response.text


def test_open_session_websocket() -> None:
    client = TestClient(create_app(TitanRuntimeContainer()))

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "open_session", "payload": {}})
        response = websocket.receive_json()

    assert response["type"] == "session_opened"
    assert response["payload"]["adapter"] == "local_web"
    assert response["payload"]["transport"] == "websocket"
    assert response["payload"]["session_id"].startswith("session-")


class FakeWorkflowRunService:
    def __init__(self) -> None:
        self.queue: Queue[EngineEvent] = Queue()
        self.run_id = "run-web-123"
        self.result = RunResult(
            run_id=self.run_id,
            workflow_name="commit-ai",
            status=RunStatus.COMPLETED,
            result=OutputPayload(format=OutputFormat.TEXT, content="Finished"),
        )
        self.run_state = WorkflowRunState(
            run_id=self.run_id,
            workflow_name="commit-ai",
            status=RunSessionStatus.CREATED,
            result=self.result,
        )

    def create_run(self, request: StartWorkflowRequest):
        assert request.workflow_name == "commit-ai"
        return SimpleNamespace(run_id=self.run_id)

    def subscribe_events(self, run_id: str):
        assert run_id == self.run_id
        return self.queue

    def snapshot_events(self, run_id: str, after_sequence: int = 0):
        assert run_id == self.run_id
        return [
            event
            for event in self.run_state.events
            if event.sequence > after_sequence
        ]

    def _emit(self, event: EngineEvent) -> None:
        self.run_state.events.append(event)
        self.queue.put(event)

    def execute_run(self, session, request: StartWorkflowRequest) -> None:
        self.run_state.status = RunSessionStatus.RUNNING
        self._emit(
            EngineEvent(
                type=EventType.RUN_STARTED,
                run_id=self.run_id,
                sequence=1,
                payload={"workflow_name": request.workflow_name},
            )
        )
        self.run_state.status = RunSessionStatus.COMPLETED
        # The runtime now owns the terminal snapshot event (run_result_emitted)
        self._emit(
            EngineEvent(
                type=EventType.RUN_RESULT_EMITTED,
                run_id=self.run_id,
                sequence=2,
                payload={"run_result": self.result},
            )
        )

    def get_run(self, run_id: str):
        assert run_id == self.run_id
        return self.run_state

    def unsubscribe_events(self, run_id: str, queue: Queue[EngineEvent]) -> None:
        assert run_id == self.run_id
        assert queue is self.queue


class FakeContainer(TitanRuntimeContainer):
    def __init__(self) -> None:
        self.service = FakeWorkflowRunService()

    def workflow_run_service(self) -> FakeWorkflowRunService:
        return self.service


def test_start_run_streams_runtime_events() -> None:
    client = TestClient(create_app(FakeContainer()))

    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "open_session", "payload": {}})
        opened = websocket.receive_json()

        websocket.send_json(
            {
                "type": "start_run",
                "payload": {
                    "workflow_name": "commit-ai",
                    "project_path": None,
                    "params": {},
                },
            }
        )

        bootstrapped = websocket.receive_json()
        runtime_started = websocket.receive_json()
        runtime_result = websocket.receive_json()

    assert opened["type"] == "session_opened"
    assert bootstrapped["type"] == "run_bootstrapped"
    assert bootstrapped["payload"]["run_id"] == "run-web-123"
    assert runtime_started["type"] == "runtime_event"
    assert runtime_started["event"]["type"] == "run_started"
    assert runtime_result["type"] == "runtime_event"
    assert runtime_result["event"]["type"] == "run_result_emitted"
