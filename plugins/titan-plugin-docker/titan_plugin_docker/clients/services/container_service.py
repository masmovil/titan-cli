# plugins/titan-plugin-docker/titan_plugin_docker/clients/services/container_service.py
"""
Container Service

Business logic for host-wide container inspection and removal.
Uses network layer to execute commands, parses to network models, maps to view models.

Unlike ComposeService, this operates on every container on the host, not a
single project's compose file.
"""
import json
from typing import List

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import DockerNetwork
from ...models.network.container import NetworkContainer
from ...models.view.container import UIContainer
from ...models.mappers import from_network_containers
from ...exceptions import DockerCommandError


class ContainerService:
    """
    Service for host-wide container inspection and removal.

    `remove_containers` intentionally does not pass `-f` to `docker rm`, so
    Docker itself refuses (and this surfaces as a `ClientError`) if a caller
    tries to remove a still-running container.
    """

    def __init__(self, docker_network: DockerNetwork):
        """
        Initialize Container service.

        Args:
            docker_network: DockerNetwork instance for command execution
        """
        self.docker = docker_network

    @log_client_operation()
    def list_containers(self) -> ClientResult[List[UIContainer]]:
        """
        List every container on the host, running or stopped.

        Returns:
            ClientResult[List[UIContainer]]
        """
        try:
            output = self.docker.run_command(["docker", "ps", "-a", "--format", "json"])
            network_containers = self._parse_ps_output(output)
            ui_containers = from_network_containers(network_containers)

            return ClientSuccess(data=ui_containers, message=f"Found {len(ui_containers)} container(s)")
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="LIST_CONTAINERS_ERROR")

    @log_client_operation()
    def remove_containers(self, container_ids: List[str]) -> ClientResult[List[str]]:
        """
        Remove the given (stopped) containers.

        Args:
            container_ids: Container IDs or names to remove

        Returns:
            ClientResult[List[str]] with the removed container IDs/names
        """
        try:
            self.docker.run_command(["docker", "rm", *container_ids])
            return ClientSuccess(data=container_ids, message=f"Removed {len(container_ids)} container(s)")
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="REMOVE_CONTAINERS_ERROR")

    @staticmethod
    def _parse_ps_output(output: str) -> List[NetworkContainer]:
        """
        Parse `docker ps -a --format json` output.

        Handles both a single JSON array and newline-delimited JSON objects,
        since the CLI output shape has changed across Docker versions.
        """
        if not output.strip():
            return []

        try:
            entries = json.loads(output)
            if isinstance(entries, dict):
                entries = [entries]
        except json.JSONDecodeError:
            entries = [json.loads(line) for line in output.splitlines() if line.strip()]

        return [
            NetworkContainer(
                container_id=entry.get("ID", ""),
                name=entry.get("Names", ""),
                image=entry.get("Image", ""),
                state=entry.get("State", ""),
                status=entry.get("Status", ""),
            )
            for entry in entries
        ]
