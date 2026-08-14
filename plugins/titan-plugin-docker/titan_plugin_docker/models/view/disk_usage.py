"""UI models for Docker disk usage - pre-formatted for display."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class UIDiskUsageEntry:
    """UI model for a single disk usage row - formatted for display."""
    resource_type: str
    total_count: str
    active: str
    size: str
    reclaimable: str
    has_reclaimable: bool = False


@dataclass
class UIDiskUsage:
    """UI model for the full disk usage report."""
    entries: List[UIDiskUsageEntry] = field(default_factory=list)
