"""Network model for a Docker container - faithful to `docker ps` output."""
from dataclasses import dataclass


@dataclass
class NetworkContainer:
    """
    Network model for a single container - raw data from `docker ps`.

    Host-wide: not scoped to any project's compose file.
    """
    container_id: str
    name: str
    image: str
    state: str
    status: str
