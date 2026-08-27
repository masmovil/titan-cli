import json
from queue import Queue
import time
from datetime import datetime, timezone

from typer.testing import CliRunner

from titan_cli.engine.runs.models import StartWorkflowRequest
from titan_cli.engine.runs.models import WorkflowRunState
from titan_cli.engine.runs.session import RunSession
from titan_cli.engine.runs.status import RunSessionStatus
from titan_cli.core.services.models import KnownPluginSummary
from titan_cli.core.services.models import PluginMutationResult
from titan_cli.core.services.models import PluginSourcePreview
from titan_cli.core.services.models import PluginInspection
from titan_cli.core.services.models import ProjectInspection
from titan_cli.core.services.models import WorkflowDetail
from titan_cli.core.services.models import WorkflowStepSummary
from titan_cli.core.services.models import WorkflowSummary
from titan_cli.cli import app
from titan_cli.commands.headless.runs import _command_log_fields
from titan_cli.commands.headless.runs import _event_log_fields
from titan_cli.commands.headless.runs import _run_event_stream_mode
from titan_cli.ports.protocol import CommandType
from titan_cli.ports.protocol import EngineEvent
from titan_cli.ports.protocol import EngineCommand
from titan_cli.ports.protocol import EventType
from titan_cli.ports.protocol import InteractionOption
from titan_cli.ports.protocol import InteractionRequest
from titan_cli.ports.protocol import OutputPayload
from titan_cli.ports.protocol import PromptRequest
from titan_cli.ports.protocol import RunResult
from titan_cli.ports.protocol import StepRef


