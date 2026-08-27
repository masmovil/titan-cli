"""
Container Operations

Pure business logic for deciding which host containers are safe candidates
for removal. These functions can be used by any step and are easily testable.
"""
from typing import List

from ..models.view.container import UIContainer


def list_removable_containers(containers: List[UIContainer]) -> List[UIContainer]:
    """
    Filter containers down to those safe to offer for removal (not running).

    Args:
        containers: Every container on the host

    Returns:
        Containers whose state is not "running"
    """
    return [container for container in containers if container.state != "running"]
