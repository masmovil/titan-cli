"""UI model for a Docker container - pre-formatted for display."""
from dataclasses import dataclass


@dataclass
class UIContainer:
    """UI model for a single container - formatted for display."""
    container_id: str
    name: str
    image: str
    state: str
    status: str
    state_icon: str = ""  # "✓" if running, "✗" otherwise
