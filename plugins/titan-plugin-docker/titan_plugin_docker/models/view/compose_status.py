"""UI models for Docker Compose status - pre-formatted for display."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class UIComposeService:
    """UI model for a single compose service - formatted for display."""
    service: str
    container_name: str
    image: str
    state: str
    status: str
    health: str = ""
    state_icon: str = ""  # "✓" if running, "✗" otherwise


@dataclass
class UIComposeStatus:
    """UI model for compose project status - formatted for display."""
    services: List[UIComposeService] = field(default_factory=list)
    all_running: bool = False
    summary: str = ""  # e.g. "3/3 running"
