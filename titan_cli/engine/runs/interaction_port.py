"""Headless interaction port that mirrors workflow activity into V1 events."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Optional

from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.interaction.base import ItemReviewResponse
from titan_cli.engine.interaction.headless import HeadlessInteractionPort
from titan_cli.engine.runs.projection import normalize_step_status
from titan_cli.engine.runs.session import RunSession
from titan_cli.ports.protocol import ContentBlockVariant
from titan_cli.ports.protocol import EventType
from titan_cli.ports.protocol import InteractionAction
from titan_cli.ports.protocol import InteractionOption
from titan_cli.ports.protocol import InteractionRequest
from titan_cli.ports.protocol import InteractionType
from titan_cli.ports.protocol import ItemReviewDecision
from titan_cli.ports.protocol import ItemReviewState
from titan_cli.ports.protocol import OutputFormat
from titan_cli.ports.protocol import OutputPayload
from titan_cli.ports.protocol import PromptRequest
from titan_cli.ports.protocol import PromptType
from titan_cli.ports.protocol import RunStepStatus
from titan_cli.ports.protocol import StepRef

if TYPE_CHECKING:
    from titan_cli.engine.runs.service import WorkflowRunService


class PromptRequestedError(BaseException):
    """Raised when workflow execution requires a structured prompt response."""

    def __init__(self, prompt: PromptRequest) -> None:
        super().__init__(prompt.message)
        self.prompt = prompt


class InteractionRequestedError(BaseException):
    """Raised when workflow execution requires a structured interaction response."""

    def __init__(self, interaction: InteractionRequest) -> None:
        super().__init__(interaction.message or interaction.interaction_id)
        self.interaction = interaction


class RunInteractionPort(HeadlessInteractionPort):
    """Headless interaction port that mirrors workflow activity into V1 events."""

    def __init__(
        self,
        service: "WorkflowRunService",
        session: RunSession,
        ctx: WorkflowContext,
        queued_prompt_responses: Optional[list[object]] = None,
        queued_interaction_responses: Optional[list[dict[str, object]]] = None,
        resume_step_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._session = session
        self._ctx = ctx
        self._queued_prompt_responses = queued_prompt_responses or []
        self._queued_interaction_responses = queued_interaction_responses or []
        self._resume_step_id = resume_step_id
        self._suppress_replayed_prefix = bool(
            resume_step_id and (self._queued_prompt_responses or self._queued_interaction_responses)
        )
        self._progress_counter = 0

    def step_output(self, text: str) -> None:
        super().step_output(text)
        self._emit_text_output(text, variant=ContentBlockVariant.DEFAULT)

    def info(self, message: str) -> None:
        super().info(message)
        self._emit_text_output(message, variant=ContentBlockVariant.DEFAULT)

    def warning(self, message: str) -> None:
        super().warning(message)
        self._emit_text_output(message, variant=ContentBlockVariant.WARNING)

    def error(self, message: str) -> None:
        super().error(message)
        self._emit_text_output(message, variant=ContentBlockVariant.ERROR)

    def success_text(self, message: str) -> None:
        HeadlessInteractionPort.info(self, message)
        self._emit_text_output(message, variant=ContentBlockVariant.SUCCESS)

    def dim_text(self, message: str) -> None:
        HeadlessInteractionPort.info(self, message)
        self._emit_text_output(message, variant=ContentBlockVariant.MUTED)

    def _emit_text_output(self, text: str, *, variant: ContentBlockVariant) -> None:
        if self._suppress_replayed_prefix:
            return
        self._service._append_event(
            self._session,
            EventType.OUTPUT_EMITTED,
            {
                "step": self._step_ref(),
                "output": OutputPayload(
                    format=OutputFormat.TEXT,
                    content=text,
                    metadata={"variant": variant.value},
                ),
            },
        )

    def markdown(self, markdown_text: str) -> None:
        self.messages.append(("markdown", markdown_text))
        if self._suppress_replayed_prefix:
            return
        self._service._append_event(
            self._session,
            EventType.OUTPUT_EMITTED,
            {
                "step": self._step_ref(),
                "output": OutputPayload(
                    format=OutputFormat.MARKDOWN,
                    title="Markdown output",
                    content=markdown_text,
                ),
            },
        )

    @contextmanager
    def loading(self, message: str):
        """Emit a transient progress lifecycle for long-running operations."""
        self._progress_counter += 1
        progress_id = f"{self._ctx.current_step_id or 'step'}:progress:{self._progress_counter}"
        self._emit_progress_output(
            progress_id=progress_id,
            state="started",
            message=message,
            variant=ContentBlockVariant.DEFAULT,
        )
        try:
            yield
        except Exception:
            self._emit_progress_output(
                progress_id=progress_id,
                state="failed",
                message=message,
                variant=ContentBlockVariant.ERROR,
            )
            raise
        else:
            self._emit_progress_output(
                progress_id=progress_id,
                state="finished",
                message=message,
                variant=ContentBlockVariant.SUCCESS,
            )

    def _emit_progress_output(
        self,
        *,
        progress_id: str,
        state: str,
        message: str,
        variant: ContentBlockVariant,
    ) -> None:
        if self._suppress_replayed_prefix:
            return
        self._service._append_event(
            self._session,
            EventType.OUTPUT_EMITTED,
            {
                "step": self._step_ref(),
                "output": OutputPayload(
                    format=OutputFormat.PROGRESS,
                    content=message,
                    metadata={
                        "progress_id": progress_id,
                        "state": state,
                        "indeterminate": True,
                        "variant": variant.value,
                    },
                ),
            },
        )

    def display_diff(
        self,
        diff_text: str,
        *,
        title: str | None = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.messages.append(("diff", diff_text))
        if self._suppress_replayed_prefix:
            return
        self._service._append_event(
            self._session,
            EventType.OUTPUT_EMITTED,
            {
                "step": self._step_ref(),
                "output": OutputPayload(
                    format=OutputFormat.DIFF,
                    title=title,
                    content=diff_text,
                    metadata=metadata or {},
                ),
            },
        )

    def display_structured_summary(
        self,
        *,
        title: str,
        summary_lines: list[str],
        sections: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        payload_metadata = dict(metadata or {})
        payload_metadata.setdefault("summary_lines", list(summary_lines))
        payload_metadata.setdefault("sections", list(sections))
        self.messages.append(("structured_summary", title))
        self._service._append_event(
            self._session,
            EventType.OUTPUT_EMITTED,
            {
                "step": self._step_ref(),
                "output": OutputPayload(
                    format=OutputFormat.STRUCTURED_SUMMARY,
                    title=title,
                    content="\n".join(summary_lines),
                    metadata=payload_metadata,
                ),
            },
        )

    def begin_step(self, step_name: str) -> None:
        super().begin_step(step_name)
        if self._suppress_replayed_prefix and self._ctx.current_step_id == self._resume_step_id:
            return
        self._service._append_event(
            self._session,
            EventType.STEP_STARTED,
            {
                "step": self._step_ref(step_name=step_name),
                "plugin": self._ctx.current_step_plugin,
                "step_kind": self._ctx.current_step_kind or "plugin",
            },
        )

    def end_step(self, result_type: str) -> None:
        super().end_step(result_type)
        if self._suppress_replayed_prefix:
            return
        normalized = normalize_step_status(result_type)

        if normalized == RunStepStatus.SUCCESS:
            self._service._append_event(
                self._session,
                EventType.STEP_FINISHED,
                {
                    "step": self._step_ref(),
                    "status": RunStepStatus.SUCCESS,
                    "message": result_type,
                    "metadata": {},
                },
            )
            return

        self._service._append_event(
            self._session,
            EventType.STEP_SKIPPED if normalized == RunStepStatus.SKIPPED else EventType.STEP_FAILED,
            {
                "step": self._step_ref(),
                "message": result_type,
            },
        )

    def confirm(self, prompt_id: str, message: str, default: bool = False) -> bool:
        value = self._request_prompt(
            prompt_type=PromptType.CONFIRM,
            prompt_id=prompt_id,
            message=message,
            default=default,
        )
        return bool(value)

    def input_text(
        self,
        prompt_id: str,
        message: str,
        default: str | None = None,
    ) -> str:
        value = self._request_prompt(
            prompt_type=PromptType.TEXT,
            prompt_id=prompt_id,
            message=message,
            default=default,
        )
        return "" if value is None else str(value)

    def multiline_text(
        self,
        prompt_id: str,
        message: str,
        default: str | None = None,
    ) -> str:
        value = self._request_prompt(
            prompt_type=PromptType.MULTILINE,
            prompt_id=prompt_id,
            message=message,
            default=default,
        )
        return "" if value is None else str(value)

    def _request_prompt(
        self,
        prompt_type: PromptType,
        prompt_id: str,
        message: str,
        default: object = None,
    ) -> object:
        full_prompt_id = (
            f"{self._ctx.current_step_id}:{prompt_id}"
            if self._ctx.current_step_id
            else prompt_id
        )
        prompt = PromptRequest(
            prompt_id=full_prompt_id,
            prompt_type=prompt_type,
            message=message,
            default=default,
        )
        if self._queued_prompt_responses:
            value = self._queued_prompt_responses.pop(0)
            self._session.record_prompt_answer(prompt, value)
            if self._suppress_replayed_prefix and self._ctx.current_step_id == self._resume_step_id:
                self._suppress_replayed_prefix = False
            return value

        self._session.pending_prompt = prompt
        self._service._append_event(
            self._session,
            EventType.PROMPT_REQUESTED,
            {
                "step": self._step_ref(),
                "prompt": prompt,
            },
        )
        raise PromptRequestedError(prompt)

    def option_list(
        self,
        interaction_id: str,
        message: str,
        options: list[InteractionOption],
    ) -> object:
        interaction = self._build_interaction_request(
            interaction_id=interaction_id,
            interaction_type=InteractionType.OPTION_LIST,
            message=message,
            state={
                "options": options,
                "allow_empty": False,
            },
        )
        response = self._request_interaction(interaction)
        return self._resolve_interaction_value(interaction, response)

    def item_review(
        self,
        interaction_id: str,
        message: str,
        state: ItemReviewState,
    ) -> ItemReviewResponse:
        interaction = self._build_interaction_request(
            interaction_id=interaction_id,
            interaction_type=InteractionType.ITEM_REVIEW,
            message=message,
            state={
                "review_id": state.review_id,
                "items": list(state.items),
                "initial_index": state.initial_index,
                "allowed_actions": list(state.allowed_actions),
                "edit": state.edit,
                "metadata": dict(state.metadata),
            },
            actions=[
                InteractionAction(id=action, label=action.replace("_", " ").title())
                for action in state.allowed_actions
            ],
        )
        response = self._request_interaction(interaction)
        return self._resolve_interaction_value(interaction, response)

    def _build_interaction_request(
        self,
        *,
        interaction_id: str,
        interaction_type: InteractionType,
        message: str,
        state: dict[str, Any],
        actions: Optional[list[InteractionAction]] = None,
    ) -> InteractionRequest:
        full_interaction_id = (
            f"{self._ctx.current_step_id}:{interaction_id}"
            if self._ctx.current_step_id
            else interaction_id
        )
        return InteractionRequest(
            interaction_id=full_interaction_id,
            interaction_type=interaction_type,
            message=message,
            state=state,
            actions=actions or [],
        )

    def _request_interaction(self, interaction: InteractionRequest) -> dict[str, object]:
        if self._queued_interaction_responses:
            response = self._queued_interaction_responses.pop(0)
            self._session.record_interaction_answer(interaction, response)
            if self._suppress_replayed_prefix and self._ctx.current_step_id == self._resume_step_id:
                self._suppress_replayed_prefix = False
            return response

        self._session.pending_interaction = interaction
        self._service._append_event(
            self._session,
            EventType.INTERACTION_REQUESTED,
            {
                "step": self._step_ref(),
                "interaction": interaction,
            },
        )
        raise InteractionRequestedError(interaction)

    def _resolve_interaction_value(
        self,
        interaction: InteractionRequest,
        response: dict[str, object],
    ) -> object:
        """Resolve the semantic interaction response into the value a step expects."""
        if interaction.interaction_type == InteractionType.OPTION_LIST:
            selected_id = response.get("value")
            options = interaction.state.get("options") or []
            for option in options:
                if isinstance(option, InteractionOption) and option.id == selected_id:
                    return option.value if option.value is not None else option.id
            return selected_id
        if interaction.interaction_type == InteractionType.ITEM_REVIEW:
            response_type = str(response.get("response_type") or "")
            if response_type != "complete":
                raise ValueError(f"Unsupported item_review response_type: {response_type or 'empty'}")
            value = response.get("value")
            if not isinstance(value, dict):
                return ItemReviewResponse(items=[])
            raw_items = value.get("items")
            decisions: list[ItemReviewDecision] = []
            if isinstance(raw_items, list):
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    item_id = item.get("item_id")
                    action = item.get("action")
                    if item_id is None or action is None:
                        continue
                    decisions.append(
                        ItemReviewDecision(
                            item_id=str(item_id),
                            action=str(action),
                            content=None if item.get("content") is None else str(item.get("content")),
                            metadata=dict(item.get("metadata") or {}),
                        )
                    )
            return ItemReviewResponse(
                items=decisions,
                exit_requested=bool(value.get("exit_requested", False)),
            )
        return response.get("value")

    def _step_ref(self, step_name: Optional[str] = None) -> StepRef:
        return StepRef(
            step_id=self._ctx.current_step_id or "step",
            step_name=step_name or self._ctx.current_step_name or "Step",
            step_index=self._ctx.current_step or 0,
        )
