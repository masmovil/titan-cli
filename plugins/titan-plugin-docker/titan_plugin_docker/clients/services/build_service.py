# plugins/titan-plugin-docker/titan_plugin_docker/clients/services/build_service.py
"""
Build Service

Business logic for building (and optionally pushing) Docker images.
Uses network layer to execute commands, parses to network models, maps to view models.
"""
from typing import Callable, Optional

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation
from titan_cli.core.plugins.models import DockerBuildTargetConfig

from ..network import DockerNetwork
from ...models.network.build_result import NetworkBuildResult
from ...models.view.build_result import UIBuildResult
from ...models.mappers import from_network_build_result
from ...exceptions import DockerCommandError


class BuildService:
    """
    Service for building and pushing Docker images.

    Operates on a single `DockerBuildTargetConfig` at a time - the caller
    (operations layer) decides which target(s) to build.
    """

    def __init__(self, docker_network: DockerNetwork):
        """
        Initialize Build service.

        Args:
            docker_network: DockerNetwork instance for command execution
        """
        self.docker = docker_network

    @log_client_operation()
    def build_target(
        self,
        target: DockerBuildTargetConfig,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> ClientResult[UIBuildResult]:
        """
        Build (and optionally push) a single configured image.

        Uses `docker buildx build` so a single code path covers both
        single-platform and multi-platform builds.

        Args:
            target: Build target configuration
            on_output: Optional callback invoked with each line of build output as it streams

        Returns:
            ClientResult[UIBuildResult]
        """
        try:
            image_ref = f"{target.image}:{target.tag}"

            args = [
                "docker", "buildx", "build",
                # Line-oriented output: without this buildx may pick its TTY
                # renderer (ANSI cursor-movement redraws) and the streamed
                # "lines" become raw control sequences that garble the console.
                "--progress=plain",
                "-t", image_ref,
                "-f", target.dockerfile,
            ]
            # Omitted when unconfigured so buildx targets its native platform.
            # Passing a platform list the host doesn't match makes buildx emulate
            # through QEMU, so this is never guessed on the project's behalf.
            if target.platforms:
                args.extend(["--platform", target.platforms])
            if target.target:
                args.extend(["--target", target.target])
            if target.push:
                args.append("--push")
            args.append(target.context)

            if on_output:
                self.docker.stream_command(args, on_line=on_output)
            else:
                self.docker.run_command(args)

            network_result = NetworkBuildResult(
                name=target.name,
                image=target.image,
                tag=target.tag,
                platforms=target.platforms,
                target=target.target or "",
                pushed=target.push,
            )
            ui_result = from_network_build_result(network_result)

            return ClientSuccess(data=ui_result, message=f"Built {image_ref}")
        except DockerCommandError as e:
            return ClientError(error_message=str(e), error_code="BUILD_ERROR")
