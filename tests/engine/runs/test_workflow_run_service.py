from unittest.mock import MagicMock
from unittest.mock import patch
import threading

from titan_cli.engine.runs.models import StartWorkflowRequest
from titan_cli.engine.runs.models import SubmitInteractionResponseRequest
from titan_cli.engine.runs.models import SubmitPromptResponseRequest
from titan_cli.engine.runs.status import RunSessionStatus
from titan_cli.engine.runs.service import WorkflowRunService
from titan_cli.core.workflows.workflow_sources import WorkflowInfo
from titan_cli.engine.results import Error, Success
from titan_cli.ports.protocol import ContentBlock
from titan_cli.ports.protocol import ContentBlockType
from titan_cli.ports.protocol import ItemReviewEditState
from titan_cli.ports.protocol import ItemReviewItem
from titan_cli.ports.protocol import ItemReviewState


def test_list_workflows_maps_registry_discovery():
    config = MagicMock()
    config.workflows.discover.return_value = [
        WorkflowInfo(
            name="demo",
            description="Demo workflow",
            source="project",
            path=MagicMock(),
        )
    ]

    service = WorkflowRunService(config=config)
    workflows = service.list_workflows()

    assert len(workflows) == 1
    assert workflows[0].name == "demo"
    assert workflows[0].description == "Demo workflow"
    assert workflows[0].source == "project"


def test_start_workflow_creates_run_state():
    config = MagicMock()
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = None
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    service = WorkflowRunService(config=config)

    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert response.status == RunSessionStatus.FAILED
    assert run is not None
    assert run.workflow_name == "demo"
    assert run.status == RunSessionStatus.FAILED
    assert run.events[0].type == "run_started"
    assert run.events[-2].type == "run_failed"
    assert run.events[-1].type == "run_result_emitted"


