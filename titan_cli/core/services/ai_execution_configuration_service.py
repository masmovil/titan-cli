"""Application service for persisted AI execution configuration."""

from titan_cli.ai.router.enums import AIProviderType
from titan_cli.core.config import TitanConfig
from titan_cli.external_cli.adapters.registry import HEADLESS_ADAPTER_REGISTRY
from titan_cli.external_cli.adapters.base import resolve_cli_executable
from titan_cli.external_cli.configs import CLI_REGISTRY


class AIExecutionConfigurationService:
    """Manage the CLI default and per-task provider routing for native clients."""

    def __init__(self, config: TitanConfig) -> None:
        self._config = config

    def get_configuration(self) -> dict[str, object]:
        """Return Titan's canonical persisted execution configuration."""
        ai_config = self._config.get_ai_connections_config()
        preferences = self._config.get_ai_preferences_config()

        clis = []
        for cli_id, cli_config in CLI_REGISTRY.items():
            clis.append(
                {
                    "id": cli_id,
                    "name": cli_config.get("display_name", cli_id),
                    "command": cli_id,
                    "is_installed": resolve_cli_executable(cli_id) is not None,
                    "supports_headless": cli_id in HEADLESS_ADAPTER_REGISTRY,
                    "supports_interactive": True,
                }
            )

        task_preferences = [
            {
                "task_id": task_id,
                "provider": preference.get("provider"),
            }
            for task_id, preference in sorted(preferences.get("tasks", {}).items())
        ]

        return {
            "default_cli": ai_config.get("default_cli"),
            "clis": clis,
            "task_preferences": task_preferences,
            "provider_types": [provider.value for provider in AIProviderType],
        }

    def set_default_cli(self, cli_id: str) -> dict[str, object]:
        """Persist the single CLI used by all CLI-routed tasks."""
        if cli_id not in CLI_REGISTRY:
            known = ", ".join(CLI_REGISTRY)
            raise ValueError(f"Unknown AI CLI '{cli_id}'. Known CLIs: {known}")
        self._config.set_default_ai_cli(cli_id)
        return self.get_configuration()

    def clear_default_cli(self) -> dict[str, object]:
        """Clear the persisted default CLI."""
        self._config.clear_default_ai_cli()
        return self.get_configuration()

    def set_task_provider(self, task_id: str, provider: str) -> dict[str, object]:
        """Persist which provider kind executes one AI task."""
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("AI task ID cannot be empty.")
        try:
            provider_type = AIProviderType(provider)
        except ValueError as exc:
            known = ", ".join(item.value for item in AIProviderType)
            raise ValueError(
                f"Unknown AI provider type '{provider}'. Known types: {known}"
            ) from exc

        self._config.upsert_task_ai_preference(
            normalized_task_id,
            {"provider": provider_type.value},
        )
        return self.get_configuration()

    def clear_task_provider(self, task_id: str) -> dict[str, object]:
        """Restore one task to its workflow policy default."""
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("AI task ID cannot be empty.")
        self._config.delete_task_ai_preference(normalized_task_id)
        return self.get_configuration()
