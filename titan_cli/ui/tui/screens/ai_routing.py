"""
Per-task AI routing: the widgets and the pure logic behind the "AI per task" and "CLI"
sections of the AI Configuration screen.

The unit a user configures is the TASK ("for commit messages, use X"), not the step, the
workflow or the plugin - those are how the setting is discovered, not how it is chosen. So
discovery output is aggregated by task here, and each row offers only KINDS of provider.
Which connection or CLI serves a kind is one global setting, set once in the CLI section and
in the connections grid.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static

from titan_cli.ai.router.availability import AIProviderAvailability
from titan_cli.ai.router.enums import (
    AIProviderType,
    provider_description,
    provider_label,
)
from titan_cli.ai.router.models import AIRouteDecision, AIRoutePolicy
from titan_cli.ai.router.resolver import AIRouteNeedsInput, AIRouteResolution, AIRouteResolver
from titan_cli.core.workflows.ai_usage_discovery import (
    DiscoveredAIStep,
    DiscoveredWorkflowAIUsage,
)
from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import (
    Button,
    DimText,
    ErrorText,
    SegmentedSwitch,
    SegmentedSwitchOption,
    StyledOption,
    StyledOptionList,
    SuccessText,
    WarningText,
)

# Human labels for the task keys official plugins use. A task not listed here - a community
# plugin's own key - falls back to its humanized raw value, so the row is still readable.
TASK_LABELS: Dict[str, str] = {
    "commit_message": "Commit messages",
    "pr_description": "PR descriptions",
    "issue_generation": "Issue generation",
    "jira_analysis": "Jira issue analysis",
    "jira_issue_enhancement": "Jira issue descriptions",
    "code_review_plan": "Code review plan",
    "code_review_findings": "Code review findings",
    "thread_resolution": "Review thread resolution",
    "respond_pr_comment": "PR comment replies",
    "fix_test_failures": "Test failure fixes",
    "fix_lint_failures": "Lint failure fixes",
    "generic_assistant": "Code assistant",
    "slack_summary": "Slack summaries",
}


def task_label(task: str) -> str:
    """A readable name for a task key, including ones this module has never seen."""
    return TASK_LABELS.get(task, task.replace("_", " ").capitalize())


def provider_type_label(provider: AIProviderType) -> str:
    """Kept as the UI's entry point to the router's own vocabulary."""
    return provider_label(provider)


def widget_key(task: str) -> str:
    """A widget-id-safe form of a task key."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", task)


@dataclass
class TaskRouting:
    """Everything one row of the "AI per task" section needs to render itself."""

    task: str
    label: str
    workflows: List[str] = field(default_factory=list)
    executes: List[AIProviderType] = field(default_factory=list)
    resolution: Optional[AIRouteResolution] = None
    has_preference: bool = False
    unenforced_steps: List[str] = field(default_factory=list)

    @property
    def configurable(self) -> bool:
        """Whether there is anything honest to offer the user for this task."""
        return bool(self.executes)

    @property
    def needs_setup(self) -> bool:
        """
        Whether this row is asking the user for something.

        Either nothing can run the task, or resolution could not pick a provider - a missing
        default, an uninstalled one, or a stored preference the step cannot execute. Both are
        "you have to do something here", which is what the row's warning border marks.
        """
        return not self.configurable or isinstance(self.resolution, AIRouteNeedsInput)


def executable_types(steps: Sequence[DiscoveredAIStep]) -> List[AIProviderType]:
    """
    The provider types EVERY step behind a task can run.

    An intersection, not a union: one setting drives all of them, so offering a type only
    some can execute would configure a guaranteed failure for the rest. Steps that declare
    nothing contribute no constraint - they are unrouted anyway, and treating their silence
    as "supports nothing" would empty the intersection for everyone sharing the task.
    """
    declared = [set(step.policy.executes) for step in steps if step.policy.executes]
    if not declared:
        return []
    return [
        provider
        for provider in AIProviderType
        if provider != AIProviderType.OFF and all(provider in d for d in declared)
    ]


def _merged_policy(task: str, steps: Sequence[DiscoveredAIStep]) -> AIRoutePolicy:
    """
    One policy standing in for every step behind a task, used to preview resolution.

    `executes` is what they can all run; `preferred` keeps the first step's order, minus
    anything the others can't run, so the preview matches what the majority case - a single
    declaring step - would actually do.
    """
    executes = executable_types(steps)
    preferred = [p for p in (steps[0].policy.preferred if steps else []) if p in executes]
    return AIRoutePolicy(task=task, executes=executes, preferred=preferred)


