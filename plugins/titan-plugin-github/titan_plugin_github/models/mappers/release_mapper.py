"""Mapper for GitHub release: Network model -> UI model."""

from ..network.rest import NetworkRelease
from ..view import UIRelease


def from_network_release(network_release: NetworkRelease) -> UIRelease:
    """
    Transform network release model to UI release model.

    Args:
        network_release: Raw release data from gh CLI JSON

    Returns:
        UIRelease ready for rendering
    """
    return UIRelease(
        tag_name=network_release.tag_name,
        title=network_release.name,
        url=network_release.url,
        is_prerelease=network_release.is_prerelease,
        body=network_release.body,
        published_at=network_release.published_at,
        is_draft=network_release.is_draft,
    )
