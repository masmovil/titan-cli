import pytest

from titan_cli.core.plugins.models import DockerBuildTargetConfig
from titan_plugin_docker.operations.build_operations import resolve_build_targets
from titan_plugin_docker.exceptions import DockerBuildTargetNotFoundError


def _target(name: str) -> DockerBuildTargetConfig:
    return DockerBuildTargetConfig(name=name, dockerfile=f"{name}/Dockerfile", image=f"ghcr.io/org/{name}")


def test_resolve_build_targets_returns_all_when_no_name_given() -> None:
    targets = [_target("frontend"), _target("backend")]

    result = resolve_build_targets(targets)

    assert result == targets


def test_resolve_build_targets_returns_single_match() -> None:
    frontend = _target("frontend")
    targets = [frontend, _target("backend")]

    result = resolve_build_targets(targets, name="frontend")

    assert result == [frontend]


def test_resolve_build_targets_unknown_name_raises() -> None:
    targets = [_target("frontend")]

    with pytest.raises(DockerBuildTargetNotFoundError):
        resolve_build_targets(targets, name="backup")


def test_resolve_build_targets_empty_config_returns_empty() -> None:
    assert resolve_build_targets([]) == []
