"""Headless interaction port that mirrors workflow activity into V1 events."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Optional

from titan_cli.engine.context import WorkflowContext
from titan_cli.external_cli.adapters.base import ExternalCLIActivity
from titan_cli.external_cli.adapters.base import ExternalCLIActivityPhase
from titan_cli.engine.interaction.base import EditableTextResponse, ItemReviewResponse
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
        self._is_resuming = resume_step_id is not None
        self._suppress_replayed_prefix = bool(
            resume_step_id and (self._queued_prompt_responses or self._queued_interaction_responses)
        )
        self._progress_counter = 0

    def stream_output(self, text: str) -> None:
        """Emit output produced by a streaming toolkit widget."""
        self._emit_text_output(
            text,
            variant=ContentBlockVariant.MUTED,
            metadata={"presentation": "stream"},
        )

    def secret_text(self, prompt_id: str, message: str) -> str:
        value = self._request_prompt(
            prompt_type=PromptType.SECRET,
            prompt_id=prompt_id,
            message=message,
        )
        return "" if value is None else str(value)

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

    def ai_chip(self, text: str) -> None:
        HeadlessInteractionPort.ai_chip(self, text)
        self._emit_text_output(
            text,
            variant=ContentBlockVariant.MUTED,
            metadata={"presentation": "ai_chip"},
        )

    def external_cli_activity(
        self,
        activity_id: str,
        activity: ExternalCLIActivity,
    ) -> None:
        """Mirror provider activity as one correlatable progress lifecycle."""
        terminal_state = {
            ExternalCLIActivityPhase.COMPLETED: "finished",
            ExternalCLIActivityPhase.TIMED_OUT: "timed_out",
            ExternalCLIActivityPhase.FAILED: "failed",
            ExternalCLIActivityPhase.CANCELLED: "cancelled",
        }
        state = terminal_state.get(activity.phase, "running")
        variant = {
            "finished": ContentBlockVariant.SUCCESS,
            "timed_out": ContentBlockVariant.WARNING,
            "failed": ContentBlockVariant.ERROR,
            "cancelled": ContentBlockVariant.WARNING,
        }.get(state, ContentBlockVariant.DEFAULT)
        metadata = {
            "progress_id": f"external-cli:{activity_id}",
            "state": state,
            "indeterminate": state == "running",
            "variant": variant.value,
            "provider": activity.provider.value,
            "phase": activity.phase.value,
            "elapsed_seconds": round(activity.elapsed_seconds, 1),
            "idle_seconds": round(activity.idle_seconds, 1),
        }
        if activity.activity_kind:
            metadata["activity_kind"] = activity.activity_kind
        metadata.update(activity.metadata or {})
        self._emit_output_payload(
            OutputPayload(
                format=OutputFormat.PROGRESS,
                title=f"{activity.provider.value.capitalize()} activity",
                content=activity.message,
                metadata=metadata,
            )
        )

    def cancellation_requested(self) -> bool:
        return bool(self._session.metadata.get("cancel_requested"))

    def panel(
        self,
        text: str,
        *,
        panel_type: str = "info",
        show_icon: bool = True,
        use_markdown: bool = False,
    ) -> None:
        """Emit a panel as content with a semantic visual variant."""
        variant = {
            "success": ContentBlockVariant.SUCCESS,
            "warning": ContentBlockVariant.WARNING,
            "error": ContentBlockVariant.ERROR,
        }.get(panel_type, ContentBlockVariant.DEFAULT)
        if use_markdown:
            self._emit_output_payload(
                OutputPayload(
                    format=OutputFormat.MARKDOWN,
                    content=text,
                    metadata={"variant": variant.value, "presentation": "panel", "show_icon": show_icon},
                )
            )
            return
        self._emit_text_output(
            text,
            variant=variant,
            metadata={"presentation": "panel", "panel_type": panel_type, "show_icon": show_icon},
        )

    def table(
        self,
        headers: list[str],
        rows: list[list[str]],
        title: str = "",
        **_: Any,
    ) -> None:
        """Emit table data instead of relying on Textual's widget renderer."""
        self._emit_output_payload(
            OutputPayload(
                format=OutputFormat.TABLE,
                title=title or None,
                content="\n".join(" | ".join(str(cell) for cell in row) for row in rows),
                metadata={"headers": list(headers), "rows": [list(row) for row in rows]},
            )
        )

    def mount(self, widget: Any) -> None:
        """Reject toolkit widgets so headless never loses workflow output silently."""
        raise TypeError(
            "Headless workflows cannot mount UI widgets; use a semantic interaction method"
        )

    def _emit_text_output(
        self,
        text: str,
        *,
        variant: ContentBlockVariant,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        output_metadata = {"variant": variant.value}
        output_metadata.update(metadata or {})
        self._emit_output_payload(
            OutputPayload(
                format=OutputFormat.TEXT,
                content=text,
                metadata=output_metadata,
            )
        )

    def _emit_output_payload(self, output: OutputPayload) -> None:
        if self._suppress_replayed_prefix:
            return
        self._service._append_event(
            self._session,
            EventType.OUTPUT_EMITTED,
            {
                "step": self._step_ref(),
                "output": output,
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
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "y", "1"}:
                return True
            if normalized in {"false", "no", "n", "0", ""}:
                return False
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
            if not self._is_resuming:
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

    def select_one(
        self,
        prompt_id: str,
        message: str,
        options: list[dict[str, Any]],
    ) -> str:
        selected = self.option_list(
            interaction_id=prompt_id,
            message=message,
            options=[
                InteractionOption(
                    id=str(option.get("id") or index),
                    label=str(option.get("label") or option.get("id") or "Option"),
                    value=option.get("value", option.get("id")),
                    description=option.get("description"),
                )
                for index, option in enumerate(options, start=1)
            ],
        )
        return "" if selected is None else str(selected)

    def action_list(
        self,
        interaction_id: str,
        message: str,
        actions: list[InteractionAction],
        *,
        state: Optional[dict[str, Any]] = None,
    ) -> str:
        interaction = self._build_interaction_request(
            interaction_id=interaction_id,
            interaction_type=InteractionType.ACTION_LIST,
            message=message,
            state=dict(state or {}),
            actions=actions,
        )
        response = self._request_interaction(interaction)
        value = self._resolve_interaction_value(interaction, response)
        return "" if value is None else str(value)

    def editable_text(
        self,
        interaction_id: str,
        message: str,
        *,
        title: str,
        content: str,
        title_label: str = "Title",
        content_label: str = "Content",
        actions: Optional[list[InteractionAction]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> EditableTextResponse:
        interaction = self._build_interaction_request(
            interaction_id=interaction_id,
            interaction_type=InteractionType.EDITABLE_TEXT,
            message=message,
            state={
                "title": title,
                "content": content,
                "title_label": title_label,
                "content_label": content_label,
                "metadata": dict(metadata or {}),
            },
            actions=actions or [
                InteractionAction(id="use", label="Use", variant="primary"),
                InteractionAction(id="edit", label="Edit"),
                InteractionAction(id="reject", label="Reject", variant="warning"),
            ],
        )
        response = self._request_interaction(interaction)
        value = self._resolve_interaction_value(interaction, response)
        if not isinstance(value, dict):
            return EditableTextResponse(action=str(value or "reject"), title=title, content=content)
        return EditableTextResponse(
            action=str(value.get("action") or "use"),
            title=str(value.get("title") or title),
            content=str(value.get("content") or content),
        )

    def batch_progress(
        self,
        progress_id: str,
        message: str,
        *,
        completed: int,
        total: int,
        state: str = "running",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        progress_metadata = {
            "progress_id": f"batch:{progress_id}",
            "state": state,
            "completed": completed,
            "total": total,
            "indeterminate": total <= 0,
            "interaction_type": InteractionType.BATCH_PROGRESS.value,
        }
        progress_metadata.update(metadata or {})
        self._emit_output_payload(
            OutputPayload(
                format=OutputFormat.PROGRESS,
                title="Batch progress",
                content=message,
                metadata=progress_metadata,
            )
        )

    def external_cli_session(
        self,
        interaction_id: str,
        *,
        cli_name: str,
        prompt: str,
        cwd: str,
    ) -> int:
        interaction = self._build_interaction_request(
            interaction_id=interaction_id,
            interaction_type=InteractionType.EXTERNAL_CLI_SESSION,
            message=f"Open {cli_name} to continue this workflow.",
            state={
                "cli_name": cli_name,
                "prompt": prompt,
                "cwd": cwd,
                "presentation": "external_cli_session",
            },
            actions=[
                InteractionAction(id="complete", label="Session completed", variant="primary"),
                InteractionAction(id="cancel", label="Cancel", variant="warning"),
            ],
        )
        response = self._request_interaction(interaction)
        value = self._resolve_interaction_value(interaction, response)
        if isinstance(value, dict):
            return int(value.get("exit_code", 1))
        return int(value or 0)

    def ask_multiselect(self, message: str, options: list[Any]) -> list[Any]:
        """Expose legacy checkbox prompts as a portable multi-select interaction."""
        semantic_options = [
            InteractionOption(
                id=str(index),
                label=str(getattr(option, "label", getattr(option, "title", option))),
                value=getattr(option, "value", option),
                description=getattr(option, "description", None),
                badges=["selected"]
                if (
                    getattr(option, "selected", False)
                    or "selected" in getattr(option, "badges", [])
                )
                else [],
            )
            for index, option in enumerate(options, start=1)
        ]
        interaction = self._build_interaction_request(
            interaction_id="select-options",
            interaction_type=InteractionType.OPTION_LIST,
            message=message,
            state={
                "options": semantic_options,
                "selection_mode": "multiple",
                "allow_empty": True,
            },
        )
        response = self._request_interaction(interaction)
        value = self._resolve_interaction_value(interaction, response)
        return list(value) if isinstance(value, list) else ([] if value is None else [value])

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
            if not self._is_resuming:
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
            if interaction.state.get("selection_mode") == "multiple":
                selected_values = selected_id if isinstance(selected_id, list) else []
                resolved: list[object] = []
                for selected in selected_values:
                    for option in options:
                        if not isinstance(option, InteractionOption):
                            continue
                        option_value = option.value if option.value is not None else option.id
                        if option.id == selected or str(option_value) == str(selected):
                            resolved.append(option_value)
                            break
                return resolved
            for option in options:
                if not isinstance(option, InteractionOption):
                    continue
                option_value = option.value if option.value is not None else option.id
                if option.id == selected_id or str(option_value) == str(selected_id):
                    return option_value
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
        if interaction.interaction_type == InteractionType.ACTION_LIST:
            return response.get("value")
        if interaction.interaction_type == InteractionType.EDITABLE_TEXT:
            return response.get("value")
        if interaction.interaction_type == InteractionType.EXTERNAL_CLI_SESSION:
            return response.get("value")
        return response.get("value")

    def _step_ref(self, step_name: Optional[str] = None) -> StepRef:
        return StepRef(
            step_id=self._ctx.current_step_id or "step",
            step_name=step_name or self._ctx.current_step_name or "Step",
            step_index=self._ctx.current_step or 0,
        )
