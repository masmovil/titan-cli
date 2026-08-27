"""Projection of run session events into terminal V1 protocol snapshots."""

from __future__ import annotations

from typing import Any, Optional

from titan_cli.engine.runs.session import RunSession
from titan_cli.engine.runs.status import RunSessionStatus, TERMINAL_SESSION_STATUSES
from titan_cli.ports.protocol import EventType
from titan_cli.ports.protocol import OutputPayload
from titan_cli.ports.protocol import RunResult
from titan_cli.ports.protocol import RunStatus
from titan_cli.ports.protocol import RunStepResult
from titan_cli.ports.protocol import RunStepStatus
from titan_cli.ports.protocol import StepRef


def result_for_session(session: RunSession) -> RunResult | None:
    """Return the terminal RunResult only for terminal session states."""
    if session.status not in TERMINAL_SESSION_STATUSES:
        return None
    return build_run_result(session)


def build_run_result(session: RunSession) -> RunResult:
    """Build the terminal V1 run snapshot from structured run events."""
    steps: list[RunStepResult] = []
    step_by_id: dict[str, RunStepResult] = {}
    final_output: OutputPayload | None = None
    last_step: RunStepResult | None = None

    for event in session.events:
        payload = event.payload

        if event.type == EventType.STEP_STARTED:
            step = payload.get("step")
            if not isinstance(step, StepRef):
                continue

            existing_step = step_by_id.get(step.step_id)
            if existing_step is not None:
                existing_step.title = step.step_name
                existing_step.plugin = _optional_str(payload.get("plugin"))
                existing_step.status = RunStepStatus.SUCCESS
                existing_step.error = None
                existing_step.outputs.clear()
                existing_step.metadata = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"step", "plugin"}
                }
                last_step = existing_step
                continue

            current_step = RunStepResult(
                id=step.step_id,
                title=step.step_name,
                status=RunStepStatus.SUCCESS,
                plugin=_optional_str(payload.get("plugin")),
                metadata={
                    key: value
                    for key, value in payload.items()
                    if key not in {"step", "plugin"}
                },
            )
            steps.append(current_step)
            step_by_id[step.step_id] = current_step
            last_step = current_step
            continue

        step = payload.get("step")
        current_step = _lookup_step(step_by_id, step)

        if event.type == EventType.STEP_FINISHED:
            if current_step is not None:
                current_step.status = RunStepStatus.SUCCESS
            continue

        if event.type == EventType.STEP_FAILED:
            if current_step is not None:
                current_step.status = RunStepStatus.FAILED
                current_step.error = _optional_str(payload.get("message"))
            continue

        if event.type == EventType.STEP_SKIPPED:
            if current_step is not None:
                current_step.status = RunStepStatus.SKIPPED
            continue

        if event.type == EventType.OUTPUT_EMITTED:
            output = payload.get("output")
            if not isinstance(output, OutputPayload):
                continue
            if current_step is not None:
                current_step.outputs.append(output)
            final_output = output
            continue

        if event.type == EventType.RUN_FAILED:
            failed_step = current_step or last_step
            if failed_step is not None and failed_step.status == RunStepStatus.SUCCESS:
                failed_step.status = RunStepStatus.FAILED
                failed_step.error = _optional_str(payload.get("message"))

    return RunResult(
        run_id=session.run_id,
        workflow_name=session.workflow_name,
        status=normalize_run_status(session.status),
        steps=steps,
        result=final_output,
        diagnostics={
            "result_message": session.result_message,
            "pending_prompt_id": (
                session.pending_prompt.prompt_id
                if session.pending_prompt is not None
                else None
            ),
            "pending_interaction_id": (
                session.pending_interaction.interaction_id
                if session.pending_interaction is not None
                else None
            ),
        },
    )


def normalize_run_status(value: RunSessionStatus) -> RunStatus:
    """Return a valid terminal V1 run status."""
    if value == RunSessionStatus.COMPLETED:
        return RunStatus.COMPLETED
    if value == RunSessionStatus.CANCELLED:
        return RunStatus.CANCELLED
    return RunStatus.FAILED


def normalize_step_status(value: object) -> RunStepStatus:
    """Convert engine result labels into terminal V1 step statuses."""
    raw = str(value or "").lower()
    if raw in {"success", "succeeded", "completed", "done"}:
        return RunStepStatus.SUCCESS
    if raw in {"skip", "skipped"}:
        return RunStepStatus.SKIPPED
    return RunStepStatus.FAILED


def count_workflow_steps(workflow: Any) -> int:
    """Count executable non-hook steps for the run_started payload."""
    if workflow is None:
        return 0
    return len([step for step in workflow.steps if not step.get("hook")])


def _lookup_step(
    step_by_id: dict[str, RunStepResult],
    step: object,
) -> RunStepResult | None:
    """Resolve a step result from a StepRef payload."""
    if not isinstance(step, StepRef):
        return None
    return step_by_id.get(step.step_id)


def _optional_str(value: object) -> Optional[str]:
    """Return string values while preserving absent metadata as null."""
    if value is None:
        return None
    return str(value)
