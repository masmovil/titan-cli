"""
Titan TUI Module

Textual-based Terminal User Interface for Titan CLI.
"""
from .app import TitanApp

__all__ = ["TitanApp"]


def _run_app(app: TitanApp) -> None:
    """
    Run the app, then guarantee the process actually exits.

    Workflow steps run on non-daemon executor threads that the interpreter
    joins at exit. Blocking calls made from them are interruptible and notice
    the app closing within half a second - but if any future call slips through
    without that escape, the console would hang after the TUI is gone until a
    second Ctrl+C. Waiting briefly and then forcing the exit turns that worst
    case into a short pause instead of a hang.
    """
    import logging
    import os
    import threading

    app.run()

    for _ in range(6):  # up to ~3s for worker threads to notice the app closed
        lingering = [
            t for t in threading.enumerate()
            if t is not threading.current_thread() and not t.daemon
        ]
        if not lingering:
            return
        lingering[0].join(timeout=0.5)

    logging.shutdown()
    os._exit(0)


def launch_tui(debug: bool = False, devtools: bool = False):
    """
    Launch the Titan TUI application.

    This is the main entry point for running Titan in TUI mode.

    Args:
        debug: Enable DEBUG level file logging (set by titan-dev or --debug)
        devtools: Enable Textual devtools for visual debugging (requires `textual console` in another terminal)

    Flow:
    1. Check if global config exists (~/.titan/config.toml)
       - If NO: Launch global setup wizard
       - If YES: Continue
    2. Check if project config exists (./.titan/config.toml)
       - If NO: Launch project setup wizard
       - If YES: Continue to main menu

    Logging:
    - Production (debug=False): Console logging disabled, logs only to file
    - Development (debug=True, devtools=False): Console logging disabled, logs only to file at DEBUG level
    - Development + Visual (debug=True, devtools=True): Console logging enabled for Textual devtools,
      (use `textual console` in another terminal to see logs)
      while logs continue to be written to file
    """
    import os
    from titan_cli.core.config import TitanConfig
    from titan_cli.core.plugins.plugin_registry import PluginRegistry
    from titan_cli.core.logging import disable_console_logging
    from titan_cli.core.utils import find_project_root
    from .screens import GlobalSetupWizardScreen, ProjectSetupWizardScreen, MainMenuScreen

    # Enable Textual devtools only if explicitly requested.
    # Keep console logging enabled in this mode so `textual console` can receive logs.
    if devtools:
        features = set()
        features.add("debug")
        features.add("devtools")
        os.environ["TEXTUAL"] = ",".join(sorted(features))
    else:
        # Without Textual devtools, the TUI would hide console logs anyway.
        # Keep logging only in the file handler, even in debug mode.
        disable_console_logging()

    # Check if global config exists
    global_config_path = TitanConfig.GLOBAL_CONFIG

    if not global_config_path.exists():
        # First-time setup: Launch global setup wizard
        # Skip plugin initialization until after setup completes
        plugin_registry = PluginRegistry()
        config = TitanConfig(registry=plugin_registry, skip_plugin_init=True)

        # We'll create a special wrapper screen that handles the wizard flow
        from .screens.base import BaseScreen
        from textual.app import ComposeResult
        from textual.containers import Container

        class WizardFlowScreen(BaseScreen):
            """Temporary screen to manage wizard flow."""

            def __init__(self, config, *args, **kwargs):
                super().__init__(config, title="Setup", show_back=False, *args, **kwargs)

            def compose_content(self) -> ComposeResult:
                # This won't be used, we push wizard immediately
                yield Container()

            def on_mount(self) -> None:
                """Push the global wizard on mount."""
                def on_project_wizard_complete(_=None):
                    """After project wizard completes, show main menu."""
                    # Reload project config without resetting plugins
                    from titan_cli.core.security import create_broker_factory
                    from titan_cli.core.models import TitanConfigModel

                    _project_root = find_project_root()
                    self.config.project_config_path = _project_root / ".titan" / "config.toml"
                    self.config.project_config = self.config._load_toml(self.config.project_config_path)

                    # Merge configs and update
                    merged = self.config._merge_configs(self.config.global_config, self.config.project_config)
                    self.config.config = TitanConfigModel(**merged)

                    # Rebuild the broker factory against the project root
                    self.config.broker_factory = create_broker_factory(project_path=_project_root)

                    # Initialize only the configured plugins (without reset)
                    self.config.registry.initialize_plugins(config=self.config, broker_factory=self.config.broker_factory)

                    # Reload workflow registry to reflect enabled/disabled plugins
                    self.config.workflows.reload()

                    # Pop all screens except the base one, then push main menu
                    # WizardFlowScreen is still there, so we need to pop it too
                    # Stack after project wizard completes: [WizardFlowScreen]
                    # We want: [MainMenuScreen]
                    self.app.pop_screen()  # Remove WizardFlowScreen
                    self.app.push_screen(MainMenuScreen(self.config))

                def on_global_wizard_complete(_=None):
                    """After global wizard completes, check for project config."""
                    from titan_cli.core.models import TitanConfigModel

                    # Reload global config
                    self.config.global_config = self.config._load_toml(self.config._global_config_path)

                    # Update config.config with the new global config
                    # (merge with empty project config since we don't have one yet)
                    merged = self.config._merge_configs(self.config.global_config, {})
                    self.config.config = TitanConfigModel(**merged)

                    # Check if project config exists at project root (git root or cwd)
                    _project_root = find_project_root()
                    project_config_path = _project_root / ".titan" / "config.toml"

                    if not project_config_path.exists():
                        # Launch project setup wizard with callback to show main menu
                        self.app.push_screen(
                            ProjectSetupWizardScreen(self.config, _project_root),
                            on_project_wizard_complete
                        )
                    else:
                        # Project is configured, reload configs without resetting plugins
                        from titan_cli.core.security import create_broker_factory
                        from titan_cli.core.models import TitanConfigModel

                        self.config.project_config_path = project_config_path
                        self.config.project_config = self.config._load_toml(self.config.project_config_path)

                        # Merge configs and update
                        merged = self.config._merge_configs(self.config.global_config, self.config.project_config)
                        self.config.config = TitanConfigModel(**merged)

                        # Rebuild the broker factory against the project root
                        self.config.broker_factory = create_broker_factory(project_path=_project_root)

                        # Initialize plugins with new config
                        self.config.registry.initialize_plugins(config=self.config, broker_factory=self.config.broker_factory)

                        # Reload workflow registry to reflect enabled/disabled plugins
                        self.config.workflows.reload()

                        # Stack: [WizardFlowScreen]
                        # We want: [MainMenuScreen]
                        self.app.pop_screen()  # Remove WizardFlowScreen
                        self.app.push_screen(MainMenuScreen(self.config))

                # Push global wizard
                self.app.push_screen(GlobalSetupWizardScreen(self.config), on_global_wizard_complete)

        # Create app with the flow screen
        app = TitanApp(config=config, initial_screen=WizardFlowScreen(config))
        _run_app(app)
        return

    # Global config exists, check if project config exists at project root (git root or cwd)
    project_config_path = find_project_root() / ".titan" / "config.toml"

    if not project_config_path.exists():
        # Project not configured: Skip plugin initialization until after setup
        plugin_registry = PluginRegistry()
        config = TitanConfig(registry=plugin_registry, skip_plugin_init=True)
        # Create a wrapper screen similar to global wizard flow
        from .screens.base import BaseScreen
        from textual.app import ComposeResult
        from textual.containers import Container

        class ProjectWizardFlowScreen(BaseScreen):
            """Temporary screen to manage project wizard flow."""

            def __init__(self, config, *args, **kwargs):
                super().__init__(config, title="Project Setup", show_back=False, *args, **kwargs)

            def compose_content(self) -> ComposeResult:
                # This won't be used, we push wizard immediately
                yield Container()

            def on_mount(self) -> None:
                """Push the project wizard on mount."""
                def on_project_wizard_complete(_=None):
                    """After project wizard completes, show main menu."""
                    # Reload project config without resetting plugins
                    from titan_cli.core.security import create_broker_factory
                    from titan_cli.core.models import TitanConfigModel

                    _project_root = find_project_root()
                    self.config.project_config_path = _project_root / ".titan" / "config.toml"
                    self.config.project_config = self.config._load_toml(self.config.project_config_path)

                    # Merge configs and update
                    merged = self.config._merge_configs(self.config.global_config, self.config.project_config)
                    self.config.config = TitanConfigModel(**merged)

                    # Rebuild the broker factory against the project root
                    self.config.broker_factory = create_broker_factory(project_path=_project_root)

                    # Initialize only the configured plugins (without reset)
                    self.config.registry.initialize_plugins(config=self.config, broker_factory=self.config.broker_factory)

                    # Reload workflow registry to reflect enabled/disabled plugins
                    self.config.workflows.reload()

                    # Pop this flow screen and show main menu
                    self.app.pop_screen()  # Remove ProjectWizardFlowScreen
                    self.app.push_screen(MainMenuScreen(self.config))

                # Push project wizard
                self.app.push_screen(
                    ProjectSetupWizardScreen(self.config, find_project_root()),
                    on_project_wizard_complete
                )

        # Create app with the flow screen
        app = TitanApp(config=config, initial_screen=ProjectWizardFlowScreen(config))
        _run_app(app)
        return

    # Both global and project configs exist: Initialize normally with plugins
    plugin_registry = PluginRegistry()
    config = TitanConfig(registry=plugin_registry)  # Plugins will initialize here
    app = TitanApp(config=config)
    _run_app(app)