def build_task_routings(
    usages: Sequence[DiscoveredWorkflowAIUsage],
    resolver: AIRouteResolver,
    persisted_tasks: Optional[Sequence[str]] = None,
) -> List[TaskRouting]:
    """Aggregate discovered steps into one entry per task, resolved and ready to render."""
    persisted = set(persisted_tasks or ())
    steps_by_task: Dict[str, List[DiscoveredAIStep]] = {}
    workflows_by_task: Dict[str, List[str]] = {}

    for usage in usages:
        for step in usage.steps:
            steps_by_task.setdefault(step.policy.task, []).append(step)
            workflows = workflows_by_task.setdefault(step.policy.task, [])
            if usage.workflow_name not in workflows:
                workflows.append(usage.workflow_name)

    routings = []
    for task, steps in steps_by_task.items():
        policy = _merged_policy(task, steps)
        routings.append(
            TaskRouting(
                task=task,
                label=task_label(task),
                workflows=workflows_by_task.get(task, []),
                executes=policy.executes,
                resolution=resolver.resolve(task=task, policy=policy),
                has_preference=task in persisted,
                unenforced_steps=[s.step_name for s in steps if not s.enforces],
            )
        )

    return sorted(routings, key=lambda r: r.label.lower())


def installed_clis(
    headless: Sequence[AIProviderAvailability],
    interactive: Sequence[AIProviderAvailability],
) -> List[str]:
    """
    Every CLI usable in either mode, in a stable order.

    One CLI serves both modes - the same binary, invoked differently - so the two lists are
    merged into the single choice the user actually makes.
    """
    names: List[str] = []
    for candidate in list(headless) + list(interactive):
        if candidate.identifier not in names:
            names.append(candidate.identifier)
    return names


def suggested_cli(installed: Sequence[str], current_default: Optional[str]) -> Optional[str]:
    """
    The CLI to highlight when no default is set yet.

    Only when there is exactly one installed: with one candidate there is nothing to get
    wrong, while picking among several would be choosing for the user. Highlighting is not
    saving - the user still confirms.
    """
    if current_default or len(installed) != 1:
        return None
    return installed[0]


