from unittest.mock import MagicMock, patch

import pytest

from titan_plugin_docker.plugin import DockerPlugin
from titan_plugin_docker.exceptions import DockerClientError


def test_docker_plugin_basic_properties() -> None:
    plugin = DockerPlugin()

    assert plugin.name == "docker"
    assert plugin.dependencies == []


def test_docker_plugin_exposes_public_steps() -> None:
    plugin = DockerPlugin()

    steps = plugin.get_steps()

    assert set(steps) == {
        "select_service_group",
        "select_services_to_stop",
        "compose_up",
        "compose_down",
        "compose_status",
        "build_push_images",
        "disk_usage",
        "select_prune_targets",
        "prune_resources",
        "select_containers_to_remove",
        "remove_containers",
    }


def test_docker_plugin_exposes_workflows_path() -> None:
    plugin = DockerPlugin()

    assert plugin.workflows_path.name == "workflows"


def test_docker_plugin_exposes_config_schema() -> None:
    plugin = DockerPlugin()

    schema = plugin.get_config_schema()

    assert "service_groups" in schema["properties"]
    assert "build_targets" in schema["properties"]


def test_docker_plugin_get_client_before_initialize_raises() -> None:
    plugin = DockerPlugin()

    with pytest.raises(DockerClientError):
        plugin.get_client()


def test_docker_plugin_initialize_builds_client_from_config() -> None:
    plugin = DockerPlugin()
    config = MagicMock()
    config.config.plugins = {
        "docker": MagicMock(
            config={
                "compose_file": "docker-compose.yml",
                "service_groups": {"infra": ["db", "ollama"]},
                "build_targets": [
                    {
                        "name": "frontend",
                        "dockerfile": "packages/frontend/Dockerfile",
                        "image": "ghcr.io/finxo/economy-frontend",
                    }
                ],
            }
        )
    }
    secrets = MagicMock()

    with patch("shutil.which", return_value="/usr/bin/docker"):
        plugin.initialize(config, secrets)
        client = plugin.get_client()

    assert client.compose_file == "docker-compose.yml"
    assert client.service_groups == {"infra": ["db", "ollama"]}
    assert [t.name for t in client.build_targets] == ["frontend"]


def test_docker_plugin_is_available_requires_client_and_cli() -> None:
    plugin = DockerPlugin()

    with patch("shutil.which", return_value=None):
        assert plugin.is_available() is False
