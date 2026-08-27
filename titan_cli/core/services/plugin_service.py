"""Plugin-oriented application services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli
import tomli_w

from titan_cli.core.services.models import (
    KnownPluginSummary,
    PluginMutationResult,
    PluginSourcePreview,
)
from titan_cli.core.config import TitanConfig
from titan_cli.core.plugins.available import KNOWN_PLUGINS
from titan_cli.core.plugins.community_sources import (
    PluginChannel,
    build_raw_pyproject_url,
    detect_host,
    fetch_pyproject_toml,
    get_github_token,
    parse_plugin_metadata,
    parse_repo_url,
    resolve_ref_to_commit_sha,
    validate_url,
)
from titan_cli.core.plugins.runtime import PluginRuntimeManager


class PluginService:
    """Service layer for plugin inspection and orchestration."""

    def __init__(
        self,
        config: TitanConfig,
        runtime_manager: PluginRuntimeManager | None = None,
    ) -> None:
        self._config = config
        self._runtime_manager = runtime_manager or PluginRuntimeManager()

    def list_plugins(self) -> list[str]:
        """List installed plugins known to the current registry."""
        return sorted(self._config.registry.list_installed())

    def list_enabled_plugins(self) -> list[str]:
        """List enabled plugins for the active project/config context."""
        return sorted(self._config.get_enabled_plugins())

    def list_available_plugins(self) -> list[KnownPluginSummary]:
        """Return curated plugins available for guided installation."""
        return [
            KnownPluginSummary(
                name=plugin["name"],
                description=plugin["description"],
                package_name=plugin["package_name"],
                dependencies=list(plugin.get("dependencies", [])),
                source=plugin.get("source", "official"),
                repo_url=plugin.get("repo_url"),
                recommended_ref=plugin.get("recommended_ref"),
            )
            for plugin in KNOWN_PLUGINS
        ]

    def get_config_schema(self, plugin_name: str) -> dict[str, Any]:
        """Return a plugin configuration JSON schema."""
        plugin = self._config.registry.get_plugin(plugin_name)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_name}' is not available.")

        if not hasattr(plugin, "get_config_schema"):
            return {"type": "object", "properties": {}}

        schema = plugin.get_config_schema()
        if not isinstance(schema, dict):
            raise ValueError(f"Plugin '{plugin_name}' returned an invalid schema.")
        return schema

    def set_enabled(self, plugin_name: str, enabled: bool) -> PluginMutationResult:
        """Persist the project-level enabled flag for a plugin."""
        project_cfg = self._load_project_config()
        plugin_table = self._plugin_table(project_cfg, plugin_name)
        plugin_table["enabled"] = enabled
        self._write_project_config(project_cfg)
        return PluginMutationResult(
            plugin_name=plugin_name,
            changed=True,
            message=f"Plugin '{plugin_name}' {'enabled' if enabled else 'disabled'}.",
            source=self._config.get_effective_plugin_source(plugin_name),
            config=dict(plugin_table.get("config", {})),
        )

    def configure_plugin(
        self,
        plugin_name: str,
        config_values: dict[str, Any],
    ) -> PluginMutationResult:
        """Persist project-level plugin configuration values."""
        project_cfg = self._load_project_config()
        plugin_table = self._plugin_table(project_cfg, plugin_name)
        plugin_table["enabled"] = plugin_table.get("enabled", True)
        config_table = plugin_table.setdefault("config", {})
        config_table.update(config_values)
        self._write_project_config(project_cfg)
        return PluginMutationResult(
            plugin_name=plugin_name,
            changed=True,
            message=f"Plugin '{plugin_name}' configured.",
            source=self._config.get_effective_plugin_source(plugin_name),
            config=dict(config_table),
        )

    def set_dev_source(self, plugin_name: str, path: str) -> PluginMutationResult:
        """Persist a user-local development source override for a plugin."""
        resolved_path = str(Path(path).expanduser().resolve())
        self._config.set_global_plugin_source(
            plugin_name,
            channel=PluginChannel.DEV_LOCAL,
            path=resolved_path,
        )
        return PluginMutationResult(
            plugin_name=plugin_name,
            changed=True,
            message=f"Development source configured for '{plugin_name}'.",
            source={"channel": PluginChannel.DEV_LOCAL, "path": resolved_path},
        )

    def clear_dev_source(self, plugin_name: str) -> PluginMutationResult:
        """Remove a user-local development source override for a plugin."""
        self._config.clear_global_plugin_source(plugin_name)
        return PluginMutationResult(
            plugin_name=plugin_name,
            changed=True,
            message=f"Development source removed for '{plugin_name}'.",
            source=self._config.get_effective_plugin_source(plugin_name),
        )

    def preview_stable_source(self, raw_url: str) -> PluginSourcePreview:
        """Validate and preview a stable community plugin source."""
        validate_url(raw_url)
        base_url, requested_ref = parse_repo_url(raw_url)
        token = get_github_token()
        resolved_commit = self._resolve_commit(base_url, requested_ref, token)
        metadata = self._fetch_metadata(base_url, resolved_commit, token)
        return self._build_preview(
            repo_url=base_url,
            requested_ref=requested_ref,
            resolved_commit=resolved_commit,
            metadata=metadata,
        )

    def install_stable_source(self, raw_url: str) -> PluginMutationResult:
        """Pin a stable community plugin source and prepare its runtime."""
        preview = self.preview_stable_source(raw_url)
        if not preview.titan_entry_points:
            raise ValueError("Plugin source does not declare any Titan entry points.")

        plugin_name = next(iter(preview.titan_entry_points.keys()))
        self._save_stable_source(
            plugin_name=plugin_name,
            repo_url=preview.repo_url,
            requested_ref=preview.requested_ref,
            resolved_commit=preview.resolved_commit,
        )
        self._runtime_manager.ensure_stable_runtime(
            plugin_name=plugin_name,
            repo_url=preview.repo_url,
            resolved_commit=preview.resolved_commit,
            token=get_github_token(),
        )
        return PluginMutationResult(
            plugin_name=plugin_name,
            changed=True,
            message=f"Plugin '{plugin_name}' installed.",
            source={
                "channel": PluginChannel.STABLE,
                "repo_url": preview.repo_url,
                "requested_ref": preview.requested_ref,
                "resolved_commit": preview.resolved_commit,
            },
        )

    def _load_project_config(self) -> dict[str, Any]:
        path = self._project_config_path()
        if not path.exists():
            return {}

        with open(path, "rb") as file:
            return tomli.load(file)

    def _write_project_config(self, data: dict[str, Any]) -> None:
        path = self._project_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as file:
            tomli_w.dump(data, file)

    def _project_config_path(self) -> Path:
        return self._config.project_config_path or (
            self._config.project_root / ".titan" / "config.toml"
        )

    def _plugin_table(
        self,
        project_cfg: dict[str, Any],
        plugin_name: str,
    ) -> dict[str, Any]:
        plugins_table = project_cfg.setdefault("plugins", {})
        return plugins_table.setdefault(plugin_name, {})

    def _resolve_commit(
        self,
        base_url: str,
        requested_ref: str,
        token: str | None,
    ) -> str:
        host = detect_host(base_url)
        resolved_commit, error = resolve_ref_to_commit_sha(
            base_url,
            requested_ref,
            host,
            token,
        )
        if error or not resolved_commit:
            raise ValueError(
                f"Could not resolve '{requested_ref}' to a commit SHA: {error}"
            )
        return resolved_commit

    def _fetch_metadata(
        self,
        base_url: str,
        resolved_commit: str,
        token: str | None,
    ) -> dict[str, Any]:
        host = detect_host(base_url)
        raw_url = build_raw_pyproject_url(base_url, resolved_commit, host)
        if raw_url is None:
            raise ValueError("Could not build the metadata URL for this repository.")

        content, error = fetch_pyproject_toml(raw_url, token)
        if error == "not_found":
            raise ValueError("Repository or version not found.")
        if error == "network_error":
            raise ValueError("Could not reach the repository.")
        if not content:
            raise ValueError("Repository did not return plugin metadata.")

        metadata = parse_plugin_metadata(content)
        if metadata.get("parse_error"):
            raise ValueError("Could not read plugin metadata from pyproject.toml.")
        return metadata

    def _build_preview(
        self,
        *,
        repo_url: str,
        requested_ref: str,
        resolved_commit: str,
        metadata: dict[str, Any],
    ) -> PluginSourcePreview:
        entry_points = dict(metadata.get("titan_entry_points") or {})
        warnings = []
        if not entry_points:
            warnings.append("This package does not declare a Titan plugin entry point.")

        return PluginSourcePreview(
            repo_url=repo_url,
            requested_ref=requested_ref,
            resolved_commit=resolved_commit,
            package_name=metadata.get("name"),
            version=metadata.get("version"),
            description=metadata.get("description"),
            authors=list(metadata.get("authors") or []),
            titan_entry_points=entry_points,
            python_dependencies=list(metadata.get("python_deps") or []),
            warnings=warnings,
        )

    def _save_stable_source(
        self,
        *,
        plugin_name: str,
        repo_url: str,
        requested_ref: str,
        resolved_commit: str,
    ) -> None:
        project_cfg = self._load_project_config()
        plugin_table = self._plugin_table(project_cfg, plugin_name)
        plugin_table["enabled"] = True
        source_table = plugin_table.setdefault("source", {})
        source_table["channel"] = PluginChannel.STABLE
        source_table["repo_url"] = repo_url
        source_table["requested_ref"] = requested_ref
        source_table["resolved_commit"] = resolved_commit
        self._write_project_config(project_cfg)
