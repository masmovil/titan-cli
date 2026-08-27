import pytest

from titan_plugin_docker.operations.compose_operations import (
    resolve_services,
    list_group_names,
    resolve_stop_selection,
)
from titan_plugin_docker.exceptions import DockerServiceGroupNotFoundError


def test_resolve_services_explicit_takes_precedence() -> None:
    result = resolve_services(
        service_groups={"infra": ["db"]},
        group="infra",
        explicit_services=["frontend"],
    )

    assert result == ["frontend"]


def test_resolve_services_by_group_name() -> None:
    result = resolve_services(
        service_groups={"infra": ["db", "ollama"]},
        group="infra",
    )

    assert result == ["db", "ollama"]


def test_resolve_services_unknown_group_raises() -> None:
    with pytest.raises(DockerServiceGroupNotFoundError):
        resolve_services(service_groups={"infra": ["db"]}, group="observability")


def test_resolve_services_no_group_returns_empty_for_all() -> None:
    result = resolve_services(service_groups={"infra": ["db"]})

    assert result == []


def test_list_group_names_preserves_order() -> None:
    result = list_group_names({"infra": ["db"], "backend-only": ["backend"]})

    assert result == ["infra", "backend-only"]


def test_resolve_stop_selection_all_checked_means_full_down() -> None:
    result = resolve_stop_selection(
        all_services=["db", "backend", "frontend"],
        selected_services=["db", "backend", "frontend"],
    )

    assert result == []


def test_resolve_stop_selection_all_checked_ignores_order() -> None:
    result = resolve_stop_selection(
        all_services=["db", "backend", "frontend"],
        selected_services=["frontend", "db", "backend"],
    )

    assert result == []


def test_resolve_stop_selection_subset_stops_only_checked() -> None:
    result = resolve_stop_selection(
        all_services=["db", "backend", "frontend"],
        selected_services=["backend", "frontend"],
    )

    assert result == ["backend", "frontend"]
