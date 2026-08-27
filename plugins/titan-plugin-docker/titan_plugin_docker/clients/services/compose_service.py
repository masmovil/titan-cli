# plugins/titan-plugin-docker/titan_plugin_docker/clients/services/compose_service.py
"""
Compose Service

Business logic for Docker Compose lifecycle operations.
Uses network layer to execute commands, parses to network models, maps to view models.
"""
import json
from typing import List, Optional

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import DockerNetwork
from ...models.network.compose_status import NetworkComposeService, NetworkComposeStatus
from ...models.view.compose_status import UIComposeStatus
from ...models.mappers import from_network_compose_status
from ...exceptions import DockerCommandError


class ComposeService:
    """
    Service for Docker Compose lifecycle operations.

    Operates on an arbitrary list of service names (or all services when
    none is given). Has no notion of "profiles" or special-cased groups -
    that resolution happens in the operations layer.
    """

    def __init__(self, docker_network: DockerNetwork, compose_file: str = "docker-compose.yml"):
        """
        Initialize Compose service.

        Args:
            docker_network: DockerNetwork instance for command execution
            compose_file: Path to the compose file, relative to the project root
        """
        self.docker = docker_network
        self.compose_file = compose_file

    def _compose_args(self, *args: str) -> List[str]:
        return ["docker", "compose", "-f", self.compose_file, *args]

    @log_client_operation()
    def up(self, services: Optional[List[str]] = None, detach: bool = True) -> ClientResult[List[str]]:
        """
        Start compose services.

        Args:
            services: Service names to start (empty/None starts all services)
            detach: Run containers in the background (default: True)

        Returns:
            ClientResult[List[str]] with the started service names
        """
        try:
            args = self._compose_args("up")
            if detach:
                args.append("-d")
            args.extend(services or [])

            self.docker.run_command(args)
            return ClientSuccess(
                data=services or [],
                message="Started services" if services else "Started all services",
            )
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="COMPOSE_UP_ERROR")

    @log_client_operation()
    def down(self, services: Optional[List[str]] = None) -> ClientResult[List[str]]:
        """
        Stop compose services.

        Args:
            services: Service names to stop (empty/None stops the whole project)

        Returns:
            ClientResult[List[str]] with the stopped service names
        """
        try:
            if services:
                # `docker compose down` doesn't accept service names; use `stop` for a subset.
                args = self._compose_args("stop", *services)
            else:
                args = self._compose_args("down")

            self.docker.run_command(args)
            return ClientSuccess(
                data=services or [],
                message="Stopped services" if services else "Stopped project",
            )
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="COMPOSE_DOWN_ERROR")

    @log_client_operation()
    def status(self, services: Optional[List[str]] = None) -> ClientResult[UIComposeStatus]:
        """
        Get compose project status.

        Args:
            services: Service names to inspect (empty/None inspects all services)

        Returns:
            ClientResult[UIComposeStatus]
        """
        try:
            args = self._compose_args("ps", "--format", "json")
            args.extend(services or [])

            output = self.docker.run_command(args, check=False)
            network_status = NetworkComposeStatus(services=self._parse_ps_output(output))
            ui_status = from_network_compose_status(network_status)

            return ClientSuccess(data=ui_status, message="Status retrieved")
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="COMPOSE_STATUS_ERROR")

    @log_client_operation()
    def list_services(self) -> ClientResult[List[str]]:
        """
        List every service name defined in the compose file, regardless of
        whether it currently has a running/stopped container.

        Returns:
            ClientResult[List[str]]
        """
        try:
            args = self._compose_args("config", "--services")
            output = self.docker.run_command(args)
            services = [line.strip() for line in output.splitlines() if line.strip()]
            return ClientSuccess(data=services, message=f"Found {len(services)} service(s)")
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="COMPOSE_LIST_SERVICES_ERROR")

    @staticmethod
    def _parse_ps_output(output: str) -> List[NetworkComposeService]:
        """
        Parse `docker compose ps --format json` output.

        Handles both a single JSON array (newer Compose) and newline-delimited
        JSON objects (older Compose), since the CLI output shape has changed
        across versions.
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
            NetworkComposeService(
                service=entry.get("Service", ""),
                container_name=entry.get("Name", ""),
                image=entry.get("Image", ""),
                state=entry.get("State", ""),
                status=entry.get("Status", ""),
                health=entry.get("Health", ""),
            )
            for entry in entries
        ]
