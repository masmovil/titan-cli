"""
AI Configuration Screen

The single place AI is configured: the connections to remote providers, which CLI to run,
and which kind of AI serves each task.
"""

from typing import Dict, Optional

from textual.app import ComposeResult
from textual.widgets import Static, LoadingIndicator, OptionList
from textual.containers import Container, Horizontal, VerticalScroll, Grid
from textual.binding import Binding
from textual.screen import ModalScreen

from titan_cli.ai.constants import (
    get_connection_type_display_name,
    get_source_display_name,
)
from titan_cli.ai.router.availability import AIAvailabilityChecker
from titan_cli.ai.router.enums import AIProviderType
from titan_cli.ai.router.resolver import AIRouteResolver
from titan_cli.core.models import AIConnectionType
from titan_cli.core.workflows.ai_usage_discovery import AIUsageDiscoveryService
from titan_cli.engine.workflow_executor import WorkflowExecutor
from titan_cli.ui.tui.icons import Icons
from titan_cli.ui.tui.widgets import (
    DimText,
    Button,
    SuccessText,
    ErrorText,
    StyledOptionList,
    StyledOption,
    SegmentedSwitch,
    TabbedPanel,
    TabPanel,
)
from .ai_routing import (
    CliDefaultPicker,
    SelectProviderTypeModal,
    TaskRouting,
    TaskRoutingRow,
    build_task_routings,
    installed_clis,
    provider_type_label,
    task_label,
)
from .base import BaseScreen


