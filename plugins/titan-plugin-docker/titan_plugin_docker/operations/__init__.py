"""Operations layer for Docker plugin."""
from .compose_operations import resolve_services, list_group_names, resolve_stop_selection
from .build_operations import resolve_build_targets
from .container_operations import list_removable_containers

__all__ = [
    "resolve_services",
    "list_group_names",
    "resolve_stop_selection",
    "resolve_build_targets",
    "list_removable_containers",
]
