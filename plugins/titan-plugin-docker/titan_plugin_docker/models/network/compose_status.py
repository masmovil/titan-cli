"""Network models for Docker Compose status - faithful to `docker compose ps` output."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class NetworkComposeService:
    """
    Network model for a single compose service - raw data from `docker compose ps`.
    """
    service: str
    container_name: str
    image: str
    state: str
    status: str
    health: str = ""


@dataclass
class NetworkComposeStatus:
    """
    Network model for compose project status - raw data from `docker compose ps`.
    """
    services: List[NetworkComposeService] = field(default_factory=list)