class TestConnectionModal(ModalScreen):
    """Modal screen for testing an AI connection."""

    DEFAULT_CSS = """
    TestConnectionModal {
        align: center middle;
    }

    #test-modal-container {
        width: 70;
        height: auto;
        background: $surface-lighten-1;
        border: solid $primary;
        padding: 2;
    }

    #test-modal-header {
        text-style: bold;
        text-align: center;
        margin-bottom: 2;
    }

    #test-modal-content {
        height: auto;
        min-height: 15;
        align: center middle;
    }

    #test-modal-buttons {
        height: auto;
        align: center middle;
        margin-top: 2;
    }

    #loading-container {
        width: 100%;
        height: auto;
        align: center middle;
    }

    LoadingIndicator {
        height: 5;
        margin: 2 0;
    }

    .center-text {
        text-align: center;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close_modal", "Close"),
    ]

    def __init__(self, connection_id: str, connection_cfg, config, **kwargs):
        super().__init__(**kwargs)
        self.connection_id = connection_id
        self.connection_cfg = connection_cfg
        self.config = config

    def compose(self) -> ComposeResult:
        """Compose the test modal."""
        with Container(id="test-modal-container"):
            yield Static(
                f"{Icons.SETTINGS} Testing connection: {self.connection_cfg.name}",
                id="test-modal-header",
            )
            yield Container(id="test-modal-content")
            with Container(id="test-modal-buttons"):
                yield Button("Close", variant="default", id="close-modal-button")

    def on_mount(self) -> None:
        """Start the test when modal mounts."""
        # Show loading indicator
        content = self.query_one("#test-modal-content", Container)

        # Mount loading indicator and text directly
        content.mount(LoadingIndicator())
        content.mount(
            DimText(
                f"\nTesting connection to {self.connection_cfg.name}...",
                classes="center-text",
            )
        )

        # Run test in background AFTER the UI has refreshed
        self.call_after_refresh(self._start_test)

    def _start_test(self) -> None:
        """Start the test after UI refresh."""
        self.run_worker(self._run_test(), exclusive=True)

    async def _run_test(self) -> None:
        """Run the test asynchronously."""
        import asyncio
        import importlib
        from titan_cli.ai.client import AIClient
        from titan_cli.ai.models import AIMessage
        from titan_cli.ai.dependencies import (
            dependencies_available,
            find_missing_modules,
            get_install_command,
            install_missing_dependencies,
        )
        from titan_cli.core.security import create_ai_provider

        content = self.query_one("#test-modal-content", Container)

        try:
            source_name = str(
                self.connection_cfg.provider
                or self.connection_cfg.gateway_backend
                or ""
            )
            if source_name and not dependencies_available(source_name):
                missing_modules = find_missing_modules(source_name)
                install_command = get_install_command(source_name) or []

                should_install = await self.app.push_screen_wait(
                    ConfirmInstallDependenciesModal(
                        source_name=source_name,
                        missing_modules=missing_modules,
                        install_command=install_command,
                    )
                )

                if not should_install:
                    raise RuntimeError(
                        "Required dependencies are not installed for this connection."
                    )

                result = await asyncio.to_thread(
                    install_missing_dependencies,
                    source_name,
                )
                importlib.invalidate_caches()

                if result is None:
                    raise RuntimeError(
                        f"No installer is configured for source '{source_name}'."
                    )

                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr
                        or result.stdout
                        or "Dependency installation failed."
                    )

                if not dependencies_available(source_name):
                    raise RuntimeError(
                        "Dependencies were installed but are still not importable."
                    )

            ai_client = AIClient(
                self.config.config.ai,
                create_ai_provider,
                connection_id=self.connection_id,
            )

            # Run the blocking generate call in a thread to keep UI responsive
            response = await asyncio.to_thread(
                ai_client.generate,
                messages=[AIMessage(role="user", content="Say 'Hello!' if you can hear me")],
            )

            # Show success - remove loading and show result
            content.remove_children()
            content.mount(SuccessText(f"{Icons.CHECK} Connection successful!\n\n"))

            model_info = (
                f" with model '{self.connection_cfg.model}'"
                if self.connection_cfg.model
                else ""
            )
            endpoint_info = (
                " (gateway endpoint)" if self.connection_cfg.base_url else ""
            )
            source_name = get_source_display_name(
                self.connection_cfg.provider or self.connection_cfg.gateway_backend
            )

            content.mount(
                DimText(
                    f"Connection: {source_name}{model_info}{endpoint_info}\n"
                )
            )
            content.mount(DimText(f"Model: {response.model}\n"))
            content.mount(DimText(f"\nResponse: {response.content}"))

        except Exception as e:
            # Show error - remove loading and show error
            content.remove_children()
            content.mount(ErrorText(f"{Icons.ERROR} Connection failed!\n\n"))
            content.mount(DimText(f"Error: {str(e)}"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "close-modal-button":
            self.dismiss()

    def action_close_modal(self) -> None:
        """Close the modal."""
        self.dismiss()


class ConfirmInstallDependenciesModal(ModalScreen[bool]):
    """Modal asking whether missing AI dependencies should be installed."""

    DEFAULT_CSS = """
    ConfirmInstallDependenciesModal {
        align: center middle;
    }

    #confirm-install-container {
        width: 80;
        height: auto;
        background: $surface-lighten-1;
        border: solid $primary;
        padding: 2;
    }

    #confirm-install-buttons {
        height: auto;
        align: right middle;
        margin-top: 2;
    }
    """

    def __init__(
        self,
        source_name: str,
        missing_modules: list[str],
        install_command: list[str],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.source_name = source_name
        self.missing_modules = missing_modules
        self.install_command = install_command

    def compose(self) -> ComposeResult:
        with Container(id="confirm-install-container"):
            yield Static(
                f"{Icons.WARNING} Missing dependencies for {self.source_name}"
            )
            yield DimText("The following Python modules are required:")
            for module_name in self.missing_modules:
                yield DimText(f"  • {module_name}")
            yield DimText("")
            yield DimText("Install command:")
            yield DimText(f"  {' '.join(self.install_command)}")
            with Horizontal(id="confirm-install-buttons"):
                yield Button("Cancel", variant="default", id="cancel-install")
                yield Button("Install", variant="primary", id="confirm-install")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-install":
            self.dismiss(True)
        elif event.button.id == "cancel-install":
            self.dismiss(False)


class SelectGatewayModelModal(ModalScreen[str | None]):
    """Modal for selecting a gateway model from discovered models."""

    DEFAULT_CSS = """
    SelectGatewayModelModal {
        align: center middle;
    }

    #select-model-container {
        width: 80;
        height: auto;
        background: $surface-lighten-1;
        border: solid $primary;
        padding: 2;
    }

    #select-model-content {
        height: auto;
        max-height: 20;
        margin-top: 1;
    }

    #select-model-buttons {
        height: auto;
        align: center middle;
        margin-top: 2;
    }
    """

    def __init__(
        self,
        connection_name: str,
        gateway_client,
        current_model: str,
        **kwargs,
    ):
        """
        Args:
            connection_name: Display name of the gateway connection.
            gateway_client: An already-authenticated LiteLLMClient; built by
                the caller through the secret broker so the key never reaches
                this screen.
            current_model: The connection's current default model.
        """
        super().__init__(**kwargs)
        self.connection_name = connection_name
        self.gateway_client = gateway_client
        self.current_model = current_model

    def compose(self) -> ComposeResult:
        with Container(id="select-model-container"):
            yield Static(f"{Icons.AI_CONFIG} Select gateway model")
            yield DimText(f"Connection: {self.connection_name}")
            yield Container(id="select-model-content")
            with Horizontal(id="select-model-buttons"):
                yield Button("Close", variant="default", id="close-select-model")

    def on_mount(self) -> None:
        content = self.query_one("#select-model-content", Container)
        content.mount(LoadingIndicator())
        content.mount(DimText("Loading models from gateway..."))
        self.call_after_refresh(self._start_loading)

    def _start_loading(self) -> None:
        self.run_worker(self._load_models(), exclusive=True)

    async def _load_models(self) -> None:
        import asyncio

        content = self.query_one("#select-model-content", Container)

        try:
            models = await asyncio.to_thread(self.gateway_client.list_models)

            content.remove_children()

            if not models:
                content.mount(ErrorText("No models available from this gateway."))
                return

            styled_options = [
                StyledOption(
                    id=model.id,
                    title=model.id,
                    description=model.owned_by or "",
                )
                for model in models
            ]

            option_list = StyledOptionList(*styled_options, id="gateway-model-list")
            content.mount(
                DimText("Select the default model for this connection:")
            )
            content.mount(option_list)

            current_index = next(
                (
                    idx
                    for idx, model in enumerate(models)
                    if model.id == self.current_model
                ),
                0,
            )
            option_list.highlighted = current_index
            self.call_after_refresh(lambda: option_list.focus())

        except Exception as e:
            content.remove_children()
            content.mount(ErrorText("Could not load models from gateway."))
            content.mount(DimText(str(e)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-select-model":
            self.dismiss(None)

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option_list.id != "gateway-model-list":
            return
        self.dismiss(event.option.id)


class ConnectionCard(Container):
    """Widget showing a single AI connection with action buttons."""

    DEFAULT_CSS = """
    ConnectionCard {
        width: 100%;
        max-width: 60;
        height: auto;
        background: $surface-lighten-1;
        border: solid $accent;
        padding: 1 2;
    }

    ConnectionCard.default {
        border: solid $primary;
    }

    ConnectionCard .connection-name {
        text-style: bold;
    }

    ConnectionCard .connection-info {
        color: $text-muted;
    }

    ConnectionCard .button-row {
        width: 100%;
        height: auto;
        margin-top: 1;
        grid-size: 2;
        grid-gutter: 1 1;
    }

    ConnectionCard .button-row Button {
        width: 100%;
    }
    """

    def __init__(
        self,
        connection_id: str,
        connection_cfg: dict,
        is_default: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.connection_id = connection_id
        self.connection_cfg = connection_cfg
        self.is_default = is_default

    def compose(self) -> ComposeResult:
        """Compose the connection card."""
        import re

        clean_id = re.sub(r"[^a-z0-9_-]", "", self.connection_id.lower())

        name = self.connection_cfg.get("name", self.connection_id)
        default_marker = f"{Icons.STAR} " if self.is_default else ""
        yield Static(f"{default_marker}{name}", classes="connection-name")

        connection_type = self.connection_cfg.get("connection_type", "")
        provider = self.connection_cfg.get("provider")
        gateway_backend = self.connection_cfg.get("gateway_backend")
        source_label = get_source_display_name(provider or gateway_backend)
        type_label = get_connection_type_display_name(connection_type)
        model = self.connection_cfg.get(
            "default_model", self.connection_cfg.get("model", "")
        )

        yield DimText(f"Type: {type_label}", classes="connection-info")
        yield DimText(f"Source: {source_label}", classes="connection-info")
        yield DimText(f"Model: {model}", classes="connection-info")

        base_url = self.connection_cfg.get("base_url")
        if base_url:
            yield DimText(f"Base URL: {base_url}", classes="connection-info")
        else:
            yield DimText(" ", classes="connection-info")

        # Action buttons (use cleaned ID for button IDs)
        with Grid(classes="button-row"):
            if not self.is_default:
                yield Button("Set Default", variant="primary", id=f"set-default-{clean_id}")
            if connection_type == AIConnectionType.GATEWAY.value:
                yield Button(
                    "Change Model", variant="default", id=f"change-model-{clean_id}"
                )
            yield Button("Test Connection", variant="default", id=f"test-{clean_id}")
            yield Button("Delete", variant="error", id=f"delete-{clean_id}")


class AIConfigScreen(BaseScreen):
    """
    Screen for AI connection configuration and management.
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
    ]

    CSS = """
    AIConfigScreen {
        align: center middle;
    }

    #config-container {
        width: 85%;
        height: 1fr;
        background: $surface-lighten-1;
        padding: 0 2 1 2;
        margin: 1 0 1 0;
    }

    #connections-scroll, #cli-scroll, #tasks-scroll {
        height: 1fr;
        padding: 1 2;
        align: center top;
        overflow-y: auto;
    }

    .section-note {
        margin-bottom: 1;
    }

    #connections-grid {
        grid-size: 2;
        grid-gutter: 2;
        width: 100%;
        height: auto;
    }

    #cli-list, #task-routing-list {
        height: auto;
        width: 100%;
    }

    #no-connections {
        text-align: center;
        color: $text-muted;
        margin: 8 0;
        column-span: 2;
    }

    #add-connection-container {
        height: auto;
        padding: 0 0;
        align: center middle;
    }
    """

    def __init__(self, config):
        super().__init__(
            config,
            title=f"{Icons.AI_CONFIG} AI Configuration",
            show_back=True
        )
        self._routings: Dict[str, TaskRouting] = {}

    def compose_content(self) -> ComposeResult:
        """
        Compose the AI configuration screen.

        Three independent things are configured here, so they get three tabs rather than one
        long scroll: each has the whole screen to itself, and every action stays one
        keystroke away instead of behind navigation.
        """
        with Container(id="config-container"):
            with TabbedPanel(initial="tab-connections"):
                with TabPanel("Connections", id="tab-connections"):
                    with VerticalScroll(id="connections-scroll"):
                        yield Static(
                            "No AI connections configured yet.\n\n"
                            "Click 'New Connection' to configure your first connection.",
                            id="no-connections",
                        )
                        yield Grid(id="connections-grid")
                    with Container(id="add-connection-container"):
                        yield Button(
                            f"{Icons.SETTINGS} New Connection",
                            variant="primary",
                            id="add-connection-button",
                        )

                with TabPanel("CLI", id="tab-cli"):
                    with VerticalScroll(id="cli-scroll"):
                        yield Container(id="cli-list")

                with TabPanel("AI per task", id="tab-tasks"):
                    with VerticalScroll(id="tasks-scroll"):
                        yield Container(id="task-routing-list")

    def on_mount(self) -> None:
        """Load everything when mounted."""
        self.load_sections()

    def on_screen_resume(self) -> None:
        """Reload when returning from a wizard or modal."""
        self.load_sections()
        self._refresh_status_bar()

    def load_sections(self) -> None:
        """
        Reload config once, then repaint every section from it.

        Reading config is expensive enough that each section doing its own reload was
        noticeable; the routing section additionally re-resolves here rather than caching
        what it resolved at mount time, so a preference changed elsewhere is reflected.
        """
        self.config.load()
        self.load_connections()
        self.load_cli_defaults()
        self.load_task_routing()

    def _refresh_status_bar(self) -> None:
        """Refresh the status bar with current AI info."""
        try:
            from titan_cli.ui.tui.widgets import StatusBarWidget
            status_bar = self.query_one(StatusBarWidget)
            self._update_status_bar(status_bar)
        except Exception:
            pass  # Status bar might not be available

    def load_connections(self) -> None:
        """Display all configured AI connections."""
        # Get the grid
        try:
            grid = self.query_one("#connections-grid", Grid)
        except Exception:
            # Grid was removed, recreate it inside its own tab.
            section = self.query_one("#connections-scroll", VerticalScroll)
            grid = Grid(id="connections-grid")
            section.mount(grid)

        grid.remove_children()

        # The empty-state message is always in the tree and only toggled. Removing and
        # re-mounting it by id raced with itself: `remove()` completes on a later frame, so
        # two repaints in the same tick tried to insert a second widget with the same id.
        has_connections = bool(
            self.config.config.ai and self.config.config.ai.connections
        )
        self.query_one("#no-connections", Static).display = not has_connections

        if not has_connections:
            return

        default_id = self.config.config.ai.default_connection

        for connection_id, connection_cfg in self.config.config.ai.connections.items():
            is_default = connection_id == default_id
            card = ConnectionCard(
                connection_id=connection_id,
                connection_cfg=connection_cfg.model_dump(),
                is_default=is_default
            )
            if is_default:
                card.add_class("default")
            grid.mount(card)

    def _availability(self) -> AIAvailabilityChecker:
        """
        A checker for this repaint.

        Deliberately rebuilt per repaint rather than kept on the screen: it caches its
        probes, so a long-lived one would keep reporting a CLI you just installed as absent.
        """
        from titan_cli.core.security import create_broker_factory

        ai_config = self.config.config.ai if self.config.config else None
        broker = create_broker_factory(self.config.project_root).for_plugin("core")
        return AIAvailabilityChecker(ai_config, broker)

    def load_cli_defaults(self) -> None:
        """Display the installed CLIs and which one Titan will run."""
        container = self.query_one("#cli-list", Container)
        container.remove_children()

        checker = self._availability()
        installed = installed_clis(
            checker.available_headless_clis(), checker.available_interactive_clis()
        )
        ai_config = self.config.config.ai if self.config.config else None
        container.mount(
            CliDefaultPicker(installed, current=ai_config.default_cli if ai_config else None)
        )

    def load_task_routing(self) -> None:
        """Display one row per discovered AI task, with its live resolution."""
        container = self.query_one("#task-routing-list", Container)
        container.remove_children()

        ai_config = self.config.config.ai if self.config.config else None
        resolver = AIRouteResolver(ai_config, self._availability())
        discovery = AIUsageDiscoveryService(
            workflow_registry=self.config.workflows,
            plugin_registry=self.config.registry,
            core_steps=WorkflowExecutor.CORE_STEPS,
        )

        preferences = ai_config.preferences if ai_config else None
        try:
            self._routings = {
                routing.task: routing
                for routing in build_task_routings(
                    discovery.discover_all(),
                    resolver,
                    persisted_tasks=list(preferences.tasks) if preferences else [],
                )
            }
        except Exception as e:
            # A single broken plugin or malformed workflow must not take down the
            # whole AI Configuration screen; degrade this tab and keep the rest.
            from titan_cli.core.logging import get_logger
            get_logger(__name__).exception("ai_config_task_routing_load_failed")
            self._routings = {}
            container.mount(
                DimText(
                    "Could not discover AI task usage. Check the logs for details.",
                    classes="section-note",
                )
            )
            self.app.notify(f"Failed to load task routing: {e}", severity="error")
            return

        if not self._routings:
            container.mount(
                DimText(
                    "No workflow step declares AI usage yet.", classes="section-note"
                )
            )
            return

        for routing in self._routings.values():
            row = TaskRoutingRow(routing)
            if routing.needs_setup:
                row.add_class("needs-setup")
            container.mount(row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id or ""

        if button_id == "add-connection-button":
            self.handle_add_connection()
        elif button_id.startswith("task-change-"):
            self.handle_change_task_provider(self._task_of(event.button))
        elif button_id.startswith("task-clear-"):
            self.handle_clear_task_provider(self._task_of(event.button))
        elif (
            button_id.startswith("set-default-")
            or button_id.startswith("change-model-")
            or button_id.startswith("test-")
            or button_id.startswith("delete-")
        ):
            card = event.button.parent.parent
            if isinstance(card, ConnectionCard):
                connection_id = card.connection_id

                if button_id.startswith("set-default-"):
                    self.handle_set_default(connection_id)
                elif button_id.startswith("change-model-"):
                    self.handle_change_model(connection_id)
                elif button_id.startswith("test-"):
                    self.handle_test_connection(connection_id)
                elif button_id.startswith("delete-"):
                    self.handle_delete(connection_id)

    @staticmethod
    def _task_of(button) -> Optional[str]:
        """
        The task a row's button belongs to, read from the row itself.

        Widget ids are sanitized, so a community task key containing punctuation cannot be
        recovered from the id - the owning row is the only reliable source.
        """
        node = button.parent
        while node is not None and not isinstance(node, TaskRoutingRow):
            node = node.parent
        return node.routing.task if node else None

    def handle_change_task_provider(self, task: Optional[str]) -> None:
        """Pick which kind of AI serves a task."""
        routing = self._routings.get(task) if task else None
        if not routing:
            return

        def on_selected(provider: Optional[str]) -> None:
            if provider is None:
                return
            try:
                self.config.upsert_task_ai_preference(task, {"provider": provider})
                self.load_sections()
                self.app.notify(
                    f"{routing.label}: {provider_type_label(AIProviderType(provider))}",
                    severity="information",
                )
            except Exception as e:
                self.app.notify(f"Failed to save preference: {e}", severity="error")

        self.app.push_screen(
            SelectProviderTypeModal(f"AI for {routing.label}", routing.executes),
            on_selected,
        )

    def handle_clear_task_provider(self, task: Optional[str]) -> None:
        """Drop a task preference so the step's own default applies again."""
        if not task:
            return
        try:
            self.config.delete_task_ai_preference(task)
            self.load_sections()
            self.app.notify(f"Cleared: {task_label(task)}", severity="information")
        except Exception as e:
            self.app.notify(f"Failed to clear preference: {e}", severity="error")

    def on_segmented_switch_changed(self, event: SegmentedSwitch.Changed) -> None:
        """Picking a segment in the CLI tab is the act of setting the default."""
        if event.sender.id != "cli-default-switch":
            return
        self.handle_set_default_cli(event.value)

    def handle_set_default_cli(self, cli_name: str) -> None:
        """
        Set the CLI every CLI-routed task will run.

        Moving across the switch is how it is chosen, so this runs on each keypress: it
        updates the status line in place and repaints only the task rows, rather than
        reloading and rebuilding the whole screen under the user's fingers.
        """
        try:
            self.config.set_default_ai_cli(cli_name)
            self.query_one(CliDefaultPicker).set_current(cli_name)
            self.load_task_routing()
        except Exception as e:
            self.app.notify(f"Failed to set default CLI: {e}", severity="error")

    def handle_add_connection(self) -> None:
        """Open the configuration wizard to add a new connection."""
        from .ai_config_wizard import AIConfigWizardScreen

        self.app.push_screen(AIConfigWizardScreen(self.config))

    def handle_set_default(self, connection_id: str) -> None:
        """Set a connection as default."""

        try:
            self.config.set_default_ai_connection(connection_id)

            self.load_sections()
            self._refresh_status_bar()

            connection_name = self.config.config.ai.connections[connection_id].name
            self.app.notify(
                f"'{connection_name}' is now the default connection",
                severity="information",
            )

        except Exception as e:
            self.app.notify(f"Failed to set default: {e}", severity="error")

    def handle_test_connection(self, connection_id: str) -> None:
        """Test connection to an AI connection."""
        self.config.load()

        if connection_id not in self.config.config.ai.connections:
            self.app.notify("Connection not found", severity="error")
            return

        connection_cfg = self.config.config.ai.connections[connection_id]
        self.app.push_screen(
            TestConnectionModal(connection_id, connection_cfg, self.config)
        )

    def handle_change_model(self, connection_id: str) -> None:
        """Change the default model for an AI connection."""
        from titan_cli.ai.litellm_client import LiteLLMClient
        from titan_cli.core.security import create_broker_factory

        self.config.load()

        if connection_id not in self.config.config.ai.connections:
            self.app.notify("Connection not found", severity="error")
            return

        connection_cfg = self.config.config.ai.connections[connection_id]
        if connection_cfg.connection_type != AIConnectionType.GATEWAY:
            self.app.notify(
                "Model selection from gateway is only available for AI gateways.",
                severity="warning",
            )
            return

        if not connection_cfg.base_url:
            self.app.notify("Gateway base URL is missing", severity="error")
            return

        current_model = connection_cfg.default_model or ""
        # The gateway key crosses into the client constructor inside the
        # broker call; the modal receives the authenticated client. A gateway
        # may legitimately have no key (e.g. a local proxy).
        broker = create_broker_factory(self.config.project_root).for_plugin("core")
        gateway_client = broker.create_client(
            f"{connection_id}_api_key",
            lambda api_key: LiteLLMClient(
                base_url=connection_cfg.base_url,
                api_key=api_key,
            ),
            required=False,
        )

        def on_change_model(result: str | None) -> None:
            if not result:
                return

            try:
                self.config.update_ai_connection(
                    connection_id,
                    {"default_model": result},
                )
                self.load_sections()
                self._refresh_status_bar()
                self.app.notify(
                    f"Default model for '{connection_cfg.name}' updated",
                    severity="information",
                )
            except Exception as e:
                self.app.notify(f"Failed to update model: {e}", severity="error")

        self.app.push_screen(
            SelectGatewayModelModal(
                connection_cfg.name,
                gateway_client,
                current_model,
            ),
            on_change_model,
        )

    def handle_delete(self, connection_id: str) -> None:
        """Delete an AI connection."""
        from titan_cli.core.security import create_broker_factory

        try:
            self.config.load()

            if connection_id not in self.config.config.ai.connections:
                self.app.notify("Connection not found", severity="error")
                return

            connection_name = self.config.config.ai.connections[connection_id].name
            self.config.delete_ai_connection(connection_id)

            broker = create_broker_factory(self.config.project_root).for_plugin("core")
            try:
                broker.delete(f"{connection_id}_api_key")
            except Exception:
                pass

            self.load_sections()
            self._refresh_status_bar()

            self.app.notify(
                f"Connection '{connection_name}' deleted",
                severity="information",
            )

        except Exception as e:
            self.app.notify(f"Failed to delete connection: {e}", severity="error")

    def action_back(self) -> None:
        """Go back to main menu (ESC key)."""
        self.dismiss()

    def action_go_back(self) -> None:
        """Go back to main menu (Back button)."""
        self.dismiss()
