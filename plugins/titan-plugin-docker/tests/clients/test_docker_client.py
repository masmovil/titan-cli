import json
from unittest.mock import patch

from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.core.plugins.models import DockerBuildTargetConfig
from titan_plugin_docker.clients.docker_client import DockerClient
from titan_plugin_docker.exceptions import DockerCommandError


def _make_client(**kwargs) -> DockerClient:
    with patch("shutil.which", return_value="/usr/bin/docker"):
        return DockerClient(**kwargs)


def test_compose_up_delegates_to_compose_service() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", return_value="") as run_command:
        result = client.compose_up(services=["db"])

    assert isinstance(result, ClientSuccess)
    assert result.data == ["db"]
    args = run_command.call_args.args[0]
    assert args[:4] == ["docker", "compose", "-f", "docker-compose.yml"]
    assert args[-1] == "db"


def test_compose_up_wraps_command_failures() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", side_effect=DockerCommandError("boom")):
        result = client.compose_up()

    assert isinstance(result, ClientError)
    assert result.error_code == "COMPOSE_UP_ERROR"


def test_compose_status_parses_json_array() -> None:
    client = _make_client()
    ps_output = json.dumps([
        {"Service": "db", "Name": "postgres_container", "Image": "pgvector/pgvector:pg17", "State": "running", "Status": "Up 2 hours", "Health": "healthy"},
        {"Service": "backend", "Name": "backend_container", "Image": "economy-backend", "State": "exited", "Status": "Exited (1)", "Health": ""},
    ])

    with patch.object(client.network, "run_command", return_value=ps_output):
        result = client.compose_status()

    assert isinstance(result, ClientSuccess)
    assert result.data.summary == "1/2 running"
    assert result.data.all_running is False
    assert [s.service for s in result.data.services] == ["db", "backend"]


def test_list_services_parses_newline_output() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", return_value="db\nbackend\nfrontend\n") as run_command:
        result = client.list_services()

    assert isinstance(result, ClientSuccess)
    assert result.data == ["db", "backend", "frontend"]
    args = run_command.call_args.args[0]
    assert args == ["docker", "compose", "-f", "docker-compose.yml", "config", "--services"]


def test_list_services_wraps_command_failures() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", side_effect=DockerCommandError("boom")):
        result = client.list_services()

    assert isinstance(result, ClientError)
    assert result.error_code == "COMPOSE_LIST_SERVICES_ERROR"


def test_build_target_delegates_to_build_service() -> None:
    client = _make_client()
    target = DockerBuildTargetConfig(
        name="frontend",
        dockerfile="packages/frontend/Dockerfile",
        image="ghcr.io/finxo/economy-frontend",
        target="production",
        push=True,
    )

    with patch.object(client.network, "run_command", return_value="") as run_command:
        result = client.build_target(target)

    assert isinstance(result, ClientSuccess)
    assert result.data.image_ref == "ghcr.io/finxo/economy-frontend:latest"
    assert result.data.pushed is True
    args = run_command.call_args.args[0]
    assert args[:3] == ["docker", "buildx", "build"]
    assert "--push" in args
    assert "--target" in args and "production" in args


def test_build_target_omits_platform_flag_when_unconfigured() -> None:
    client = _make_client()
    target = DockerBuildTargetConfig(
        name="frontend",
        dockerfile="packages/frontend/Dockerfile",
        image="ghcr.io/finxo/economy-frontend",
    )

    with patch.object(client.network, "run_command", return_value="") as run_command:
        result = client.build_target(target)

    assert isinstance(result, ClientSuccess)
    args = run_command.call_args.args[0]
    assert "--platform" not in args
    assert result.data.platforms == "builder native"


def test_build_target_passes_configured_platforms() -> None:
    client = _make_client()
    target = DockerBuildTargetConfig(
        name="frontend",
        dockerfile="packages/frontend/Dockerfile",
        image="ghcr.io/finxo/economy-frontend",
        platforms="linux/amd64,linux/arm64",
    )

    with patch.object(client.network, "run_command", return_value="") as run_command:
        result = client.build_target(target)

    assert isinstance(result, ClientSuccess)
    args = run_command.call_args.args[0]
    assert args[args.index("--platform") + 1] == "linux/amd64,linux/arm64"
    assert result.data.platforms == "linux/amd64,linux/arm64"


