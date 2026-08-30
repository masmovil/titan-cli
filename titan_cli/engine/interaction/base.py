"""Base interaction contracts for workflow execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Optional

from titan_cli.external_cli.adapters.base import ExternalCLIActivity

from titan_cli.ports.protocol import ContentBlock
from titan_cli.ports.protocol import ContentBlockType
from titan_cli.ports.protocol import ItemReviewDecision
from titan_cli.ports.protocol import ItemReviewState
from titan_cli.ports.protocol import InteractionOption


@dataclass(slots=True)
class ItemReviewResponse:
    """Resolved aggregated response returned by the semantic item-review interaction."""

    items: list[ItemReviewDecision]
    exit_requested: bool = False


class InteractionPort(ABC):
    """Abstract interaction surface consumed by workflow steps."""

    @abstractmethod
    def info(self, message: str) -> None:
        """Emit a neutral informational message."""

    @abstractmethod
    def warning(self, message: str) -> None:
        """Emit a warning message."""

    @abstractmethod
    def error(self, message: str) -> None:
        """Emit an error message."""

    @abstractmethod
    def step_output(self, text: str) -> None:
        """Emit step output content."""

    def text(self, message: str) -> None:
        """Legacy-compatible alias for plain text output."""
        self.step_output(message)

    def dim_text(self, message: str) -> None:
        """Legacy-compatible alias for low-emphasis text."""
        self.info(message)

    def success_text(self, message: str) -> None:
        """Legacy-compatible alias for success text."""
        self.info(message)

    def error_text(self, message: str) -> None:
        """Legacy-compatible alias for error text."""
        self.error(message)

    def warning_text(self, message: str) -> None:
        """Legacy-compatible alias for warning text."""
        self.warning(message)

    def ai_chip(self, text: str) -> None:
        """Announce the AI route used by a step.

        Textual renders this as a compact chip. Non-visual adapters keep the
        same semantic signal as muted output so steps can depend on one
        interaction contract regardless of the active UI.
        """
        self.dim_text(text)

    def external_cli_activity(
        self,
        activity_id: str,
        activity: ExternalCLIActivity,
    ) -> None:
        """Receive replaceable activity from an unattended external CLI call.

        Visual adapters may render this as one live status surface. The base
        implementation intentionally stays silent so heartbeat updates do not
        become an ever-growing transcript.
        """

    def cancellation_requested(self) -> bool:
        """Whether the active workflow run requested cooperative cancellation."""
        return False

    def bold_text(self, message: str) -> None:
        """Legacy-compatible alias for emphasized text output."""
        self.step_output(message)

    def bold_primary_text(self, message: str) -> None:
        """Legacy-compatible alias for emphasized primary text output."""
        self.step_output(message)

    def primary_text(self, message: str) -> None:
        """Legacy-compatible alias for primary text output."""
        self.step_output(message)

    def markdown(self, markdown_text: str) -> None:
        """Render markdown-capable output in the current UI."""
        self.step_output(markdown_text)

    def panel(
        self,
        text: str,
        *,
        panel_type: str = "info",
        show_icon: bool = True,
        use_markdown: bool = False,
    ) -> None:
        """Render a semantic panel without requiring a concrete UI toolkit."""
        if use_markdown:
            self.markdown(text)
        else:
            self.step_output(text)

    def table(
        self,
        headers: list[str],
        rows: list[list[str]],
        title: str = "",
        **_: Any,
    ) -> None:
        """Render a tabular result in a portable interaction adapter."""
        if title:
            self.step_output(title)
        if headers:
            self.step_output(" | ".join(headers))
        for row in rows:
            self.step_output(" | ".join(str(cell) for cell in row))

    def mount(self, widget: Any) -> None:
        """Compatibility hook for toolkit-only widgets.

        Portable adapters cannot serialize arbitrary UI widgets. Workflow steps
        should use semantic methods such as ``panel`` or ``table`` for content
        that must be consumed by another UI.
        """

    def display_diff(
        self,
        diff_text: str,
        *,
        title: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Render diff-oriented output in the current UI."""
        if title:
            self.step_output(title)

        summary_lines = metadata.get("summary_lines", []) if metadata else []
        if summary_lines:
            for line in summary_lines:
                self.step_output(str(line))
            return

        self.step_output(diff_text)

    def display_structured_summary(
        self,
        *,
        title: str,
        summary_lines: list[str],
        sections: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Render compact structured summary output in the current UI."""
        self.step_output(title)
        for line in summary_lines:
            self.step_output(line)

        for section in sections:
            section_title = str(section.get("title") or "").strip()
            if section_title:
                self.step_output(section_title)
            for line in section.get("lines", []) or []:
                self.step_output(str(line))

    def display_content_block(self, block: ContentBlock) -> None:
        """Render a reusable semantic content block in the current UI."""
        if block.type == ContentBlockType.TEXT:
            if block.title:
                self.step_output(block.title)
            self.step_output(block.content)
            return

        if block.type == ContentBlockType.MARKDOWN:
            if block.title:
                self.step_output(block.title)
            self.markdown(block.content)
            return

        if block.type == ContentBlockType.DIFF:
            self.display_diff(block.content, title=block.title, metadata=block.metadata)
            return

        if block.type == ContentBlockType.STRUCTURED_SUMMARY:
            metadata = block.metadata or {}
            self.display_structured_summary(
                title=block.title or "Summary",
                summary_lines=list(metadata.get("summary_lines") or [block.content]),
                sections=list(metadata.get("sections") or []),
                metadata=metadata,
            )
            return

        if block.title:
            self.step_output(block.title)
        self.step_output(block.content)

    def begin_step(self, step_name: str) -> None:
        """Hook called when a step starts."""

    def end_step(self, result_type: str) -> None:
        """Hook called when a step ends."""

    def confirm(self, prompt_id: str, message: str, default: bool = False) -> bool:
        """Request a confirmation from the current UI client."""
        raise NotImplementedError("confirm is not implemented for this interaction port")

    def input_text(
        self,
        prompt_id: str,
        message: str,
        default: str | None = None,
    ) -> str:
        """Request text input from the current UI client."""
        raise NotImplementedError("input_text is not implemented for this interaction port")

    def multiline_text(
        self,
        prompt_id: str,
        message: str,
        default: str | None = None,
    ) -> str:
        """Request multiline input from the current UI client."""
        return self.input_text(prompt_id=prompt_id, message=message, default=default)

    def ask_confirm(self, message: str, default: bool = False) -> bool:
        """Legacy-compatible confirmation API."""
        return self.confirm(prompt_id="confirm", message=message, default=default)

    def ask_text(self, message: str, default: str = "") -> str:
        """Legacy-compatible single-line prompt API."""
        return self.input_text(prompt_id="text", message=message, default=default)

    def ask_multiline(self, message: str, default: str = "") -> str:
        """Legacy-compatible multiline prompt API."""
        return self.multiline_text(prompt_id="multiline", message=message, default=default)

    def ask_multiselect(self, message: str, options: list[Any]) -> list[Any]:
        """Legacy-compatible multiselect API.

        Headless execution cannot display an interactive picker, so default to the
        options already marked as selected. If the option shape is unknown, use
        its value when present and otherwise the option itself.
        """
        raise NotImplementedError("ask_multiselect is not implemented for this interaction port")

    def show_diff_stat(
        self,
        formatted_files: list[str],
        formatted_summary: list[str],
        title: str,
        use_panel: bool = False,
    ) -> None:
        """Legacy-compatible diff renderer for non-Textual execution."""
        self.step_output(title)
        for line in formatted_files:
            self.step_output(line)
        for line in formatted_summary:
            self.step_output(line)

    def loading(self, message: str):
        """Legacy-compatible loading context manager."""
        self.info(message)
        return nullcontext()

    def select_one(
        self,
        prompt_id: str,
        message: str,
        options: list[dict[str, Any]],
    ) -> str:
        """Request a single-choice selection from the current UI client."""
        raise NotImplementedError("select_one is not implemented for this interaction port")

    def option_list(
        self,
        interaction_id: str,
        message: str,
        options: list[Any],
    ) -> Any:
        """Request a richer single selection from the current UI client."""
        raise NotImplementedError("option_list is not implemented for this interaction port")

    def item_review(
        self,
        interaction_id: str,
        message: str,
        state: ItemReviewState,
    ) -> ItemReviewResponse:
        """Review a full item collection and return the aggregated final result."""
        if message:
            self.info(message)

        decisions: list[ItemReviewDecision] = []
        items = state.items
        if not items:
            return ItemReviewResponse(items=[])

        start_index = max(0, min(state.initial_index, len(items) - 1))
        for index, item in enumerate(items[start_index:], start=start_index):
            self.step_output(f"{item.title} ({index + 1}/{len(items)})")
            if item.status:
                self.info(f"Status: {item.status}")
            for block in item.content_blocks:
                self.display_content_block(block)

            options = [
                {
                    "id": action,
                    "label": action.replace("_", " ").title(),
                    "description": None,
                }
                for action in state.allowed_actions
            ]
            if not options:
                raise NotImplementedError("item_review requires at least one allowed action")

            selected = self.select_one(
                prompt_id=f"{interaction_id}:{item.id}:action",
                message="Choose an action:",
                options=options,
            )
            action = str(selected or "skip")
            if action == "edit" and state.edit and state.edit.enabled and item.editable:
                edited = self.multiline_text(
                    prompt_id=f"{interaction_id}:{item.id}:edit",
                    message=state.edit.label or "Edit item content:",
                    default=state.edit.initial_value or (item.content_blocks[0].content if item.content_blocks else ""),
                )
                decisions.append(ItemReviewDecision(item_id=item.id, action="edit", content=edited))
                continue

            if action == "exit":
                return ItemReviewResponse(items=decisions, exit_requested=True)

            decisions.append(ItemReviewDecision(item_id=item.id, action=action))

        return ItemReviewResponse(items=decisions, exit_requested=False)

    def ask_option(self, message: str, options: list[Any]) -> Any:
        """Legacy-compatible rich single-selection API.

        Older steps still pass `OptionItem`-style objects with `title`,
        `description`, and `value`. Map them into the semantic option-list
        capability so headless and future adapters do not need Textual-specific
        methods.
        """
        semantic_options = [
            InteractionOption(
                id=str(index),
                label=str(getattr(option, "title", getattr(option, "label", option))),
                value=getattr(option, "value", option),
                description=getattr(option, "description", None),
            )
            for index, option in enumerate(options, start=1)
        ]
        return self.option_list(
            interaction_id="select-option",
            message=message,
            options=semantic_options,
        )

    def ask_choice(self, message: str, options: list[Any]) -> Any:
        """Legacy-compatible single-choice API used by button-style prompts."""
        return self.ask_option(message, options)
