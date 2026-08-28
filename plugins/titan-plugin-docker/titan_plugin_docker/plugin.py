# plugins/titan-plugin-docker/titan_plugin_docker/plugin.py
import shutil
from typing import Optional
from pathlib import Path

from titan_cli.core.plugins.models import DockerPluginConfig
from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.config import TitanConfig
from titan_cli.core.security import SecretBroker

from .clients.docker_client import DockerClient
from .exceptions import DockerClientError


class DockerPlugin(TitanPlugin):
    """
    Titan CLI Plugin for Docker operations.
    Provides a DockerClient for interacting with the Docker CLI (compose lifecycle, image builds).
    """

    @property
    def titan_requires(self) -> str:
        # Must stay in sync with the titan-cli dependency in this plugin's
        # pyproject.toml; a repo test enforces the pairing.
        return ">=0.8.0"

    @property
    def name(self) -> str:
        return "docker"

    @property
    def description(self) -> str:
        return "Provides Docker Compose lifecycle management and image build/push workflows."

    @property
    def dependencies(self) -> list[str]:
        return []

    def initialize(self, config: TitanConfig, broker: SecretBroker) -> None:
        """
        Initialize with configuration.

        Reads config from:
            config.config.plugins["docker"].config
        """
        plugin_config_data = self._get_plugin_config(config)
        validated_config = DockerPluginConfig(**plugin_config_data)

        self._client = DockerClient(
            compose_file=validated_config.compose_file,
            service_groups=validated_config.service_groups,
            build_targets=validated_config.build_targets,
        )

    def _get_plugin_config(self, config: TitanConfig) -> dict:
        """
        Extract plugin-specific configuration.

        Args:
            config: TitanConfig instance

        Returns:
            Plugin config dict (empty if not configured)
        """
        if "docker" not in config.config.plugins:
            return {}

        plugin_entry = config.config.plugins["docker"]
        return plugin_entry.config if hasattr(plugin_entry, 'config') else {}

    def get_config_schema(self) -> dict:
        """
        Return JSON schema for plugin configuration.

        Returns:
            JSON schema dict
        """
        return DockerPluginConfig.model_json_schema()

    def is_available(self) -> bool:
        """
        Checks if the Docker CLI is installed and available.
        """
        return shutil.which("docker") is not None and hasattr(self, '_client') and self._client is not None

    def get_client(self) -> DockerClient:
        """
        Returns the initialized DockerClient instance.
        """
        if not hasattr(self, '_client') or self._client is None:
            raise DockerClientError("DockerPlugin not initialized or Docker CLI not available.")
        return self._client

    def get_steps(self) -> dict:
        """
        Returns a dictionary of available workflow steps.
        """
        from .steps.select_service_group_step import select_service_group_step
        from .steps.select_services_to_stop_step import select_services_to_stop_step
        from .steps.compose_up_step import compose_up_step
        from .steps.compose_down_step import compose_down_step
        from .steps.compose_status_step import compose_status_step
        from .steps.build_push_images_step import build_push_images_step
        from .steps.disk_usage_step import disk_usage_step
        from .steps.select_prune_targets_step import select_prune_targets_step
        from .steps.prune_resources_step import prune_resources_step
        from .steps.select_containers_to_remove_step import select_containers_to_remove_step
        from .steps.remove_containers_step import remove_containers_step

        return {
            "select_service_group": select_service_group_step,
            "select_services_to_stop": select_services_to_stop_step,
            "compose_up": compose_up_step,
            "compose_down": compose_down_step,
            "compose_status": compose_status_step,
            "build_push_images": build_push_images_step,
            "disk_usage": disk_usage_step,
            "select_prune_targets": select_prune_targets_step,
            "prune_resources": prune_resources_step,
            "select_containers_to_remove": select_containers_to_remove_step,
            "remove_containers": remove_containers_step,
        }

    @property
    def workflows_path(self) -> Optional[Path]:
        """
        Returns the path to the workflows directory for this plugin.
        """
        return Path(__file__).parent / "workflows"