def test_build_target_streams_output_when_callback_given() -> None:
    client = _make_client()
    target = DockerBuildTargetConfig(
        name="frontend",
        dockerfile="packages/frontend/Dockerfile",
        image="ghcr.io/finxo/economy-frontend",
    )
    lines = []

    def fake_stream_command(args, on_line, check=True, cwd=None):
        on_line("#1 [internal] load build definition")
        on_line("#2 DONE 0.1s")
        return "#1 [internal] load build definition\n#2 DONE 0.1s"

    with patch.object(client.network, "stream_command", side_effect=fake_stream_command) as stream_command:
        result = client.build_target(target, on_output=lines.append)

    assert isinstance(result, ClientSuccess)
    assert lines == ["#1 [internal] load build definition", "#2 DONE 0.1s"]
    stream_command.assert_called_once()


def test_disk_usage_parses_ndjson_output() -> None:
    client = _make_client()
    df_output = "\n".join([
        json.dumps({"Type": "Images", "TotalCount": "15", "Active": "7", "Size": "36.45GB", "Reclaimable": "19.08GB (52%)"}),
        json.dumps({"Type": "Containers", "TotalCount": "7", "Active": "7", "Size": "89.45MB", "Reclaimable": "0B (0%)"}),
    ])

    with patch.object(client.network, "run_command", return_value=df_output):
        result = client.disk_usage()

    assert isinstance(result, ClientSuccess)
    assert [e.resource_type for e in result.data.entries] == ["Images", "Containers"]
    assert result.data.entries[0].has_reclaimable is True
    assert result.data.entries[1].has_reclaimable is False


def test_prune_runs_one_command_per_target() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", return_value="Total reclaimed space: 1.2GB") as run_command:
        result = client.prune(["containers", "images"])

    assert isinstance(result, ClientSuccess)
    assert [e.target for e in result.data] == ["containers", "images"]
    assert all(e.reclaimed == "1.2GB" for e in result.data)
    assert run_command.call_args_list[0].args[0] == ["docker", "container", "prune", "-f"]
    assert run_command.call_args_list[1].args[0] == ["docker", "image", "prune", "-f"]


def test_prune_wraps_command_failures() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", side_effect=DockerCommandError("boom")):
        result = client.prune(["volumes"])

    assert isinstance(result, ClientError)
    assert result.error_code == "PRUNE_ERROR"


def test_list_containers_parses_ndjson_output() -> None:
    client = _make_client()
    ps_output = "\n".join([
        json.dumps({"ID": "abc123", "Names": "db_container", "Image": "postgres", "State": "running", "Status": "Up 2 hours"}),
        json.dumps({"ID": "def456", "Names": "old_container", "Image": "old-app", "State": "exited", "Status": "Exited (0) 3 days ago"}),
    ])

    with patch.object(client.network, "run_command", return_value=ps_output):
        result = client.list_containers()

    assert isinstance(result, ClientSuccess)
    assert [c.name for c in result.data] == ["db_container", "old_container"]
    assert result.data[0].state_icon == "✓"
    assert result.data[1].state_icon == "✗"


def test_remove_containers_delegates_to_container_service() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", return_value="") as run_command:
        result = client.remove_containers(["abc123", "def456"])

    assert isinstance(result, ClientSuccess)
    assert result.data == ["abc123", "def456"]
    assert run_command.call_args.args[0] == ["docker", "rm", "abc123", "def456"]


def test_remove_containers_wraps_command_failures() -> None:
    client = _make_client()

    with patch.object(client.network, "run_command", side_effect=DockerCommandError("container is running")):
        result = client.remove_containers(["abc123"])

    assert isinstance(result, ClientError)
    assert result.error_code == "REMOVE_CONTAINERS_ERROR"
