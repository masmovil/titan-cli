"""
Build Operations

Pure business logic for resolving which configured build targets a step
should build. These functions can be used by any step and are easily testable.
"""
from typing import List, Optional

from titan_cli.core.plugins.models import DockerBuildTargetConfig

from ..exceptions import DockerBuildTargetNotFoundError


def resolve_build_targets(
    build_targets: List[DockerBuildTargetConfig],
    name: Optional[str] = None,
) -> List[DockerBuildTargetConfig]:
    """
    Resolve the list of build targets to build.

    Args:
        build_targets: Project-configured build targets (DockerPluginConfig.build_targets)
        name: Optional single target name to resolve (None resolves all targets)

    Returns:
        List of build targets to build (a single-item list when `name` is given)

    Raises:
        DockerBuildTargetNotFoundError: If `name` is given but not defined in `build_targets`
    """
    if name is None:
        return list(build_targets)

    for target in build_targets:
        if target.name == name:
            return [target]

    raise DockerBuildTargetNotFoundError(
        f"Build target '{name}' is not defined in the project configuration."
    )
