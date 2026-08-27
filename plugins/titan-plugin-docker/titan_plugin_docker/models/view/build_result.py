"""UI model for a Docker build - pre-formatted for display."""
from dataclasses import dataclass


@dataclass
class UIBuildResult:
    """UI model for a build result - formatted for display."""
    name: str
    image_ref: str  # e.g. "ghcr.io/org/app:latest"
    platforms: str
    target: str = ""
    pushed: bool = False
    status_icon: str = "✓"
    summary: str = ""
