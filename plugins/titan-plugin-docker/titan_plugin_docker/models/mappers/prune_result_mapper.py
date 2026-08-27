"""Mapper for Docker prune results: Network model → UI model."""
from ..formatting import parse_reclaimed_space
from ..network.prune_result import NetworkPruneEntry
from ..view.prune_result import UIPruneEntry


def from_network_prune_entry(network_entry: NetworkPruneEntry) -> UIPruneEntry:
    """
    Transform a network prune entry to a UI prune entry.

    Args:
        network_entry: Raw stdout from a `docker ... prune` command

    Returns:
        Formatted UI prune entry with the reclaimed space parsed out
    """
    reclaimed = parse_reclaimed_space(network_entry.output)

    return UIPruneEntry(
        target=network_entry.target,
        reclaimed=reclaimed,
        summary=f"Pruned {network_entry.target}: reclaimed {reclaimed}",
    )
