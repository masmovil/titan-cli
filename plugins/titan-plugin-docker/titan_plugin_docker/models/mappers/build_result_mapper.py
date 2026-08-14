"""Mapper for Docker build result: Network model → UI model."""
from ..network.build_result import NetworkBuildResult
from ..view.build_result import UIBuildResult


def from_network_build_result(network_result: NetworkBuildResult) -> UIBuildResult:
    """
    Transform network build result model to UI build result model.

    Args:
        network_result: Raw data from the buildx invocation

    Returns:
        Formatted UI build result model with an image reference and summary
    """
    image_ref = f"{network_result.image}:{network_result.tag}"
    platforms = network_result.platforms or "builder native"
    summary = f"Built {image_ref}"
    if network_result.pushed:
        summary += " (pushed)"

    return UIBuildResult(
        name=network_result.name,
        image_ref=image_ref,
        platforms=platforms,
        target=network_result.target,
        pushed=network_result.pushed,
        status_icon="✓",
        summary=summary,
    )
