"""Textual-backed interaction adapter."""

from __future__ import annotations

from typing import Any, Optional

from titan_cli.external_cli.adapters.base import ExternalCLIActivity
from titan_cli.ports.protocol import InteractionOption

from .base import EditableTextResponse, InteractionPort


class TextualInteractionPort(InteractionPort):
    """Adapter that exposes Textual components through the generic interaction port."""

    def __init__(self, textual_components) -> None:
        self.legacy = textual_components

    def __getattr__(self, name: str):
        return getattr(self.legacy, name)

    def info(self, message: str) -> None:
        self.legacy.text(message)

    def warning(self, message: str) -> None:
        self.legacy.warning_text(message)

    def error(self, message: str) -> None:
        self.legacy.error_text(message)

    def step_output(self, text: str) -> None:
        self.legacy.text(text)

    def display_diff(
        self,
        diff_text: str,
        *,
        title: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.legacy.display_diff(diff_text, title=title, metadata=metadata)

    def confirm(self, prompt_id: str, message: str, default: bool = False) -> bool:
        return self.legacy.ask_confirm(message, default=default)

    def input_text(
        self,
        prompt_id: str,
        message: str,
        default: str | None = None,
    ) -> str:
        return self.legacy.ask_text(message, default=default or "")

    def multiline_text(
        self,
        prompt_id: str,
        message: str,
        default: str | None = None,
    ) -> str:
        return self.legacy.ask_multiline(message, default=default or "")

    def secret_text(self, prompt_id: str, message: str) -> str:
        return self.legacy.ask_password(message)

    def stream_output(self, text: str) -> None:
        if hasattr(self.legacy, "stream_output"):
            self.legacy.stream_output(text)
        else:
            self.legacy.text(text)

    def external_cli_activity(
        self,
        activity_id: str,
        activity: ExternalCLIActivity,
    ) -> None:
        if hasattr(self.legacy, "external_cli_activity"):
            self.legacy.app.call_from_thread(
                self.legacy.external_cli_activity,
                activity_id,
                activity,
            )

    def external_cli_session(
        self,
        interaction_id: str,
        *,
        cli_name: str,
        prompt: str,
        cwd: str,
    ) -> int:
        return self.legacy.launch_external_cli(cli_name=cli_name, prompt=prompt, cwd=cwd)

    def ask_multiselect(self, message: str, options: list[Any]) -> list[Any]:
        """Keep legacy checkbox rendering for the Textual adapter."""
        return self.legacy.ask_multiselect(message, options)

    def panel(
        self,
        text: str,
        *,
        panel_type: str = "info",
        show_icon: bool = True,
        use_markdown: bool = False,
    ) -> None:
        return self.legacy.panel(
            text,
            panel_type=panel_type,
            show_icon=show_icon,
            use_markdown=use_markdown,
        )

    def table(self, headers: list[str], rows: list[list[str]], title: str = "", **kwargs: Any) -> None:
        return self.legacy.table(headers, rows, title=title, **kwargs)

    def mount(self, widget: Any) -> None:
        return self.legacy.mount(widget)

    def ask_choice(self, message: str, options: list[Any]) -> Any:
        return self.legacy.ask_choice(message, options)

    def option_list(
        self,
        interaction_id: str,
        message: str,
        options: list[InteractionOption],
    ):
        from titan_cli.ui.tui.widgets.prompt_option_list import OptionItem

        items = [
            OptionItem(
                value=option.value if option.value is not None else option.id,
                title=option.label,
                description=option.description or "",
            )
            for option in options
        ]
        return self.legacy.ask_option(message, items)

    def select_one(
        self,
        prompt_id: str,
        message: str,
        options: list[dict[str, Any]],
    ) -> str:
        from titan_cli.ui.tui.widgets.prompt_option_list import OptionItem

        items = [
            OptionItem(
                value=option.get("id"),
                title=str(option.get("label") or option.get("id") or "Option"),
                description=str(option.get("description") or ""),
            )
            for option in options
        ]
        selected = self.legacy.ask_option(message, items)
        return "" if selected is None else str(selected)

    def review_generated_content(
        self,
        interaction_id: str,
        *,
        content_title: str,
        content_body: str,
        header_text: str,
        title_label: str,
        description_label: str,
        choice_question: str,
    ) -> EditableTextResponse:
        choice, title, body = self.legacy.ai_content_review_flow(
            content_title=content_title,
            content_body=content_body,
            header_text=header_text,
            title_label=title_label,
            description_label=description_label,
            edit_instruction=(
                f"Edit the content below (first line = {title_label}, "
                f"rest = {description_label})"
            ),
            confirm_question="Use this content?",
            choice_question=choice_question,
        )
        return EditableTextResponse(action=choice, title=title, content=body)
