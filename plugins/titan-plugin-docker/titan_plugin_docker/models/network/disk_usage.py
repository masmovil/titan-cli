"""Network models for Docker disk usage - faithful to `docker system df` output."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class NetworkDiskUsageEntry:
    """
    Network model for a single disk usage row - raw data from `docker system df`.
    """
    resource_type: str  # e.g. "Images", "Containers", "Local Volumes", "Build Cache"
    total_count: str
    active: str
    size: str
    reclaimable: str


@dataclass
class NetworkDiskUsage:
    """Network model for the full disk usage report."""
    entries: List[NetworkDiskUsageEntry] = field(default_factory=list)
