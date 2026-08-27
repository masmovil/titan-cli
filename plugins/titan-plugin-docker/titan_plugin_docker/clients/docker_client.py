# plugins/titan-plugin-docker/titan_plugin_docker/clients/docker_client.py
"""
Docker Client Facade

Unified API that delegates to specialized services.
All methods return ClientResult for consistent error handling.
"""
from typing import Callable, Dict, List, Optional

from titan_cli.core.result import ClientResult
from titan_cli.core.plugins.models import DockerBuildTargetConfig

from .network import DockerNetwork
from .services import ComposeService, BuildService, PruneService, ContainerService
from ..models.view import UIComposeStatus, UIBuildResult, UIDiskUsage, UIPruneEntry, UIContainer


class DockerClient:
    """
    Docker client facade - delegates to specialized services.

    All public methods return ClientResult[T] for consistent error handling.
    Uses pattern matching (match/case) for result handling in operations and steps.

    Also carries the project's `service_groups` and `build_targets` config
    (set from `DockerPluginConfig` at plugin initialization), so steps can
    resolve them via `ctx.docker.service_groups` / `ctx.docker.build_targets`.
    """

    def __init__(
        self,
        project_path: str = ".",
        compose_file: str = "docker-compose.yml",
        service_groups: Optional[Dict[str, List[str]]] = None,
        build_targets: Optional[List[DockerBuildTargetConfig]] = None,
    ):
        """
        Initialize Docker client.

        Args:
            project_path: Path to the project root (default: current directory)
            compose_file: Path to the compose file, relative to the project root
            service_groups: Project-configured named service groups
            build_targets: Project-configured build targets
        """
        self.project_path = project_path
        self.compose_file = compose_file
        self.service_groups = service_groups or {}
        self.build_targets = build_targets or []

        # Initialize network layer
        self.network = DockerNetwork(project_path=project_path)

        # Initialize services
        self.compose_service = ComposeService(self.network, compose_file)
        self.build_service = BuildService(self.network)
        self.prune_service = PruneService(self.network)
        self.container_service = ContainerService(self.network)

    # ===== Compose Methods =====

    def compose_up(self, services: Optional[List[str]] = None, detach: bool = True) -> ClientResult[List[str]]:
        """Start compose services (empty/None starts all services)."""
        return self.compose_service.up(services=services, detach=detach)

    def compose_down(self, services: Optional[List[str]] = None) -> ClientResult[List[str]]:
        """Stop compose services (empty/None stops the whole project)."""
        return self.compose_service.down(services=services)

    def compose_status(self, services: Optional[List[str]] = None) -> ClientResult[UIComposeStatus]:
        """Get compose project status (empty/None inspects all services)."""
        return self.compose_service.status(services=services)

    def list_services(self) -> ClientResult[List[str]]:
        """List every service name defined in the compose file."""
        return self.compose_service.list_services()

    # ===== Build Methods =====

    def build_target(
        self,
        target: DockerBuildTargetConfig,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> ClientResult[UIBuildResult]:
        """Build (and optionally push) a single configured image, optionally streaming build output via `on_output`."""
        return self.build_service.build_target(target, on_output=on_output)

    # ===== Prune Methods =====

    def disk_usage(self) -> ClientResult[UIDiskUsage]:
        """Get a host-wide breakdown of Docker's disk usage."""
        return self.prune_service.disk_usage()

    def prune(self, targets: List[str]) -> ClientResult[List[UIPruneEntry]]:
        """Prune the given host-wide resource categories (see `PRUNE_COMMANDS` for valid keys)."""
        return self.prune_service.prune(targets)

    # ===== Container Methods =====

    def list_containers(self) -> ClientResult[List[UIContainer]]:
        """List every container on the host, running or stopped (not scoped to this project)."""
        return self.container_service.list_containers()

    def remove_containers(self, container_ids: List[str]) -> ClientResult[List[str]]:
        """Remove the given (stopped) containers."""
        return self.container_service.remove_containers(container_ids)
