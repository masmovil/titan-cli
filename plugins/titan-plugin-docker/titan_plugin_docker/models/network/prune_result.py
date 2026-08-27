"""Network model for a Docker prune invocation - faithful to CLI output."""
from dataclasses import dataclass


@dataclass
class NetworkPruneEntry:
    """
    Network model for a single prune invocation - raw stdout from the CLI.
    """
    target: str  # e.g. "containers", "images", "build_cache", "volumes"
    output: str
