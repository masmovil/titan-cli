"""Headless interaction port for backend or test execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import InteractionPort


@dataclass
class HeadlessInteractionPort(InteractionPort):
    """Collects messages in memory without assuming an interactive UI."""

    messages: list[tuple[str, str]] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.messages.append(("info", message))

    def warning(self, message: str) -> None:
        self.messages.append(("warning", message))

    def error(self, message: str) -> None:
        self.messages.append(("error", message))

    def step_output(self, text: str) -> None:
        self.messages.append(("step_output", text))

    def markdown(self, markdown_text: str) -> None:
        self.messages.append(("markdown", markdown_text))
        self.step_output(markdown_text)

    def ai_chip(self, text: str) -> None:
        self.messages.append(("ai_chip", text))

    def begin_step(self, step_name: str) -> None:
        self.messages.append(("step_started", step_name))

    def end_step(self, result_type: str) -> None:
        self.messages.append(("step_finished", result_type))
