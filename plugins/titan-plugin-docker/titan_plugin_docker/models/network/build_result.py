"""Network model for a Docker build - faithful to `docker buildx build` invocation/output."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class NetworkBuildResult:
    """
    Network model for a build result - raw data from the buildx invocation.
    """
    name: str
    image: str
    tag: str
    platforms: Optional[str] = None  # None when no --platform was passed (builder native)
    target: str = ""
    pushed: bool = False
