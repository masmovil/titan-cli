"""Mapper for Docker disk usage: Network model → UI model."""
from ..network.disk_usage import NetworkDiskUsage
from ..view.disk_usage import UIDiskUsageEntry, UIDiskUsage


def from_network_disk_usage(network_usage: NetworkDiskUsage) -> UIDiskUsage:
    """
    Transform network disk usage model to UI disk usage model.

    Args:
        network_usage: Raw disk usage data from `docker system df`

    Returns:
        Formatted UI disk usage model
    """
    entries = [
        UIDiskUsageEntry(
            resource_type=entry.resource_type,
            total_count=entry.total_count,
            active=entry.active,
            size=entry.size,
            reclaimable=entry.reclaimable,
            has_reclaimable=not entry.reclaimable.strip().startswith("0B"),
        )
        for entry in network_usage.entries
    ]

    return UIDiskUsage(entries=entries)