def test_create_run_persists_explicit_ai_cli_selection():
    config = MagicMock()
    service = WorkflowRunService(config=config)

    session = service.create_run(
        StartWorkflowRequest(workflow_name="demo", ai_cli="codex")
    )

    assert session.metadata["ai_cli"] == "codex"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_executes_successfully(mock_executor_cls, mock_secret_manager_cls):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.return_value = Success("workflow ok", metadata={"done": True})
    mock_secret_manager_cls.return_value = MagicMock()

    service = WorkflowRunService(config=config)
    response = service.start_workflow(
        StartWorkflowRequest(workflow_name="demo", params={"foo": "bar"})
    )
    run = service.get_run(response.run_id)

    assert run is not None
    assert response.status == RunSessionStatus.COMPLETED
    assert run.status == RunSessionStatus.COMPLETED
    assert run.result_message == "workflow ok"
    assert run.events[0].type == "run_started"
    assert run.events[-2].type == "run_completed"
    assert run.events[-1].type == "run_result_emitted"
    mock_executor.execute.assert_called_once()


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_marks_failed_when_executor_returns_error(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.return_value = Error("boom")
    mock_secret_manager_cls.return_value = MagicMock()

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert run is not None
    assert response.status == RunSessionStatus.FAILED
    assert run.status == RunSessionStatus.FAILED
    assert run.result_message == "boom"
    assert run.events[-2].type == "run_failed"
    assert run.events[-1].type == "run_result_emitted"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_waits_for_prompt_when_interaction_is_required(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.interaction.ask_text("Enter value", default="demo")
        return Success("unreachable")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert run is not None
    assert response.status == RunSessionStatus.WAITING_FOR_PROMPT
    assert run.status == RunSessionStatus.WAITING_FOR_PROMPT
    assert run.pending_prompt is not None
    assert run.pending_prompt.prompt_type == "text"
    assert run.events[-1].type == "prompt_requested"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_consumes_preseeded_prompt_responses(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        answer = ctx.interaction.ask_text("Enter value", default="demo")
        assert answer == "seeded-answer"
        assert start_step_index == 0
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(
        StartWorkflowRequest(
            workflow_name="demo",
            prompt_responses=["seeded-answer"],
        )
    )
    run = service.get_run(response.run_id)

    assert run is not None
    assert response.status == RunSessionStatus.COMPLETED
    assert run.pending_prompt is None
    assert len(run.prompt_history) == 1
    assert run.prompt_history[0].value == "seeded-answer"
    assert not any(event.type == "prompt_answered" for event in run.events)


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_exposes_markdown_events_in_headless_runs(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.textual.markdown("## AI Analysis\n\nLooks good.")
        assert start_step_index == 0
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert response.status == RunSessionStatus.COMPLETED
    assert run is not None
    assert any(event.type == "output_emitted" for event in run.events)
    assert not any(
        event.type == "run_failed"
        and "markdown" in str(event.payload.get("message", ""))
        for event in run.events
    )


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_exposes_ai_chip_events_in_headless_runs(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.current_step = 1
        ctx.current_step_id = "ai_analyze"
        ctx.current_step_name = "AI Analyze Issue"
        ctx.textual.ai_chip("LiteLLM / rpl-qwen2.5")
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert response.status == RunSessionStatus.COMPLETED
    assert run is not None
    chip_outputs = [
        event.payload["output"]
        for event in run.events
        if event.type == "output_emitted"
        and event.payload["output"].metadata.get("presentation") == "ai_chip"
    ]
    assert len(chip_outputs) == 1
    assert chip_outputs[0].content == "LiteLLM / rpl-qwen2.5"
    assert chip_outputs[0].metadata["variant"] == "muted"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_exposes_interaction_events_in_headless_runs(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        from titan_cli.ports.protocol import InteractionOption

        ctx.interaction.option_list(
            interaction_id="select-cli",
            message="Choose CLI",
            options=[InteractionOption(id="claude", label="Claude", value="claude")],
        )
        return Success("unreachable")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert run is not None
    assert response.status == RunSessionStatus.WAITING_FOR_INTERACTION
    assert run.pending_interaction is not None
    assert run.pending_interaction.interaction_type == "option_list"
    assert run.events[-1].type == "interaction_requested"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_submit_prompt_response_resumes_run(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    state = {"calls": 0}
    seen_start_step_indexes = []

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        state["calls"] += 1
        seen_start_step_indexes.append(start_step_index)
        if state["calls"] == 1:
            ctx.interaction.ask_text("Enter value", default="demo")
            return Success("unreachable")

        answer = ctx.interaction.ask_text("Enter value", default="demo")
        assert answer == "hello"
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    assert waiting is not None
    assert waiting.status == RunSessionStatus.WAITING_FOR_PROMPT
    assert waiting.pending_prompt is not None

    updated = service.submit_prompt_response(
        SubmitPromptResponseRequest(
            run_id=response.run_id,
            prompt_id=waiting.pending_prompt.prompt_id,
            value="hello",
        )
    )

    assert updated is not None
    assert updated.status == RunSessionStatus.COMPLETED
    assert updated.pending_prompt is None
    assert updated.prompt_history[-1].value == "hello"
    assert not any(event.type == "workflow_run_resumed" for event in updated.events)
    assert updated.events[-2].type == "run_completed"
    assert updated.events[-1].type == "run_result_emitted"
    assert state["calls"] == 2
    assert seen_start_step_indexes == [0, 0]


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_submit_interaction_response_resumes_run(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    state = {"calls": 0}

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        from titan_cli.ports.protocol import InteractionOption

        state["calls"] += 1
        choice = ctx.interaction.option_list(
            interaction_id="select-cli",
            message="Choose CLI",
            options=[InteractionOption(id="claude", label="Claude", value="claude")],
        )
        if state["calls"] == 1:
            return Success("unreachable")

        assert choice == "claude"
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    assert waiting is not None
    assert waiting.status == RunSessionStatus.WAITING_FOR_INTERACTION
    assert waiting.pending_interaction is not None

    updated = service.submit_interaction_response(
        SubmitInteractionResponseRequest(
            run_id=response.run_id,
            interaction_id=waiting.pending_interaction.interaction_id,
            response_type="select",
            value="claude",
        )
    )

    assert updated is not None
    assert updated.status == RunSessionStatus.COMPLETED
    assert updated.pending_interaction is None
    assert updated.events[-2].type == "run_completed"
    assert updated.events[-1].type == "run_result_emitted"
    assert state["calls"] == 2


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_emits_semantic_diff_output(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.textual.display_diff(
            "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new",
            title="Files affected:",
            metadata={
                "kind": "unified_patch",
                "summary_lines": ["1 file changed, 1 insertion(+), 1 deletion(-)"],
            },
        )
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert run is not None
    diff_events = [event for event in run.events if event.type == "output_emitted"]
    assert len(diff_events) == 1
    output = diff_events[0].payload["output"]
    assert output.format == "diff"
    assert output.title == "Files affected:"
    assert output.metadata["kind"] == "unified_patch"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_submit_interaction_response_supports_two_consecutive_option_lists(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    state = {"calls": 0}

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        from titan_cli.ports.protocol import InteractionOption

        state["calls"] += 1

        if start_step_index == 0:
            ctx.current_step = 1
            ctx.current_step_id = "select_pr"
            ctx.current_step_name = "Select PR"
            first = ctx.interaction.option_list(
                interaction_id="select-pr",
                message="Choose PR",
                options=[InteractionOption(id="pr-1", label="PR 1", value="pr-1")],
            )
            if state["calls"] == 1:
                return Success("unreachable")
            assert first == "pr-1"

            ctx.current_step = 2
            ctx.current_step_id = "select_cli"
            ctx.current_step_name = "Select CLI"
            ctx.interaction.option_list(
                interaction_id="select-cli",
                message="Choose CLI",
                options=[InteractionOption(id="claude", label="Claude", value="claude")],
            )
            return Success("unreachable")

        if start_step_index == 1:
            ctx.current_step = 2
            ctx.current_step_id = "select_cli"
            ctx.current_step_name = "Select CLI"
            second = ctx.interaction.option_list(
                interaction_id="select-cli",
                message="Choose CLI",
                options=[InteractionOption(id="claude", label="Claude", value="claude")],
            )
            assert second == "claude"
            return Success("workflow ok")

        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    assert waiting is not None
    assert waiting.pending_interaction is not None
    assert waiting.pending_interaction.interaction_id == "select_pr:select-pr"

    second_wait = service.submit_interaction_response(
        SubmitInteractionResponseRequest(
            run_id=response.run_id,
            interaction_id=waiting.pending_interaction.interaction_id,
            response_type="select",
            value="pr-1",
        )
    )

    assert second_wait is not None
    assert second_wait.status == RunSessionStatus.WAITING_FOR_INTERACTION
    assert second_wait.pending_interaction is not None
    assert second_wait.pending_interaction.interaction_id == "select_cli:select-cli"

    completed = service.submit_interaction_response(
        SubmitInteractionResponseRequest(
            run_id=response.run_id,
            interaction_id=second_wait.pending_interaction.interaction_id,
            response_type="select",
            value="claude",
        )
    )

    assert completed is not None
    assert completed.status == RunSessionStatus.COMPLETED
    assert completed.pending_interaction is None


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_uses_preseeded_interaction_responses(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    from titan_cli.ports.protocol import InteractionOption

    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.current_step = 1
        ctx.current_step_id = "select_pr"
        ctx.current_step_name = "Select PR for Review"
        selected = ctx.interaction.option_list(
            interaction_id="select-option",
            message="Select a PR to review comments",
            options=[
                InteractionOption(
                    id="1",
                    label="#4479: refactor unused keys",
                    value=4479,
                )
            ],
        )
        assert selected == 4479
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(
        StartWorkflowRequest(
            workflow_name="demo",
            interaction_responses=[
                {
                    "interaction_id": "select_pr:select-option",
                    "response_type": "select",
                    "value": "4479",
                }
            ],
        )
    )
    run = service.get_run(response.run_id)

    assert run is not None
    assert response.status == RunSessionStatus.COMPLETED
    assert run.status == RunSessionStatus.COMPLETED
    assert run.pending_interaction is None
    assert run.metadata["interaction_responses"] == [
        {
            "interaction_id": "select_pr:select-option",
            "response_type": "select",
            "value": "4479",
        }
    ]


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_start_workflow_exposes_item_review_interaction_events(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.interaction.item_review(
            interaction_id="review-item-0",
            message="Review the proposed action and choose what to do next.",
            state=ItemReviewState(
                review_id="validate-review-actions",
                items=[
                    ItemReviewItem(
                        id="item-1",
                        title="Comment 1 of 1",
                        status="important",
                        content_blocks=[
                            ContentBlock(
                                type=ContentBlockType.TEXT,
                                title="Proposed action",
                                content="This may fail when the response is empty.",
                            )
                        ],
                        editable=True,
                    )
                ],
                allowed_actions=["approve", "edit", "skip"],
                edit=ItemReviewEditState(
                    enabled=True,
                ),
            ),
        )
        return Success("unreachable")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert run is not None
    assert response.status == RunSessionStatus.WAITING_FOR_INTERACTION
    assert run.pending_interaction is not None
    assert run.pending_interaction.interaction_type == "item_review"
    assert run.events[-1].type == "interaction_requested"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_submit_interaction_response_resumes_item_review_with_edit(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    call_count = {"value": 0}

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        call_count["value"] += 1
        response = ctx.interaction.item_review(
            interaction_id="review-item-0",
            message="Review the proposed action and choose what to do next.",
            state=ItemReviewState(
                review_id="validate-review-actions",
                items=[
                    ItemReviewItem(
                        id="item-1",
                        title="Comment 1 of 1",
                        status="important",
                        content_blocks=[
                            ContentBlock(
                                type=ContentBlockType.TEXT,
                                title="Proposed action",
                                content="This may fail when the response is empty.",
                            )
                        ],
                        editable=True,
                    )
                ],
                allowed_actions=["approve", "edit", "skip"],
                edit=ItemReviewEditState(
                    enabled=True,
                ),
            ),
        )
        if call_count["value"] == 1:
            return Success("unreachable")

        assert response.exit_requested is False
        assert len(response.items) == 1
        assert response.items[0].action == "edit"
        assert response.items[0].content == "Edited body"
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    assert waiting is not None
    assert waiting.pending_interaction is not None

    updated = service.submit_interaction_response(
        SubmitInteractionResponseRequest(
            run_id=response.run_id,
            interaction_id=waiting.pending_interaction.interaction_id,
            response_type="complete",
            value={
                "items": [{"item_id": "item-1", "action": "edit", "content": "Edited body"}],
                "exit_requested": False,
            },
        )
    )

    assert updated is not None
    assert updated.status == RunSessionStatus.COMPLETED
    assert updated.pending_interaction is None
    assert updated.events[-2].type == "run_completed"
    assert updated.events[-1].type == "run_result_emitted"
    assert call_count["value"] == 2


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_submit_interaction_response_fails_run_for_unknown_item_review_item(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.interaction.item_review(
            interaction_id="review-item-0",
            message="Review the proposed action and choose what to do next.",
            state=ItemReviewState(
                review_id="validate-review-actions",
                items=[
                    ItemReviewItem(
                        id="item-1",
                        title="Comment 1 of 1",
                        status="important",
                        content_blocks=[
                            ContentBlock(
                                type=ContentBlockType.TEXT,
                                title="Proposed action",
                                content="This may fail when the response is empty.",
                            )
                        ],
                        editable=True,
                    )
                ],
                allowed_actions=["approve", "edit", "skip", "exit"],
                edit=ItemReviewEditState(enabled=True),
            ),
        )
        return Success("unreachable")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    updated = service.submit_interaction_response(
        SubmitInteractionResponseRequest(
            run_id=response.run_id,
            interaction_id=waiting.pending_interaction.interaction_id,
            response_type="complete",
            value={
                "items": [{"item_id": "item-999", "action": "approve"}],
                "exit_requested": False,
            },
        )
    )

    assert updated is not None
    assert updated.status == RunSessionStatus.FAILED
    assert updated.pending_interaction is None
    assert updated.events[-2].type == "run_failed"
    assert updated.events[-1].type == "run_result_emitted"
    assert "unknown item_id" in updated.events[-2].payload["message"]


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_submit_interaction_response_fails_run_for_incomplete_item_review_without_exit(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.interaction.item_review(
            interaction_id="review-item-0",
            message="Review the proposed action and choose what to do next.",
            state=ItemReviewState(
                review_id="validate-review-actions",
                items=[
                    ItemReviewItem(id="item-1", title="Comment 1 of 2", editable=True),
                    ItemReviewItem(id="item-2", title="Comment 2 of 2", editable=True),
                ],
                allowed_actions=["approve", "edit", "skip", "exit"],
                edit=ItemReviewEditState(enabled=True),
            ),
        )
        return Success("unreachable")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    updated = service.submit_interaction_response(
        SubmitInteractionResponseRequest(
            run_id=response.run_id,
            interaction_id=waiting.pending_interaction.interaction_id,
            response_type="complete",
            value={
                "items": [{"item_id": "item-1", "action": "approve"}],
                "exit_requested": False,
            },
        )
    )

    assert updated is not None
    assert updated.status == RunSessionStatus.FAILED
    assert updated.pending_interaction is None
    assert updated.events[-2].type == "run_failed"
    assert updated.events[-1].type == "run_result_emitted"
    assert "must include one decision for every item" in updated.events[-2].payload["message"]


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_submit_interaction_response_allows_partial_item_review_with_exit_requested(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    call_count = {"value": 0}

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        call_count["value"] += 1
        response = ctx.interaction.item_review(
            interaction_id="review-item-0",
            message="Review the proposed action and choose what to do next.",
            state=ItemReviewState(
                review_id="validate-review-actions",
                items=[
                    ItemReviewItem(id="item-1", title="Comment 1 of 2", editable=True),
                    ItemReviewItem(id="item-2", title="Comment 2 of 2", editable=True),
                ],
                allowed_actions=["approve", "edit", "skip", "exit"],
                edit=ItemReviewEditState(enabled=True),
            ),
        )
        if call_count["value"] == 1:
            return Success("unreachable")

        assert response.exit_requested is True
        assert len(response.items) == 1
        assert response.items[0].item_id == "item-1"
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    updated = service.submit_interaction_response(
        SubmitInteractionResponseRequest(
            run_id=response.run_id,
            interaction_id=waiting.pending_interaction.interaction_id,
            response_type="complete",
            value={
                "items": [{"item_id": "item-1", "action": "approve"}],
                "exit_requested": True,
            },
        )
    )

    assert updated is not None
    assert updated.status == RunSessionStatus.COMPLETED
    assert updated.events[-2].type == "run_completed"
    assert updated.events[-1].type == "run_result_emitted"
    assert call_count["value"] == 2


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_success_text_emits_visible_text_output_with_success_variant(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.current_step = 1
        ctx.current_step_id = "select_strategy"
        ctx.current_step_name = "Select Review Strategy"
        ctx.interaction.success_text("Plan validated")
        ctx.interaction.dim_text("up to 4 focus files per plan")
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert run is not None
    outputs = [event for event in run.events if event.type == "output_emitted"]
    assert len(outputs) == 2
    assert outputs[0].payload["output"].metadata["variant"] == "success"
    assert outputs[1].payload["output"].metadata["variant"] == "muted"


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_loading_emits_progress_lifecycle_outputs(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        ctx.current_step = 1
        ctx.current_step_id = "ai_plan"
        ctx.current_step_name = "AI Review Plan"
        with ctx.interaction.loading("Asking Claude to plan the review..."):
            pass
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    run = service.get_run(response.run_id)

    assert run is not None
    progress_outputs = [
        event.payload["output"]
        for event in run.events
        if event.type == "output_emitted" and event.payload["output"].format == "progress"
    ]
    assert len(progress_outputs) == 2
    assert progress_outputs[0].metadata["state"] == "started"
    assert progress_outputs[1].metadata["state"] == "finished"
    assert progress_outputs[0].metadata["progress_id"] == progress_outputs[1].metadata["progress_id"]


@patch("titan_cli.engine.runs.service.create_broker_factory")
@patch("titan_cli.engine.runs.service.WorkflowExecutor")
def test_cancel_run_during_resuming_transitions_to_cancelled(
    mock_executor_cls,
    mock_secret_manager_cls,
):
    config = MagicMock()
    workflow = MagicMock(name="workflow")
    config.workflows.discover.return_value = []
    config.workflows.get_workflow.return_value = workflow
    config.project_root = MagicMock()
    config.registry.list_installed.return_value = []
    config.config.ai = None
    mock_secret_manager_cls.return_value = MagicMock()

    first_call = True
    resume_entered = threading.Event()
    allow_resume_to_finish = threading.Event()

    def _execute(_workflow, ctx, params_override=None, start_step_index=0):
        nonlocal first_call
        if first_call:
            first_call = False
            ctx.interaction.ask_text("Enter value", default="demo")
            return Success("unreachable")

        resume_entered.set()
        allow_resume_to_finish.wait(timeout=1.0)
        return Success("workflow ok")

    mock_executor = mock_executor_cls.return_value
    mock_executor.execute.side_effect = _execute

    service = WorkflowRunService(config=config)
    response = service.start_workflow(StartWorkflowRequest(workflow_name="demo"))
    waiting = service.get_run(response.run_id)

    assert waiting is not None
    assert waiting.pending_prompt is not None

    resumed_state = None

    def _resume_run() -> None:
        nonlocal resumed_state
        resumed_state = service.submit_prompt_response(
            SubmitPromptResponseRequest(
                run_id=response.run_id,
                prompt_id=waiting.pending_prompt.prompt_id,
                value="hello",
            )
        )

    resume_thread = threading.Thread(target=_resume_run)
    resume_thread.start()
    assert resume_entered.wait(timeout=1.0)

    in_flight = service.get_run(response.run_id)
    assert in_flight is not None
    assert in_flight.status == RunSessionStatus.RESUMING

    cancelled = service.cancel_run(response.run_id, reason="stop while resuming")
    assert cancelled is not None
    assert cancelled.status == RunSessionStatus.RESUMING

    allow_resume_to_finish.set()
    resume_thread.join(timeout=1.0)

    assert resumed_state is not None
    assert resumed_state.status == RunSessionStatus.CANCELLED
    assert resumed_state.result_message == "stop while resuming"
    assert resumed_state.events[-2].type == "run_cancelled"
    assert resumed_state.events[-1].type == "run_result_emitted"
