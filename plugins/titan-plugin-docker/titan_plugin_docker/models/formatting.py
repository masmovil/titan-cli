"""Shared formatting/parsing helpers for Docker network -> view mappers."""
import re

_RECLAIMED_SPACE_RE = re.compile(r"Total reclaimed space:\s*(.+)", re.IGNORECASE)


def parse_reclaimed_space(output: str) -> str:
    """
    Extract the reclaimed space amount from `docker ... prune` output.

    Args:
        output: Raw stdout from a `docker container/image/builder/volume prune` command

    Returns:
        The reclaimed space amount (e.g. "89.45MB"), or "0B" if not found
    """
    match = _RECLAIMED_SPACE_RE.search(output)
    if not match:
        return "0B"
    return match.group(1).strip()
