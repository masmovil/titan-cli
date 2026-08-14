"""UI model for a Docker prune invocation - pre-formatted for display."""
from dataclasses import dataclass


@dataclass
class UIPruneEntry:
    """UI model for a single prune invocation - formatted for display."""
    target: str
    reclaimed: str  # e.g. "89.45MB", parsed from "Total reclaimed space: ..."
    summary: str
