from titan_cli.engine.runs.status import RunSessionStatus
from titan_cli.engine.runs.projection import build_run_result
from titan_cli.engine.runs.session import RunSession
from titan_cli.engine.runs.service import WorkflowRunService
from titan_cli.ports.protocol import EventType
from titan_cli.ports.protocol import OutputPayload
from titan_cli.ports.protocol import StepRef


class EmptyConfig:
    pass


def test_workflow_service_projects_events_into_ui_result():
    service = WorkflowRunService(config=EmptyConfig())
    session = RunSession(
        run_id="run-1",
        workflow_name="analyze-jira-issues",
        status=RunSessionStatus.COMPLETED,
        result_message="done",
    )

    service._append_event(
        session,
        EventType.RUN_STARTED,
        {"workflow_name": "analyze-jira-issues"},
    )
    service._append_event(
        session,
        EventType.STEP_STARTED,
        {
            "step": StepRef(
                step_id="ai_analyze_issue",
                step_name="AI Analyze Issue",
                step_index=1,
            ),
            "plugin": "jira",
        },
    )
    service._append_event(
        session,
        EventType.OUTPUT_EMITTED,
        {
            "step": StepRef(
                step_id="ai_analyze_issue",
                step_name="AI Analyze Issue",
                step_index=1,
            ),
            "output": OutputPayload(
                format="text",
                content="AI Analysis Results",
            ),
        },
    )
    service._append_event(
        session,
        EventType.OUTPUT_EMITTED,
        {
            "step": StepRef(
                step_id="ai_analyze_issue",
                step_name="AI Analyze Issue",
                step_index=1,
            ),
            "output": OutputPayload(
                format="markdown",
                title="Markdown output",
                content="# JIRA Issue Analysis\n\nLooks good.",
            ),
        },
    )
    service._append_event(
        session,
        EventType.STEP_FINISHED,
        {
            "step": StepRef(
                step_id="ai_analyze_issue",
                step_name="AI Analyze Issue",
                step_index=1,
            ),
            "status": "success",
            "message": "done",
            "metadata": {},
        },
    )
    service._append_event(session, EventType.RUN_COMPLETED, {"message": "done"})

    result = build_run_result(session)

    assert result.run_id == "run-1"
    assert result.workflow_name == "analyze-jira-issues"
    assert result.status == "completed"
    assert len(result.steps) == 1
    assert result.steps[0].id == "ai_analyze_issue"
    assert result.steps[0].title == "AI Analyze Issue"
    assert result.steps[0].status == "success"
    assert result.steps[0].plugin == "jira"
    assert [output.format for output in result.steps[0].outputs] == ["text", "markdown"]
    assert result.result is not None
    assert result.result.format == "markdown"


def test_workflow_service_marks_running_step_failed_from_workflow_failure():
    service = WorkflowRunService(config=EmptyConfig())
    session = RunSession(
        run_id="run-2",
        workflow_name="demo",
        status=RunSessionStatus.FAILED,
        result_message="boom",
    )

    service._append_event(
        session,
        EventType.STEP_STARTED,
        {
            "step": StepRef(
                step_id="explode",
                step_name="Explode",
                step_index=1,
            )
        },
    )
    service._append_event(session, EventType.RUN_FAILED, {"message": "boom"})

    result = build_run_result(session)

    assert result.steps[0].status == "failed"
    assert result.steps[0].error == "boom"


def test_workflow_service_projects_diff_output_metadata_into_terminal_result():
    service = WorkflowRunService(config=EmptyConfig())
    session = RunSession(
        run_id="run-3",
        workflow_name="review-pr",
        status=RunSessionStatus.COMPLETED,
        result_message="done",
    )

    service._append_event(
        session,
        EventType.STEP_STARTED,
        {
            "step": StepRef(
                step_id="fetch_bundle",
                step_name="Fetch PR Review Bundle",
                step_index=1,
            )
        },
    )
    service._append_event(
        session,
        EventType.OUTPUT_EMITTED,
        {
            "step": StepRef(
                step_id="fetch_bundle",
                step_name="Fetch PR Review Bundle",
                step_index=1,
            ),
            "output": OutputPayload(
                format="diff",
                title="Files affected:",
                content="diff --git a/foo.py b/foo.py",
                metadata={
                    "kind": "unified_patch",
                    "summary_lines": ["1 file changed, 1 insertion(+), 0 deletions(-)"],
                },
            ),
        },
    )
    service._append_event(session, EventType.RUN_COMPLETED, {"message": "done"})

    result = build_run_result(session)

    assert result.steps[0].outputs[0].format == "diff"
    assert result.steps[0].outputs[0].metadata["kind"] == "unified_patch"
    assert result.result is not None
    assert result.result.format == "diff"


def test_workflow_service_projects_structured_summary_into_terminal_result():
    service = WorkflowRunService(config=EmptyConfig())
    session = RunSession(
        run_id="run-4",
        workflow_name="review-pr",
        status=RunSessionStatus.COMPLETED,
        result_message="done",
    )

    service._append_event(
        session,
        EventType.STEP_STARTED,
        {
            "step": StepRef(
                step_id="classify_pr",
                step_name="Classify PR",
                step_index=1,
            )
        },
    )
    service._append_event(
        session,
        EventType.OUTPUT_EMITTED,
        {
            "step": StepRef(
                step_id="classify_pr",
                step_name="Classify PR",
                step_index=1,
            ),
            "output": OutputPayload(
                format="structured_summary",
                title="PR Classification",
                content="Size class: MEDIUM\nFiles changed: 12",
                metadata={
                    "kind": "pr_classification",
                    "summary_lines": ["Size class: MEDIUM", "Files changed: 12"],
                    "sections": [
                        {
                            "title": "Scope",
                            "lines": ["Lines changed: 184"],
                        }
                    ],
                },
            ),
        },
    )
    service._append_event(session, EventType.RUN_COMPLETED, {"message": "done"})

    result = build_run_result(session)

    assert result.steps[0].outputs[0].format == "structured_summary"
    assert result.steps[0].outputs[0].metadata["kind"] == "pr_classification"
    assert result.steps[0].outputs[0].metadata["sections"][0]["title"] == "Scope"
    assert result.result is not None
    assert result.result.format == "structured_summary"
