"""Mapper for Docker containers: Network model → UI model."""
from typing import List

from ..network.container import NetworkContainer
from ..view.container import UIContainer


def from_network_container(network_container: NetworkContainer) -> UIContainer:
    """
    Transform a network container model to a UI container model.

    Args:
        network_container: Raw container data from `docker ps`

    Returns:
        Formatted UI container model
    """
    return UIContainer(
        container_id=network_container.container_id,
        name=network_container.name,
        image=network_container.image,
        state=network_container.state,
        status=network_container.status,
        state_icon="✓" if network_container.state == "running" else "✗",
    )


def from_network_containers(network_containers: List[NetworkContainer]) -> List[UIContainer]:
    """Transform a list of network container models to UI container models."""
    return [from_network_container(container) for container in network_containers]