def test_headless_workflows_list_outputs_json(monkeypatch):
    class StubWorkflowService:
        def list_workflows(self, project_path=None):
            assert project_path == "/tmp/demo"
            return [
                WorkflowSummary(
                    name="demo",
                    description="Demo workflow",
                    source="project",
                )
            ]

    monkeypatch.setattr(
        "titan_cli.cli._workflow_run_service",
        lambda: StubWorkflowService(),
    )

    result = CliRunner().invoke(
        app,
        ["headless", "workflows", "list", "--project-path", "/tmp/demo", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "items": [
            {
                "name": "demo",
                "description": "Demo workflow",
                "source": "project",
            }
        ]
    }


def test_headless_command_log_fields_redact_prompt_value() -> None:
    command = EngineCommand(
        type="submit_prompt_response",
        run_id="run-1",
        timestamp=datetime(2026, 5, 13, 13, 0, tzinfo=timezone.utc),
        payload={
            "prompt_id": "prompt-1",
            "value": "super-secret-response",
        },
    )

    fields = _command_log_fields(command)

    assert fields["run_id"] == "run-1"
    assert fields["command_type"] == "submit_prompt_response"
    assert fields["prompt_id"] == "prompt-1"
    assert fields["value_present"] is True
    assert fields["value_type"] == "str"
    assert fields["value_length"] == len("super-secret-response")
    assert "value" not in fields


def test_headless_event_log_fields_redact_prompt_and_output_contents() -> None:
    event = EngineEvent(
        type=EventType.PROMPT_REQUESTED,
        run_id="run-1",
        sequence=4,
        timestamp=datetime(2026, 5, 13, 13, 0, tzinfo=timezone.utc),
        payload={
            "step": StepRef(step_id="confirm", step_name="Confirm", step_index=2),
            "prompt": PromptRequest(
                prompt_id="confirm:confirm",
                prompt_type="confirm",
                message="Do you want to continue?",
            ),
            "output": OutputPayload(
                format="markdown",
                title="Hidden",
                content="# Sensitive output",
            ),
        },
    )

    fields = _event_log_fields(event)

    assert fields["run_id"] == "run-1"
    assert fields["sequence"] == 4
    assert fields["event_type"] == "prompt_requested"
    assert fields["step_id"] == "confirm"
    assert fields["prompt_id"] == "confirm:confirm"
    assert fields["prompt_type"] == "confirm"
    assert fields["prompt_message_length"] == len("Do you want to continue?")
    assert fields["output_format"] == "markdown"
    assert fields["output_content_length"] == len("# Sensitive output")
    assert "message" not in fields
    assert "content" not in fields


def test_headless_runs_start_passes_headless_request_and_outputs_event_stream(monkeypatch):
    captured_request = None

    class StubWorkflowService:
        def __init__(self):
            self.session = RunSession(
                run_id="run-1",
                workflow_name="demo",
                status=RunSessionStatus.RUNNING,
            )
            self.queue = Queue()

        def _publish(self, event):
            self.session.events.append(event)
            self.queue.put(event)

        def create_run(self, request):
            nonlocal captured_request
            captured_request = request
            return self.session

        def execute_run(self, session, request):
            self._publish(
                EngineEvent(
                    type=EventType.RUN_STARTED,
                    run_id=session.run_id,
                    sequence=1,
                    payload={"workflow_name": request.workflow_name},
                )
            )
            self._publish(
                EngineEvent(
                    type=EventType.RUN_COMPLETED,
                    run_id=session.run_id,
                    sequence=2,
                    payload={"message": "done"},
                )
            )
            session.status = RunSessionStatus.COMPLETED
            # The runtime now owns the terminal snapshot event (run_result_emitted)
            self._publish(
                EngineEvent(
                    type=EventType.RUN_RESULT_EMITTED,
                    run_id=session.run_id,
                    sequence=3,
                    payload={"run_result": self.get_run(session.run_id).result},
                )
            )

        def snapshot_events(self, run_id, after_sequence=0):
            return [event for event in self.session.events if event.sequence > after_sequence]

        def subscribe_events(self, run_id):
            return self.queue

        def unsubscribe_events(self, run_id, queue):
            return None

        def get_run(self, run_id):
            return WorkflowRunState(
                run_id=self.session.run_id,
                workflow_name=self.session.workflow_name,
                status=self.session.status,
                result=RunResult(
                    run_id="run-1",
                    workflow_name="demo",
                    status="completed",
                    result=OutputPayload(
                        format="markdown",
                        title="Summary",
                        content="# Done",
                    ),
                ),
            )

    monkeypatch.setattr(
        "titan_cli.cli._workflow_run_service",
        lambda: StubWorkflowService(),
    )

    result = CliRunner().invoke(
        app,
        [
            "headless",
            "runs",
            "start",
            "demo",
            "--project-path",
            "/tmp/demo",
            "--params-json",
            '{"issue": "ABC-1"}',
            "--prompt-responses-json",
            '["yes"]',
        ],
    )

    assert result.exit_code == 0
    assert captured_request is not None
    assert captured_request.workflow_name == "demo"
    assert captured_request.project_path == "/tmp/demo"
    assert captured_request.params == {"issue": "ABC-1"}
    assert captured_request.prompt_responses == ["yes"]
    assert captured_request.interaction_mode == "headless"
    lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert [line["type"] for line in lines] == [
        "run_started",
        "run_completed",
        "run_result_emitted",
    ]
    assert lines[-1]["payload"]["run_result"]["result"]["content"] == "# Done"


def test_headless_runs_start_event_stream_outputs_json_lines(monkeypatch):
    captured_request = None

    class StubWorkflowService:
        def __init__(self):
            self.session = RunSession(
                run_id="run-1",
                workflow_name="demo",
                status=RunSessionStatus.RUNNING,
            )
            self.queue = Queue()

        def _publish(self, event):
            self.session.events.append(event)
            self.queue.put(event)

        def create_run(self, request):
            nonlocal captured_request
            captured_request = request
            return self.session

        def execute_run(self, session, request):
            self._publish(
                EngineEvent(
                    type=EventType.RUN_STARTED,
                    run_id=session.run_id,
                    sequence=1,
                    payload={"workflow_name": request.workflow_name},
                )
            )
            self._publish(
                EngineEvent(
                    type=EventType.RUN_COMPLETED,
                    run_id=session.run_id,
                    sequence=2,
                    payload={"message": "done"},
                )
            )
            session.status = RunSessionStatus.COMPLETED
            # The runtime now owns the terminal snapshot event (run_result_emitted)
            self._publish(
                EngineEvent(
                    type=EventType.RUN_RESULT_EMITTED,
                    run_id=session.run_id,
                    sequence=3,
                    payload={"run_result": self.get_run(session.run_id).result},
                )
            )

        def snapshot_events(self, run_id, after_sequence=0):
            return [event for event in self.session.events if event.sequence > after_sequence]

        def subscribe_events(self, run_id):
            return self.queue

        def unsubscribe_events(self, run_id, queue):
            return None

        def get_run(self, run_id):
            return WorkflowRunState(
                run_id=self.session.run_id,
                workflow_name=self.session.workflow_name,
                status=self.session.status,
                result=(
                    RunResult(
                        run_id="run-1",
                        workflow_name="demo",
                        status="completed",
                        result=OutputPayload(
                            format="markdown",
                            title="Summary",
                            content="# Done",
                        ),
                    )
                    if self.session.status == RunSessionStatus.COMPLETED
                    else None
                ),
            )

    monkeypatch.setattr(
        "titan_cli.cli._workflow_run_service",
        lambda: StubWorkflowService(),
    )

    result = CliRunner().invoke(
        app,
        [
            "headless",
            "runs",
            "start",
            "demo",
        ],
    )

    assert result.exit_code == 0
    assert captured_request is not None
    lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert [line["type"] for line in lines] == ["run_started", "run_completed", "run_result_emitted"]


def test_headless_runs_start_event_stream_reads_prompt_response_from_stdin(monkeypatch):
    submitted_request = None

    class StubWorkflowService:
        def __init__(self):
            self.session = RunSession(
                run_id="run-1",
                workflow_name="demo",
                status=RunSessionStatus.RUNNING,
            )
            self._cursor = 0
            self.queue = Queue()

        def _publish(self, event):
            self.session.events.append(event)
            self.queue.put(event)

        def create_run(self, request):
            return self.session

        def execute_run(self, session, request):
            self._publish(
                EngineEvent(
                    type=EventType.RUN_STARTED,
                    run_id=session.run_id,
                    sequence=1,
                    payload={"workflow_name": request.workflow_name},
                )
            )
            prompt = PromptRequest(
                prompt_id="prompt-1",
                prompt_type="text",
                message="Enter value",
            )
            session.pending_prompt = prompt
            self._publish(
                EngineEvent(
                    type=EventType.PROMPT_REQUESTED,
                    run_id=session.run_id,
                    sequence=2,
                    payload={
                        "step": StepRef(
                            step_id="ask_value",
                            step_name="Ask Value",
                            step_index=1,
                        ),
                        "prompt": prompt,
                    },
                )
            )
            session.status = RunSessionStatus.WAITING_FOR_PROMPT

        def snapshot_events(self, run_id, after_sequence=0):
            return [event for event in self.session.events if event.sequence > after_sequence]

        def subscribe_events(self, run_id):
            return self.queue

        def unsubscribe_events(self, run_id, queue):
            return None

        def get_run(self, run_id):
            return WorkflowRunState(
                run_id=self.session.run_id,
                workflow_name=self.session.workflow_name,
                status=self.session.status,
                pending_prompt=self.session.pending_prompt,
                result=(
                    RunResult(
                        run_id="run-1",
                        workflow_name="demo",
                        status="completed",
                        result=OutputPayload(
                            format="markdown",
                            title="Summary",
                            content="# Done",
                        ),
                    )
                    if self.session.status == RunSessionStatus.COMPLETED
                    else None
                ),
            )

        def submit_prompt_response(self, request):
            nonlocal submitted_request
            submitted_request = request
            self.session.pending_prompt = None
            self.session.status = RunSessionStatus.COMPLETED
            self._publish(
                EngineEvent(
                    type=EventType.RUN_COMPLETED,
                    run_id=self.session.run_id,
                    sequence=3,
                    payload={"message": "done"},
                )
            )
            # The runtime now owns the terminal snapshot event (run_result_emitted)
            self._publish(
                EngineEvent(
                    type=EventType.RUN_RESULT_EMITTED,
                    run_id=self.session.run_id,
                    sequence=4,
                    payload={"run_result": self.get_run(request.run_id).result},
                )
            )
            return self.get_run(request.run_id)

    monkeypatch.setattr(
        "titan_cli.cli._workflow_run_service",
        lambda: StubWorkflowService(),
    )

    result = CliRunner().invoke(
        app,
        [
            "headless",
            "runs",
            "start",
            "demo",
        ],
        input='{"type":"submit_prompt_response","run_id":"run-1","payload":{"prompt_id":"prompt-1","value":"hello"}}\n',
    )

    assert result.exit_code == 0
    assert submitted_request is not None
    assert submitted_request.prompt_id == "prompt-1"
    assert submitted_request.value == "hello"
    lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert [line["type"] for line in lines] == [
        "run_started",
        "prompt_requested",
        "run_completed",
        "run_result_emitted",
    ]


def test_headless_workflows_describe_outputs_resolved_steps(monkeypatch):
    class StubWorkflowService:
        def describe_workflow(self, workflow_name, project_path=None):
            assert workflow_name == "demo"
            assert project_path == "/tmp/demo"
            return WorkflowDetail(
                name="demo",
                description="Demo workflow",
                source="project",
                params={"branch": "main"},
                steps=[
                    WorkflowStepSummary(
                        id="git_status",
                        name="Git Status",
                        plugin="git",
                        step="status",
                    )
                ],
            )

    monkeypatch.setattr(
        "titan_cli.cli._workflow_run_service",
        lambda: StubWorkflowService(),
    )

    result = CliRunner().invoke(
        app,
        [
            "headless",
            "workflows",
            "describe",
            "demo",
            "--project-path",
            "/tmp/demo",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "name": "demo",
        "description": "Demo workflow",
        "source": "project",
        "params": {"branch": "main"},
        "steps": [
            {
                "id": "git_status",
                "name": "Git Status",
                "plugin": "git",
                "step": "status",
                "command": None,
                "workflow": None,
                "hook": None,
                "requires": [],
                "on_error": "fail",
                "params": {},
            }
        ],
    }


def test_headless_runs_start_accepts_interaction_response_commands(monkeypatch):
    submitted_request = None

    class StubWorkflowService:
        def __init__(self):
            self.session = RunSession(
                run_id="run-1",
                workflow_name="demo",
                status=RunSessionStatus.RUNNING,
            )
            self._cursor = 0
            self.queue = Queue()

        def _publish(self, event):
            self.session.events.append(event)
            self.queue.put(event)

        def create_run(self, request):
            return self.session

        def execute_run(self, session, request):
            self._publish(
                EngineEvent(
                    type=EventType.RUN_STARTED,
                    run_id=session.run_id,
                    sequence=1,
                    payload={"workflow_name": request.workflow_name},
                )
            )
            interaction = InteractionRequest(
                interaction_id="select-cli:select-cli",
                interaction_type="option_list",
                message="Choose CLI",
                state={
                    "options": [
                        InteractionOption(id="claude", label="Claude", value="claude"),
                    ]
                },
            )
            session.pending_interaction = interaction
            self._publish(
                EngineEvent(
                    type=EventType.INTERACTION_REQUESTED,
                    run_id=session.run_id,
                    sequence=2,
                    payload={
                        "step": StepRef(
                            step_id="select_cli",
                            step_name="Select AI CLI",
                            step_index=1,
                        ),
                        "interaction": interaction,
                    },
                )
            )
            session.status = RunSessionStatus.WAITING_FOR_INTERACTION

        def snapshot_events(self, run_id, after_sequence=0):
            return [event for event in self.session.events if event.sequence > after_sequence]

        def subscribe_events(self, run_id):
            return self.queue

        def unsubscribe_events(self, run_id, queue):
            return None

        def get_run(self, run_id):
            return WorkflowRunState(
                run_id=self.session.run_id,
                workflow_name=self.session.workflow_name,
                status=self.session.status,
                pending_prompt=self.session.pending_prompt,
                pending_interaction=self.session.pending_interaction,
                result=(
                    RunResult(
                        run_id="run-1",
                        workflow_name="demo",
                        status="completed",
                        result=OutputPayload(
                            format="markdown",
                            title="Summary",
                            content="# Done",
                        ),
                    )
                    if self.session.status == RunSessionStatus.COMPLETED
                    else None
                ),
            )

        def submit_interaction_response(self, request):
            nonlocal submitted_request
            submitted_request = request
            self.session.pending_interaction = None
            self.session.status = RunSessionStatus.COMPLETED
            self._publish(
                EngineEvent(
                    type=EventType.RUN_COMPLETED,
                    run_id=self.session.run_id,
                    sequence=3,
                    payload={"message": "done"},
                )
            )
            # The runtime now owns the terminal snapshot event (run_result_emitted)
            self._publish(
                EngineEvent(
                    type=EventType.RUN_RESULT_EMITTED,
                    run_id=self.session.run_id,
                    sequence=4,
                    payload={"run_result": self.get_run(request.run_id).result},
                )
            )
            return self.get_run(request.run_id)

    monkeypatch.setattr(
        "titan_cli.cli._workflow_run_service",
        lambda: StubWorkflowService(),
    )

    result = CliRunner().invoke(
        app,
        ["headless", "runs", "start", "demo"],
        input='{"type":"submit_interaction_response","run_id":"run-1","payload":{"interaction_id":"select-cli:select-cli","response_type":"select","value":"claude"}}\n',
    )

    assert result.exit_code == 0
    assert submitted_request is not None
    assert submitted_request.interaction_id == "select-cli:select-cli"
    assert submitted_request.response_type == "select"
    assert submitted_request.value == "claude"
    lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert [line["type"] for line in lines] == [
        "run_started",
        "interaction_requested",
        "run_completed",
        "run_result_emitted",
    ]


def test_headless_runs_start_streams_next_interaction_after_resume(monkeypatch):
    class StubWorkflowService:
        def __init__(self):
            self.session = None
            self._cursor = 0
            self.queue = Queue()

        def _publish(self, event):
            self.session.events.append(event)
            self.queue.put(event)

        def create_run(self, request):
            self.session = RunSession(
                run_id="run-1",
                workflow_name=request.workflow_name,
                status=RunSessionStatus.RUNNING,
            )
            return self.session

        def execute_run(self, session, request):
            self._publish(
                EngineEvent(
                    type=EventType.RUN_STARTED,
                    run_id=session.run_id,
                    sequence=1,
                    payload={"workflow_name": request.workflow_name},
                )
            )
            interaction = InteractionRequest(
                interaction_id="select_pr:select-pr",
                interaction_type="option_list",
                message="Choose PR",
                state={
                    "options": [
                        InteractionOption(id="223", label="PR 223", value="223"),
                    ]
                },
            )
            session.pending_interaction = interaction
            self._publish(
                EngineEvent(
                    type=EventType.INTERACTION_REQUESTED,
                    run_id=session.run_id,
                    sequence=2,
                    payload={
                        "step": StepRef(
                            step_id="select_pr",
                            step_name="Select PR",
                            step_index=1,
                        ),
                        "interaction": interaction,
                    },
                )
            )
            session.status = RunSessionStatus.WAITING_FOR_INTERACTION

        def snapshot_events(self, run_id, after_sequence=0):
            return [event for event in self.session.events if event.sequence > after_sequence]

        def subscribe_events(self, run_id):
            return self.queue

        def unsubscribe_events(self, run_id, queue):
            return None

        def get_run(self, run_id):
            return WorkflowRunState(
                run_id=self.session.run_id,
                workflow_name=self.session.workflow_name,
                status=self.session.status,
                pending_prompt=self.session.pending_prompt,
                pending_interaction=self.session.pending_interaction,
                result=None,
            )

        def submit_interaction_response(self, request):
            time.sleep(0.05)
            self.session.pending_interaction = None
            self._publish(
                EngineEvent(
                    type=EventType.STEP_FINISHED,
                    run_id=self.session.run_id,
                    sequence=3,
                    payload={
                        "step": StepRef(
                            step_id="select_pr",
                            step_name="Select PR",
                            step_index=1,
                        ),
                        "status": "success",
                        "message": "success",
                        "metadata": {},
                    },
                )
            )
            interaction = InteractionRequest(
                interaction_id="select_cli:select-cli",
                interaction_type="option_list",
                message="Choose CLI",
                state={
                    "options": [
                        InteractionOption(id="claude", label="Claude", value="claude"),
                    ]
                },
            )
            self._publish(
                EngineEvent(
                    type=EventType.STEP_STARTED,
                    run_id=self.session.run_id,
                    sequence=4,
                    payload={
                        "step": StepRef(
                            step_id="select_cli",
                            step_name="Select CLI",
                            step_index=2,
                        ),
                        "plugin": "github",
                        "step_kind": "plugin",
                    },
                )
            )
            self.session.pending_interaction = interaction
            self._publish(
                EngineEvent(
                    type=EventType.INTERACTION_REQUESTED,
                    run_id=self.session.run_id,
                    sequence=5,
                    payload={
                        "step": StepRef(
                            step_id="select_cli",
                            step_name="Select CLI",
                            step_index=2,
                        ),
                        "interaction": interaction,
                    },
                )
            )
            self.session.status = RunSessionStatus.WAITING_FOR_INTERACTION
            return self.get_run(request.run_id)

        def cancel_run(self, run_id, reason="stop"):
            self.session.pending_interaction = None
            self.session.status = RunSessionStatus.CANCELLED
            self._publish(
                EngineEvent(
                    type=EventType.RUN_CANCELLED,
                    run_id=self.session.run_id,
                    sequence=6,
                    payload={"message": reason},
                )
            )
            return self.get_run(run_id)

    class StubContainer:
        def __init__(self):
            self._service = StubWorkflowService()

        def workflow_run_service(self):
            return self._service

    command_iter = iter(
        [
            EngineCommand(
                type=CommandType.SUBMIT_INTERACTION_RESPONSE,
                run_id="run-1",
                payload={
                    "interaction_id": "select_pr:select-pr",
                    "response_type": "select",
                    "value": "223",
                },
            ),
            EngineCommand(
                type=CommandType.CANCEL_RUN,
                run_id="run-1",
                payload={"reason": "stop"},
            ),
        ]
    )
    emitted = []

    monkeypatch.setattr(
        "titan_cli.commands.headless.runs._read_engine_command",
        lambda _run_id: next(command_iter),
    )
    monkeypatch.setattr(
        "titan_cli.commands.headless.runs.typer.echo",
        lambda line: emitted.append(json.loads(line)),
    )

    _run_event_stream_mode(
        StubContainer(),
        StartWorkflowRequest(workflow_name="demo"),
    )

    assert [line["type"] for line in emitted[:5]] == [
        "run_started",
        "interaction_requested",
        "step_finished",
        "step_started",
        "interaction_requested",
    ]


def test_headless_workflows_list_keeps_stdout_json_when_runtime_prints(monkeypatch):
    class StubWorkflowService:
        def list_workflows(self, project_path=None):
            print("plugin noise")
            return [WorkflowSummary(name="demo")]

    monkeypatch.setattr(
        "titan_cli.cli._workflow_run_service",
        lambda: StubWorkflowService(),
    )

    result = CliRunner().invoke(
        app,
        ["headless", "workflows", "list", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "items": [
            {
                "name": "demo",
                "description": None,
                "source": None,
            }
        ]
    }
    assert "plugin noise" in result.stderr


def test_headless_project_inspect_outputs_project_snapshot(monkeypatch):
    class StubProjectInspectionService:
        def inspect_project(self, project_path=None):
            assert project_path == "/tmp/demo"
            return ProjectInspection(
                name="demo",
                type="ios",
                path="/tmp/demo",
                config_path="/tmp/demo/.titan/config.toml",
                configured=True,
                plugins=[
                    PluginInspection(
                        name="git",
                        enabled=True,
                        installed=True,
                        loaded=True,
                        available=True,
                        version="1.2.3",
                        workflows=["commit-ai"],
                        steps=["status"],
                    )
                ],
                workflows=[WorkflowSummary(name="commit-ai", source="project")],
            )

    monkeypatch.setattr(
        "titan_cli.cli._project_inspection_service",
        lambda: StubProjectInspectionService(),
    )

    result = CliRunner().invoke(
        app,
        ["headless", "project", "inspect", "--project-path", "/tmp/demo", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "name": "demo",
        "type": "ios",
        "path": "/tmp/demo",
        "config_path": "/tmp/demo/.titan/config.toml",
        "configured": True,
        "plugins": [
            {
                "name": "git",
                "enabled": True,
                "installed": True,
                "loaded": True,
                "available": True,
                "version": "1.2.3",
                "description": None,
                "source": {},
                "workflows": ["commit-ai"],
                "steps": ["status"],
                "error": None,
            }
        ],
        "workflows": [
            {
                "name": "commit-ai",
                "description": None,
                "source": "project",
            }
        ],
        "warnings": [],
        "sync_events": [],
        "diagnostics": [],
    }


def test_headless_ai_list_outputs_connections(monkeypatch):
    class StubTitanConfig:
        def get_ai_connections_config(self):
            return {
                "default_connection": "work",
                "connections": {
                    "work": {
                        "name": "Work Gateway",
                        "connection_type": "gateway",
                        "gateway_backend": "openai_compatible",
                        "base_url": "https://llm.example.com",
                        "default_model": "gemini-2.5-pro",
                        "max_tokens": 4096,
                        "temperature": 0.7,
                    }
                },
            }

    monkeypatch.setattr("titan_cli.cli._ai_config", lambda: StubTitanConfig())

    result = CliRunner().invoke(app, ["headless", "ai", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "default_connection": "work",
        "connections": [
            {
                "id": "work",
                "name": "Work Gateway",
                "connection_type": "gateway",
                "gateway_backend": "openai_compatible",
                "base_url": "https://llm.example.com",
                "default_model": "gemini-2.5-pro",
                "max_tokens": 4096,
                "temperature": 0.7,
                "is_default": True,
            }
        ],
    }


def test_headless_ai_upsert_saves_connection_and_secret(monkeypatch):
    saved_connection = None
    saved_secret = None

    class StubSecrets:
        def set(self, key, value, scope):
            nonlocal saved_secret
            saved_secret = (key, value, scope)

    class StubTitanConfig:
        secrets = StubSecrets()

        def __init__(self):
            self.ai_config = {"default_connection": None, "connections": {}}

        def get_ai_connections_config(self):
            return self.ai_config

        def upsert_ai_connection(self, connection_id, connection_data):
            nonlocal saved_connection
            saved_connection = (connection_id, connection_data)
            self.ai_config["connections"][connection_id] = connection_data
            self.ai_config["default_connection"] = connection_id

    stub_config = StubTitanConfig()
    monkeypatch.setattr("titan_cli.cli._ai_config", lambda: stub_config)

    result = CliRunner().invoke(
        app,
        [
            "headless",
            "ai",
            "upsert",
            "personal",
            "--connection-json",
            json.dumps(
                {
                    "name": "Personal Claude",
                    "connection_type": "direct_provider",
                    "provider": "anthropic",
                    "default_model": "claude-sonnet-4-5",
                }
            ),
            "--api-key-env",
            "TITAN_TEST_AI_API_KEY",
            "--json",
        ],
        env={"TITAN_TEST_AI_API_KEY": "secret-value"},
    )

    assert result.exit_code == 0
    assert saved_connection == (
        "personal",
        {
            "name": "Personal Claude",
            "connection_type": "direct_provider",
            "provider": "anthropic",
            "default_model": "claude-sonnet-4-5",
        },
    )
    assert saved_secret == ("personal_api_key", "secret-value", "user")
    assert json.loads(result.stdout)["default_connection"] == "personal"


def test_headless_ai_models_outputs_direct_provider_suggestions(monkeypatch):
    from titan_cli.core.models import AIConfig, AIConnectionConfig

    class StubTitanConfig:
        secrets = None
        config = type(
            "Config",
            (),
            {
                "ai": AIConfig(
                    default_connection="personal",
                    connections={
                        "personal": AIConnectionConfig(
                            name="Personal Google",
                            connection_type="direct_provider",
                            provider="gemini",
                            default_model="gemini-1.5-flash",
                        )
                    },
                )
            },
        )()

    monkeypatch.setattr("titan_cli.cli._ai_config", lambda: StubTitanConfig())

    result = CliRunner().invoke(
        app,
        ["headless", "ai", "models", "personal", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["connection_id"] == "personal"
    assert payload["default_model"] == "gemini-1.5-flash"
    assert {"id": "gemini-2.5-pro", "name": "gemini-2.5-pro", "owned_by": "gemini", "source": "suggested"} in payload["items"]


def test_headless_plugins_list_outputs_inspected_plugins(monkeypatch):
    captured_project_path = None

    class StubProjectInspectionService:
        def inspect_project(self, project_path=None):
            nonlocal captured_project_path
            captured_project_path = project_path
            return ProjectInspection(
                name="demo",
                type="ios",
                path="/tmp/demo",
                config_path="/tmp/demo/.titan/config.toml",
                configured=True,
                plugins=[
                    PluginInspection(
                        name="ragnarok",
                        enabled=True,
                        installed=True,
                        loaded=True,
                        available=True,
                        version="0.7.0",
                        description="Ragnarok workflows",
                        source={
                            "channel": "dev_local",
                            "path": "/tmp/ragnarok-plugin",
                        },
                        workflows=["analyze-jira-issues"],
                        steps=["ai_analyze_issue_requirements"],
                    )
                ],
                diagnostics=[],
            )

    monkeypatch.setattr(
        "titan_cli.cli._project_inspection_service",
        lambda: StubProjectInspectionService(),
    )

    result = CliRunner().invoke(
        app,
        ["headless", "plugins", "list", "--project-path", "/tmp/demo", "--json"],
    )

    assert result.exit_code == 0
    assert captured_project_path == "/tmp/demo"
    assert json.loads(result.stdout) == {
        "installed": ["ragnarok"],
        "enabled": ["ragnarok"],
        "items": [
            {
                "name": "ragnarok",
                "enabled": True,
                "installed": True,
                "loaded": True,
                "available": True,
                "version": "0.7.0",
                "description": "Ragnarok workflows",
                "source": {
                    "channel": "dev_local",
                    "path": "/tmp/ragnarok-plugin",
                },
                "workflows": ["analyze-jira-issues"],
                "steps": ["ai_analyze_issue_requirements"],
                "error": None,
            }
        ],
        "diagnostics": [],
    }


def test_headless_plugins_available_outputs_curated_plugins(monkeypatch):
    class StubPluginService:
        def list_available_plugins(self):
            return [
                KnownPluginSummary(
                    name="ragnarok",
                    description="Ragnarok workflows",
                    package_name="titan-plugin-ragnarok",
                    source="community",
                    repo_url="https://github.com/masmovil/ragnarok-titan-cli-workflows",
                    recommended_ref="0.7.0",
                )
            ]

    monkeypatch.setattr(
        "titan_cli.cli._plugin_service",
        lambda: StubPluginService(),
    )

    result = CliRunner().invoke(app, ["headless", "plugins", "available", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "items": [
            {
                "name": "ragnarok",
                "description": "Ragnarok workflows",
                "package_name": "titan-plugin-ragnarok",
                "source": "community",
                "repo_url": "https://github.com/masmovil/ragnarok-titan-cli-workflows",
                "recommended_ref": "0.7.0",
                "dependencies": [],
            }
        ]
    }


def test_headless_plugins_configure_passes_config_payload(monkeypatch):
    captured = None

    class StubPluginService:
        def configure_plugin(self, plugin_name, config_values):
            nonlocal captured
            captured = (plugin_name, config_values)
            return PluginMutationResult(
                plugin_name=plugin_name,
                changed=True,
                message="configured",
                config=config_values,
            )

    monkeypatch.setattr(
        "titan_cli.cli._plugin_service",
        lambda: StubPluginService(),
    )

    result = CliRunner().invoke(
        app,
        [
            "headless",
            "plugins",
            "configure",
            "ragnarok",
            "--config-json",
            '{"platform": "ios"}',
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured == ("ragnarok", {"platform": "ios"})
    assert json.loads(result.stdout) == {
        "plugin_name": "ragnarok",
        "changed": True,
        "message": "configured",
        "source": {},
        "config": {"platform": "ios"},
    }


def test_headless_plugins_preview_source_outputs_plugin_metadata(monkeypatch):
    captured = None

    class StubPluginService:
        def preview_stable_source(self, raw_url):
            nonlocal captured
            captured = raw_url
            return PluginSourcePreview(
                repo_url="https://github.com/example/titan-plugin-demo",
                requested_ref="v1.0.0",
                resolved_commit="a" * 40,
                package_name="titan-plugin-demo",
                version="1.0.0",
                description="Demo plugin",
                authors=["Titan Team"],
                titan_entry_points={"demo": "demo.plugin:DemoPlugin"},
                python_dependencies=["titan-cli"],
            )

    monkeypatch.setattr(
        "titan_cli.cli._plugin_service",
        lambda: StubPluginService(),
    )

    source = "https://github.com/example/titan-plugin-demo@v1.0.0"
    result = CliRunner().invoke(
        app,
        ["headless", "plugins", "preview-source", "--source", source, "--json"],
    )

    assert result.exit_code == 0
    assert captured == source
    assert json.loads(result.stdout) == {
        "repo_url": "https://github.com/example/titan-plugin-demo",
        "requested_ref": "v1.0.0",
        "resolved_commit": "a" * 40,
        "package_name": "titan-plugin-demo",
        "version": "1.0.0",
        "description": "Demo plugin",
        "authors": ["Titan Team"],
        "titan_entry_points": {"demo": "demo.plugin:DemoPlugin"},
        "python_dependencies": ["titan-cli"],
        "warnings": [],
    }


def test_headless_plugins_install_outputs_mutation(monkeypatch):
    captured = None

    class StubPluginService:
        def install_stable_source(self, raw_url):
            nonlocal captured
            captured = raw_url
            return PluginMutationResult(
                plugin_name="demo",
                changed=True,
                message="Plugin 'demo' installed.",
                source={
                    "channel": "stable",
                    "repo_url": "https://github.com/example/titan-plugin-demo",
                    "requested_ref": "v1.0.0",
                    "resolved_commit": "a" * 40,
                },
            )

    monkeypatch.setattr(
        "titan_cli.cli._plugin_service",
        lambda: StubPluginService(),
    )

    source = "https://github.com/example/titan-plugin-demo@v1.0.0"
    result = CliRunner().invoke(
        app,
        ["headless", "plugins", "install", "--source", source, "--json"],
    )

    assert result.exit_code == 0
    assert captured == source
    assert json.loads(result.stdout) == {
        "plugin_name": "demo",
        "changed": True,
        "message": "Plugin 'demo' installed.",
        "source": {
            "channel": "stable",
            "repo_url": "https://github.com/example/titan-plugin-demo",
            "requested_ref": "v1.0.0",
            "resolved_commit": "a" * 40,
        },
        "config": {},
    }


def test_headless_plugins_set_dev_source_outputs_mutation(monkeypatch):
    captured = None

    class StubPluginService:
        def set_dev_source(self, plugin_name, path):
            nonlocal captured
            captured = (plugin_name, path)
            return PluginMutationResult(
                plugin_name=plugin_name,
                changed=True,
                message="dev source configured",
                source={"channel": "dev_local", "path": path},
            )

    monkeypatch.setattr(
        "titan_cli.cli._plugin_service",
        lambda: StubPluginService(),
    )

    result = CliRunner().invoke(
        app,
        [
            "headless",
            "plugins",
            "set-dev-source",
            "ragnarok",
            "--path",
            "/tmp/ragnarok",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured == ("ragnarok", "/tmp/ragnarok")
    assert json.loads(result.stdout) == {
        "plugin_name": "ragnarok",
        "changed": True,
        "message": "dev source configured",
        "source": {"channel": "dev_local", "path": "/tmp/ragnarok"},
        "config": {},
    }


def test_headless_runs_start_rejects_non_object_params_json(monkeypatch):
    result = CliRunner().invoke(
        app,
        ["headless", "runs", "start", "demo", "--params-json", '["bad"]'],
    )

    assert result.exit_code != 0
    assert "--params-json must be a JSON object" in result.output
