from titan_plugin_docker.models.network.disk_usage import NetworkDiskUsageEntry, NetworkDiskUsage
from titan_plugin_docker.models.network.prune_result import NetworkPruneEntry
from titan_plugin_docker.models.network.container import NetworkContainer
from titan_plugin_docker.models.mappers import (
    from_network_disk_usage,
    from_network_prune_entry,
    from_network_container,
)


def test_from_network_disk_usage_flags_reclaimable_entries() -> None:
    usage = NetworkDiskUsage(
        entries=[
            NetworkDiskUsageEntry(resource_type="Images", total_count="15", active="7", size="36.45GB", reclaimable="19.08GB (52%)"),
            NetworkDiskUsageEntry(resource_type="Containers", total_count="7", active="7", size="89.45MB", reclaimable="0B (0%)"),
        ]
    )

    ui = from_network_disk_usage(usage)

    assert ui.entries[0].has_reclaimable is True
    assert ui.entries[1].has_reclaimable is False


def test_from_network_prune_entry_parses_reclaimed_space() -> None:
    entry = NetworkPruneEntry(target="containers", output="Deleted Containers:\nabc\n\nTotal reclaimed space: 12.3MB")

    ui = from_network_prune_entry(entry)

    assert ui.target == "containers"
    assert ui.reclaimed == "12.3MB"
    assert "12.3MB" in ui.summary


def test_from_network_container_sets_state_icon() -> None:
    running = from_network_container(NetworkContainer(container_id="1", name="db", image="postgres", state="running", status="Up 2 hours"))
    exited = from_network_container(NetworkContainer(container_id="2", name="old", image="app", state="exited", status="Exited (0)"))

    assert running.state_icon == "✓"
    assert exited.state_icon == "✗"