class SelectProviderTypeModal(ModalScreen[Optional[str]]):
    """
    Modal for choosing which KIND of AI runs a task.

    Dismisses with an `AIProviderType` value, or `None` if cancelled.
    """

    DEFAULT_CSS = """
    SelectProviderTypeModal {
        align: center middle;
    }

    #select-type-container {
        width: 74;
        height: auto;
        max-height: 26;
        background: $surface-lighten-1;
        border: solid $primary;
        padding: 2;
    }

    #select-type-list {
        height: auto;
        max-height: 16;
        margin-top: 1;
    }

    #select-type-buttons {
        height: auto;
        align: right middle;
        margin-top: 2;
    }
    """

    BINDINGS = [("escape", "dismiss_modal", "Cancel")]

    def __init__(self, title: str, choices: Sequence[AIProviderType], **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.choices = list(choices)

    def compose(self) -> ComposeResult:
        with Container(id="select-type-container"):
            yield Static(f"{Icons.AI_CONFIG} {self.title_text}")
            options = [
                StyledOption(
                    id=str(choice),
                    title=provider_type_label(choice),
                    description=provider_description(choice),
                )
                for choice in self.choices
            ]
            options.append(
                StyledOption(
                    id=str(AIProviderType.OFF),
                    title=provider_type_label(AIProviderType.OFF),
                    description=provider_description(AIProviderType.OFF),
                )
            )
            yield StyledOptionList(*options, id="select-type-list")
            with Horizontal(id="select-type-buttons"):
                yield Button("Cancel", variant="default", id="cancel-select-type")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "select-type-list":
            return
        self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-select-type":
            self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class TaskRoutingRow(Container):
    """One task, what currently serves it, and how to change that."""

    DEFAULT_CSS = """
    TaskRoutingRow {
        height: auto;
        width: 100%;
        padding: 1 2;
        margin-bottom: 1;
        background: $surface;
        border-left: thick $primary;
    }

    TaskRoutingRow.needs-setup {
        border-left: thick $warning;
    }

    TaskRoutingRow .task-name {
        text-style: bold;
    }

    TaskRoutingRow .task-options-heading {
        margin-top: 1;
    }

    TaskRoutingRow .task-buttons {
        height: auto;
        align: right middle;
        margin-top: 1;
    }

    TaskRoutingRow .task-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, routing: TaskRouting, **kwargs):
        super().__init__(**kwargs)
        self.routing = routing

    def compose(self) -> ComposeResult:
        routing = self.routing
        yield Static(routing.label, classes="task-name")

        # A task nothing can execute gets no options and no actions - offering either would
        # be inviting the user to configure something that cannot take effect.
        if not routing.configurable:
            yield DimText(self._usage_summary())
            yield WarningText(
                f"{Icons.WARNING} This one can't be changed yet - these steps pick their own AI."
            )
            # A preference saved while the task was still routable would silently re-apply
            # the moment it becomes routable again - keep the way out visible.
            if routing.has_preference:
                yield DimText(
                    "A saved preference for this task still exists and will apply "
                    "if it becomes configurable again."
                )
                with Horizontal(classes="task-buttons"):
                    yield Button(
                        "Clear",
                        variant="default",
                        id=f"task-clear-{widget_key(routing.task)}",
                    )
            return

        yield from self._resolution_lines()
        yield DimText(self._usage_summary())

        if routing.unenforced_steps:
            yield WarningText(
                f"{Icons.WARNING} May not be honored by: "
                f"{', '.join(routing.unenforced_steps)}"
            )

        # The options are listed here, not just behind the button: knowing whether a task can
        # even run on a CLI is the reason you would open the picker at all.
        yield DimText("Can run on:", classes="task-options-heading")
        for provider in routing.executes:
            yield DimText(
                f"  · {provider_type_label(provider)} — {provider_description(provider)}",
                classes="task-option",
            )

        with Horizontal(classes="task-buttons"):
            yield Button(
                "Change", variant="primary", id=f"task-change-{widget_key(routing.task)}"
            )
            if routing.has_preference:
                yield Button(
                    "Clear", variant="default", id=f"task-clear-{widget_key(routing.task)}"
                )

    def _resolution_lines(self) -> ComposeResult:
        resolution = self.routing.resolution
        origin = "your pick" if self.routing.has_preference else "default"

        if isinstance(resolution, AIRouteDecision):
            if resolution.provider == AIProviderType.OFF:
                yield DimText(f"{Icons.CHECK} Off  ({origin})")
                return
            instance = resolution.cli or resolution.connection_id or ""
            suffix = f" · {instance}" if instance else ""
            yield SuccessText(
                f"{Icons.CHECK} {provider_type_label(resolution.provider)}{suffix}  ({origin})"
            )
        elif isinstance(resolution, AIRouteNeedsInput):
            if resolution.candidates:
                yield WarningText(f"{Icons.WARNING} Needs setup - {resolution.reason}")
            else:
                yield ErrorText(f"{Icons.ERROR} No AI available - {resolution.reason}")

    def _usage_summary(self) -> str:
        count = len(self.routing.workflows)
        if count == 1:
            return f"used by 1 workflow: {self.routing.workflows[0]}"
        return f"used by {count} workflows"


class CliDefaultPicker(Container):
    """
    The one CLI Titan runs, as a single control.

    A segmented switch rather than a row of buttons: picking the default is one choice among
    a handful of mutually exclusive options, and rendering it as one control per row left the
    current one with no button at all, so the rows did not even line up.
    """

    DEFAULT_CSS = """
    CliDefaultPicker {
        height: auto;
        width: 100%;
    }

    CliDefaultPicker SegmentedSwitch {
        width: auto;
        min-width: 30;
        margin: 1 0;
    }

    CliDefaultPicker .cli-note {
        margin-top: 1;
    }
    """

    def __init__(self, installed: Sequence[str], *, current: Optional[str], **kwargs):
        super().__init__(**kwargs)
        self.installed = list(installed)
        # A saved default that is no longer installed must not read as active: the switch
        # would highlight whatever it falls back to while the status names a CLI that
        # cannot run. Keep the stale name only to explain the warning.
        self.stale_current = current if current and current not in self.installed else None
        self.current = current if current in self.installed else None
        self.suggestion = suggested_cli(self.installed, self.current)

    def compose(self) -> ComposeResult:
        if not self.installed:
            yield WarningText(
                f"{Icons.WARNING} No supported CLI is installed. "
                "Tasks set to use a CLI will say so when they run."
            )
            return

        yield Static("Which CLI should Titan run?")
        yield DimText(
            "One choice for both uses below - it is the same tool, invoked differently."
        )
        yield SegmentedSwitch(
            options=[SegmentedSwitchOption(value=name, label=name) for name in self.installed],
            value=self.current or self.suggestion or self.installed[0],
            autofocus=False,
            # Until saved, the highlighted segment is only a suggestion: picking it must
            # still emit Changed, or confirming it could never persist a default.
            emit_on_reselect=True,
            id="cli-default-switch",
        )
        yield Static(self._status_text(), id="cli-status")

        yield DimText(
            f"  · {provider_type_label(AIProviderType.CLI_HEADLESS)} — "
            f"{provider_description(AIProviderType.CLI_HEADLESS)}",
            classes="cli-note",
        )
        yield DimText(
            f"  · {provider_type_label(AIProviderType.CLI_INTERACTIVE)} — "
            f"{provider_description(AIProviderType.CLI_INTERACTIVE)}"
        )

    def _status_text(self) -> str:
        if self.stale_current:
            return (
                f"{Icons.WARNING} The default {self.stale_current} is no longer "
                "installed - pick one below."
            )
        if self.current:
            return f"{Icons.CHECK} Titan will run {self.current}."
        if self.suggestion:
            return (
                f"{Icons.WARNING} No default set yet. {self.suggestion} is the only one "
                "installed - select it to use it."
            )
        return (
            f"{Icons.WARNING} No default set yet. Tasks set to use a CLI cannot run until "
            "you pick one."
        )

    def set_current(self, cli_name: str) -> None:
        """
        Update the status line in place after a selection.

        Deliberately not a remount: the switch is what the user is currently operating, and
        rebuilding it under them would drop focus mid-keystroke.
        """
        self.current = cli_name
        self.stale_current = None
        self.suggestion = None
        self.query_one("#cli-status", Static).update(self._status_text())


__all__ = [
    "TaskRouting",
    "TaskRoutingRow",
    "CliDefaultPicker",
    "SelectProviderTypeModal",
    "build_task_routings",
    "executable_types",
    "installed_clis",
    "suggested_cli",
    "task_label",
    "provider_type_label",
    "widget_key",
]
