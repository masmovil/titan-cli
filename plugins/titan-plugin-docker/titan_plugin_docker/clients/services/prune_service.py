# plugins/titan-plugin-docker/titan_plugin_docker/clients/services/prune_service.py
"""
Prune Service

Business logic for host-wide disk usage reporting and pruning.
Uses network layer to execute commands, parses to network models, maps to view models.

Unlike ComposeService/BuildService, this operates on the whole Docker host,
not a single project's compose file - disk usage and prune targets aren't
scoped to any particular project.
"""
import json
from typing import List

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import DockerNetwork
from ...models.network.disk_usage import NetworkDiskUsageEntry, NetworkDiskUsage
from ...models.network.prune_result import NetworkPruneEntry
from ...models.view.disk_usage import UIDiskUsage
from ...models.view.prune_result import UIPruneEntry
from ...models.mappers import from_network_disk_usage, from_network_prune_entry
from ...exceptions import DockerCommandError

# Maps a prune target key to its docker CLI subcommand.
# `images` only removes dangling images (safe default); it does not pass
# `-a`, so images still referenced by a tag are left alone.
PRUNE_COMMANDS = {
    "containers": ["docker", "container", "prune", "-f"],
    "images": ["docker", "image", "prune", "-f"],
    "build_cache": ["docker", "builder", "prune", "-f"],
    "volumes": ["docker", "volume", "prune", "-f"],
}


class PruneService:
    """
    Service for host-wide disk usage reporting and cleanup.

    Docker itself refuses to remove a volume attached to any container
    (running or stopped), so `docker volume prune` only ever removes
    orphaned volumes - this service does not need to special-case that.
    """

    def __init__(self, docker_network: DockerNetwork):
        """
        Initialize Prune service.

        Args:
            docker_network: DockerNetwork instance for command execution
        """
        self.docker = docker_network

    @log_client_operation()
    def disk_usage(self) -> ClientResult[UIDiskUsage]:
        """
        Get a breakdown of Docker's disk usage (images, containers, local
        volumes, build cache).

        Returns:
            ClientResult[UIDiskUsage]
        """
        try:
            output = self.docker.run_command(["docker", "system", "df", "--format", "{{json .}}"])
            entries = self._parse_df_output(output)
            ui_usage = from_network_disk_usage(NetworkDiskUsage(entries=entries))

            return ClientSuccess(data=ui_usage, message="Disk usage retrieved")
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="DISK_USAGE_ERROR")

    @log_client_operation()
    def prune(self, targets: List[str]) -> ClientResult[List[UIPruneEntry]]:
        """
        Prune the given resource categories.

        Args:
            targets: Subset of `PRUNE_COMMANDS` keys ("containers", "images", "build_cache", "volumes")

        Returns:
            ClientResult[List[UIPruneEntry]] with one entry per pruned target
        """
        try:
            results = []
            for target in targets:
                args = PRUNE_COMMANDS[target]
                output = self.docker.run_command(args)
                network_entry = NetworkPruneEntry(target=target, output=output)
                results.append(from_network_prune_entry(network_entry))

            return ClientSuccess(data=results, message=f"Pruned {len(results)} target(s)")
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="PRUNE_ERROR")

    @staticmethod
    def _parse_df_output(output: str) -> List[NetworkDiskUsageEntry]:
        """
        Parse `docker system df --format '{{json .}}'` output (one JSON object per line).
        """
        entries = []
        for line in output.splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            entries.append(
                NetworkDiskUsageEntry(
                    resource_type=entry.get("Type", ""),
                    total_count=entry.get("TotalCount", ""),
                    active=entry.get("Active", ""),
                    size=entry.get("Size", ""),
                    reclaimable=entry.get("Reclaimable", ""),
                )
            )
        return entries
