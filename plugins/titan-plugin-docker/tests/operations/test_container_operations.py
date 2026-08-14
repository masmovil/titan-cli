from titan_plugin_docker.models.view.container import UIContainer
from titan_plugin_docker.operations.container_operations import list_removable_containers


def _container(name: str, state: str) -> UIContainer:
    return UIContainer(container_id=name, name=name, image="image", state=state, status=state)


def test_list_removable_containers_excludes_running() -> None:
    containers = [
        _container("db", "running"),
        _container("old_backend", "exited"),
        _container("paused_thing", "paused"),
    ]

    result = list_removable_containers(containers)

    assert [c.name for c in result] == ["old_backend", "paused_thing"]


def test_list_removable_containers_empty_when_all_running() -> None:
    containers = [_container("db", "running"), _container("backend", "running")]

    assert list_removable_containers(containers) == []


def test_list_removable_containers_handles_empty_list() -> None:
    assert list_removable_containers([]) == []
