"""
AI Workflow Configuration Screen

Discovers every registered workflow's AI-using steps and lets the user
pre-configure which provider/CLI serves each step's task ahead of running it.
"""

import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, HorizontalScroll, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static

from titan_cli.ai.router.availability import AIAvailabilityChecker, AIProviderAvailability
from titan_cli.ai.router.enums import AIProviderType
from titan_cli.ai.router.resolver import AIRouteDecision, AIRouteNeedsInput, AIRouteResolver
from titan_cli.core.workflows.ai_usage_discovery import AIUsageDiscoveryService, DiscoveredAIStep
from titan_cli.engine.workflow_executor import WorkflowExecutor
from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import (
    Button,
    DimText,
    ErrorText,
    StyledOption,
    StyledOptionList,
    SuccessText,
    WarningText,
)

from .base import BaseScreen

OFF_OPTION_ID = "off::off"


def _row_key(workflow_name: str, step: DiscoveredAIStep) -> str:
    """A row identifier unique across workflows, safe for use as a widget id."""
    raw = f"{workflow_name}__{step.step_id}"
    return re.sub(r"[^a-zA-Z0-9_-]", "-", raw)


class SelectProviderModal(ModalScreen[Optional[dict]]):
    """Modal for picking a provider/CLI to persist as a preference."""

    DEFAULT_CSS = """
    SelectProviderModal {
        align: center middle;
    }

    #select-provider-container {
        width: 80;
        height: auto;
        max-height: 30;
        background: $surface-lighten-1;
        border: solid $primary;
        padding: 2;
    }

    #select-provider-list {
        height: auto;
        max-height: 18;
        margin-top: 1;
    }

    #select-provider-buttons {
        height: auto;
        align: right middle;
        margin-top: 2;
    }
    """

    def __init__(self, title: str, candidates: List[AIProviderAvailability], **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.candidates = candidates

    def compose(self) -> ComposeResult:
        with Container(id="select-provider-container"):
            yield Static(f"{Icons.AI_CONFIG} {self.title_text}")
            options = [
                StyledOption(
                    id=f"{candidate.provider}::{candidate.identifier}",
                    title=candidate.display_name or candidate.identifier,
                    description=candidate.provider,
                )
                for candidate in self.candidates
            ]
            options.append(
                StyledOption(
                    id=OFF_OPTION_ID,
                    title="Off",
                    description="Disable AI for this task",
                )
            )
            yield StyledOptionList(*options, id="select-provider-list")
            with Horizontal(id="select-provider-buttons"):
                yield Button("Cancel", variant="default", id="cancel-select-provider")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "select-provider-list":
            return
        option_id = event.option.id
        provider, identifier = option_id.split("::", 1)

        if provider == AIProviderType.OFF:
            self.dismiss({"provider": AIProviderType.OFF.value})
            return

        preference_data = {"provider": provider}
        if provider == AIProviderType.REMOTE:
            preference_data["connection_id"] = identifier
        else:
            preference_data["cli"] = identifier
        self.dismiss(preference_data)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-select-provider":
            self.dismiss(None)


@dataclass
class _StepRow:
    step: DiscoveredAIStep
    resolution: object


class AIStepCard(Container):
    """Widget showing one AI-declaring step and its resolution/actions."""

    DEFAULT_CSS = """
    AIStepCard {
        width: 44;
        height: auto;
        background: $surface-lighten-1;
        border: solid $accent;
        padding: 1 2;
        margin-right: 1;
    }

    AIStepCard .step-name {
        text-style: bold;
    }

    AIStepCard .step-info {
        color: $text-muted;
    }

    AIStepCard .button-column {
        height: auto;
        margin-top: 1;
    }

    AIStepCard .button-column Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        row: _StepRow,
        row_key: str,
        has_task_preference: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.row = row
        self.row_key = row_key
        self.has_task_preference = has_task_preference

    def compose(self) -> ComposeResult:
        step = self.row.step
        resolution = self.row.resolution

        yield Static(f"{Icons.WORKFLOW} {step.step_name}", classes="step-name")

        enforce_label = "enforces" if step.enforces else "declares only"
        yield DimText(f"task: {step.policy.task}", classes="step-info")
        yield DimText(f"step: {step.step}  ({enforce_label})", classes="step-info")

        if isinstance(resolution, AIRouteDecision):
            identifier = resolution.cli or resolution.connection_id or ""
            suffix = f" ({identifier})" if identifier else ""
            yield SuccessText(f"{Icons.CHECK} {resolution.provider}{suffix} — {resolution.reason}")
        elif isinstance(resolution, AIRouteNeedsInput):
            if resolution.candidates:
                yield WarningText(f"{Icons.WARNING} Needs setup — {resolution.reason}")
            else:
                yield ErrorText(f"{Icons.ERROR} No AI provider available — {resolution.reason}")
        else:
            yield DimText("Unknown resolution state", classes="step-info")

        with Container(classes="button-column"):
            yield Button(
                "Set Preference",
                variant="primary",
                id=f"set-task-{self.row_key}",
            )
            if self.has_task_preference:
                yield Button("Clear", variant="error", id=f"clear-task-{self.row_key}")


class AIWorkflowConfigScreen(BaseScreen):
    """Screen for pre-configuring AI providers per workflow/task."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
    ]

    CSS = """
    AIWorkflowConfigScreen {
        align: center middle;
    }

    #ai-workflow-config-container {
        width: 90%;
        height: 1fr;
        background: $surface-lighten-1;
        padding: 0 2 1 2;
        margin: 1 0 1 0;
    }

    #ai-workflow-config-scroll {
        height: 1fr;
        padding: 1 0;
        overflow-y: auto;
    }

    .plugin-heading {
        text-style: bold;
        color: $primary;
        margin-top: 2;
    }

    .workflow-heading {
        text-style: bold;
        margin-top: 1;
        margin-left: 2;
    }

    .step-row {
        height: auto;
        margin-left: 2;
        overflow-x: auto;
        overflow-y: hidden;
    }

    #no-ai-usage {
        text-align: center;
        color: $text-muted;
        margin: 8 0;
    }
    """

    def __init__(self, config):
        super().__init__(
            config,
            title=f"{Icons.AI_CONFIG} AI Workflow Configuration",
            show_back=True,
        )
        self._pending_step_by_id = {}

    def compose_content(self) -> ComposeResult:
        with Container(id="ai-workflow-config-container"):
            yield VerticalScroll(id="ai-workflow-config-scroll")

    def on_mount(self) -> None:
        self.load_workflows()

    def on_screen_resume(self) -> None:
        self.load_workflows()

    def load_workflows(self) -> None:
        self.config.load()

        scroll = self.query_one("#ai-workflow-config-scroll", VerticalScroll)
        scroll.remove_children()

        ai_config = self.config.config.ai if self.config.config else None
        checker = AIAvailabilityChecker(ai_config, self.config.secrets)
        resolver = AIRouteResolver(ai_config, checker)
        discovery = AIUsageDiscoveryService(
            workflow_registry=self.config.workflows,
            plugin_registry=self.config.registry,
            core_steps=WorkflowExecutor.CORE_STEPS,
        )

        usages = discovery.discover_all()
        self._pending_step_by_id = {}

        if not usages:
            scroll.mount(
                Static(
                    "No workflow steps currently declare AI usage.",
                    id="no-ai-usage",
                )
            )
            return

        preferences = ai_config.preferences if ai_config else None

        # Group by plugin -> workflow -> steps. A workflow that mixes steps from
        # several plugins (e.g. a git step and a github step) shows up once per
        # plugin section, each time listing only that plugin's steps.
        by_plugin: Dict[str, "OrderedDict[str, List]"] = {}
        for usage in usages:
            for step in usage.steps:
                workflows_for_plugin = by_plugin.setdefault(step.plugin, OrderedDict())
                workflows_for_plugin.setdefault(usage.workflow_name, []).append(step)

        for plugin_name in sorted(by_plugin.keys()):
            scroll.mount(Static(f"{Icons.PLUGIN} {plugin_name}", classes="plugin-heading"))
            for workflow_name, steps in by_plugin[plugin_name].items():
                scroll.mount(Static(f"{Icons.WORKFLOW} {workflow_name}", classes="workflow-heading"))
                row = HorizontalScroll(classes="step-row")
                scroll.mount(row)
                for step in steps:
                    row_key = _row_key(workflow_name, step)
                    self._pending_step_by_id[row_key] = (workflow_name, step)
                    resolution = resolver.resolve(
                        task=step.policy.task,
                        policy=step.policy,
                    )
                    card = AIStepCard(
                        _StepRow(step=step, resolution=resolution),
                        row_key=row_key,
                        has_task_preference=bool(preferences and step.policy.task in preferences.tasks),
                    )
                    row.mount(card)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""

        if button_id.startswith("set-task-"):
            self._handle_set_preference(button_id[len("set-task-"):])
        elif button_id.startswith("clear-task-"):
            self._handle_clear_preference(button_id[len("clear-task-"):])

    def _handle_set_preference(self, row_key: str) -> None:
        pending = self._pending_step_by_id.get(row_key)
        if not pending:
            return
        _workflow_name, step = pending

        ai_config = self.config.config.ai if self.config.config else None
        checker = AIAvailabilityChecker(ai_config, self.config.secrets)
        candidates = (
            checker.available_remote_connections()
            + checker.available_headless_clis()
            + checker.available_interactive_clis()
        )
        # Offer only what this step's code can actually run ("Off" is always
        # added by the modal itself). No declared set -> offer everything.
        if step.policy.executes:
            candidates = [c for c in candidates if c.provider in step.policy.executes]

        scope_label = f"task '{step.policy.task}'"

        def on_selected(preference_data: Optional[dict]) -> None:
            if preference_data is None:
                return
            try:
                self.config.upsert_task_ai_preference(step.policy.task, preference_data)
                self.load_workflows()
                self.app.notify(f"AI preference saved for {scope_label}", severity="information")
            except Exception as e:
                self.app.notify(f"Failed to save preference: {e}", severity="error")

        self.app.push_screen(
            SelectProviderModal(f"Select provider for {scope_label}", candidates),
            on_selected,
        )

    def _handle_clear_preference(self, row_key: str) -> None:
        pending = self._pending_step_by_id.get(row_key)
        if not pending:
            return
        _workflow_name, step = pending

        try:
            self.config.delete_task_ai_preference(step.policy.task)
            self.load_workflows()
            self.app.notify("AI preference cleared", severity="information")
        except Exception as e:
            self.app.notify(f"Failed to clear preference: {e}", severity="error")

    def action_back(self) -> None:
        self.dismiss()

    def action_go_back(self) -> None:
        self.dismiss()


__all__ = ["AIWorkflowConfigScreen"]
