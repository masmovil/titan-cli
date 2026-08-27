"""Dependency composition for Titan command entrypoints."""

from titan_cli.core.services.ai_connection_service import AIConnectionService
from titan_cli.core.services.plugin_service import PluginService
from titan_cli.core.services.project_inspection_service import (
    ProjectInspectionService,
)
from titan_cli.engine.runs.service import WorkflowRunService
from titan_cli.core.config import TitanConfig


class TitanRuntimeContainer:
    """Build application services used by CLI, headless, and automation adapters."""

    def config(self, *, skip_plugin_init: bool = False) -> TitanConfig:
        """Return a Titan configuration instance for the current execution context."""
        return TitanConfig(skip_plugin_init=skip_plugin_init)

    def workflow_run_service(self) -> WorkflowRunService:
        """Return the workflow run service."""
        return WorkflowRunService(config=self.config())

    def project_inspection_service(self) -> ProjectInspectionService:
        """Return the project inspection service."""
        return ProjectInspectionService(config=self.config())

    def ai_config(self) -> TitanConfig:
        """Return config for AI settings without loading plugins."""
        return self.config(skip_plugin_init=True)

    def ai_connection_service(self) -> AIConnectionService:
        """Return the AI connection application service."""
        return AIConnectionService(config=self.ai_config())

    def plugin_service(self) -> PluginService:
        """Return the plugin management application service."""
        return PluginService(config=self.config())
