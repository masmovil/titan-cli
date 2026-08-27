"""Project inspection services for machine-readable native clients."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from titan_cli.core.services.models import (
    PluginInspection,
    ProjectInspection,
    WorkflowSummary,
)
from titan_cli.core.config import TitanConfig

_CONFIG_CWD_LOCK = threading.Lock()


class ProjectInspectionService:
    """Build a stable project snapshot without coupling clients to internals."""

    def __init__(self, config: TitanConfig) -> None:
        self._config = config

    def inspect_project(self, project_path: Optional[str] = None) -> ProjectInspection:
        """Return project config, plugins, workflows, and diagnostics."""
        config = self._config_for_project_path(project_path)
        workflows = [
            WorkflowSummary(
                name=workflow.name,
                description=workflow.description,
                source=workflow.source,
            )
            for workflow in config.workflows.discover()
        ]
        plugins = self._inspect_plugins(config, workflows)

        project = config.config.project
        config_path = getattr(config, "project_config_path", None)
        project_root = config.project_root.resolve()

        return ProjectInspection(
            name=project.name if project else None,
            type=project.type if project else None,
            path=str(project_root),
            config_path=str(config_path) if config_path else None,
            configured=config_path is not None,
            plugins=plugins,
            workflows=workflows,
            warnings=self._safe_warnings(config),
            sync_events=config.get_plugin_sync_events(),
            diagnostics=self._build_diagnostics(config, plugins),
        )

    def _inspect_plugins(
        self,
        config: TitanConfig,
        workflows: list[WorkflowSummary],
    ) -> list[PluginInspection]:
        failed_plugins = config.registry.list_failed()
        plugin_names = set(config.registry.list_discovered())
        plugin_names.update(config.registry.list_installed())
        plugin_names.update(config.get_enabled_plugins())
        plugin_names.update(failed_plugins.keys())
        plugin_names.update(
            (config.project_config.get("plugins") or {}).keys()
            if config.project_config
            else []
        )

        return [
            self._inspect_plugin(config, plugin_name, failed_plugins, workflows)
            for plugin_name in sorted(plugin_names)
        ]

    def _inspect_plugin(
        self,
        config: TitanConfig,
        plugin_name: str,
        failed_plugins: dict[str, Exception],
        workflows: list[WorkflowSummary],
    ) -> PluginInspection:
        plugin = config.registry.get_plugin(plugin_name)
        enabled = config.is_plugin_enabled(plugin_name)
        installed = plugin_name in config.registry.list_discovered()
        loaded = plugin is not None
        error = failed_plugins.get(plugin_name)

        description = None
        available = False
        steps: list[str] = []
        if plugin is not None:
            description = plugin.description or None
            available = self._safe_plugin_available(plugin)
            steps = self._safe_plugin_steps(plugin)

        return PluginInspection(
            name=plugin_name,
            enabled=enabled,
            installed=installed,
            loaded=loaded,
            available=available,
            version=config.registry.get_plugin_version(plugin_name),
            description=description,
            source=self._safe_plugin_source(config, plugin_name),
            workflows=[
                workflow.name
                for workflow in workflows
                if workflow.source == f"plugin:{plugin_name}"
            ],
            steps=steps,
            error=str(error) if error else None,
        )

    def _safe_plugin_available(self, plugin) -> bool:
        try:
            return bool(plugin.is_available())
        except Exception:
            return False

    def _safe_plugin_steps(self, plugin) -> list[str]:
        try:
            return sorted(plugin.get_steps().keys())
        except Exception:
            return []

    def _safe_plugin_source(self, config: TitanConfig, plugin_name: str) -> dict:
        try:
            return config.get_effective_plugin_source(plugin_name)
        except Exception:
            return {}

    def _safe_warnings(self, config: TitanConfig) -> list[str]:
        warnings = config.get_plugin_warnings()
        if isinstance(warnings, dict):
            return [
                f"{plugin_name}: {warning}"
                for plugin_name, warning in sorted(warnings.items())
            ]
        return [str(warning) for warning in warnings]

    def _build_diagnostics(
        self,
        config: TitanConfig,
        plugins: list[PluginInspection],
    ) -> list[str]:
        diagnostics: list[str] = []
        if getattr(config, "project_config_path", None) is None:
            diagnostics.append("Project is not configured with .titan/config.toml.")

        unavailable = [
            plugin.name
            for plugin in plugins
            if plugin.enabled and (plugin.error or not plugin.loaded or not plugin.available)
        ]
        if unavailable:
            diagnostics.append(
                "Some enabled plugins are not fully available: "
                + ", ".join(unavailable)
                + "."
            )

        if not config.workflows.discover():
            diagnostics.append("No workflows were discovered for this project.")

        return diagnostics

    def _config_for_project_path(self, project_path: Optional[str]) -> TitanConfig:
        """Create a workspace-specific config when a project path is provided."""
        if not project_path:
            return self._config

        workspace_path = Path(project_path).expanduser().resolve()
        registry = self._config.registry.__class__()

        with _CONFIG_CWD_LOCK:
            previous_cwd = Path.cwd()
            try:
                os.chdir(workspace_path)
                return TitanConfig(registry=registry)
            finally:
                os.chdir(previous_cwd)
