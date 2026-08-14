"""Remote availability = valid config + importable deps + key existence.

No provider is ever constructed and no secret value is ever read: the checker
only asks the scoped broker whether the connection's key exists.
"""

from unittest.mock import MagicMock, patch

import pytest

from titan_cli.ai.router.availability import AIAvailabilityChecker
from titan_cli.ai.router.enums import AIProviderType
from titan_cli.core.models import AIConfig, AIConnectionType, AIProviderConfig


def _config(**connections):
    return AIConfig(
        default_connection=next(iter(connections), None),
        connections=connections,
    )


def _direct(name="Work"):
    return AIProviderConfig(
        name=name,
        connection_type=AIConnectionType.DIRECT_PROVIDER,
        provider="anthropic",
        default_model="claude-sonnet-4-5",
    )


def _gateway(name="Gateway"):
    return AIProviderConfig(
        name=name,
        connection_type=AIConnectionType.GATEWAY,
        gateway_backend="openai_compatible",
        base_url="http://localhost:4000",
        default_model="gpt-5",
    )


def _broker(existing_keys):
    broker = MagicMock()
    broker.exists.side_effect = lambda key: key in existing_keys
    return broker


@pytest.fixture
def deps_available():
    with patch(
        "titan_cli.ai.router.availability.dependencies_available", return_value=True
    ) as mock:
        yield mock


def _remote_ids(checker):
    return [c.identifier for c in checker.available_remote_connections()]


def test_direct_connection_requires_its_key(deps_available):
    config = _config(work=_direct(), personal=_direct("Personal"))
    checker = AIAvailabilityChecker(config, _broker({"work_api_key"}))

    assert _remote_ids(checker) == ["work"]


def test_gateway_available_without_key(deps_available):
    config = _config(gw=_gateway())
    checker = AIAvailabilityChecker(config, _broker(set()))

    assert _remote_ids(checker) == ["gw"]


def test_missing_dependencies_make_connection_unavailable():
    config = _config(work=_direct())
    with patch(
        "titan_cli.ai.router.availability.dependencies_available", return_value=False
    ):
        checker = AIAvailabilityChecker(config, _broker({"work_api_key"}))
        assert _remote_ids(checker) == []


def test_no_broker_reports_nothing_available(deps_available):
    config = _config(work=_direct())
    checker = AIAvailabilityChecker(config, None)

    assert checker.available_remote_connections() == []


def test_no_config_reports_nothing_available(deps_available):
    checker = AIAvailabilityChecker(None, _broker({"work_api_key"}))

    assert checker.available_remote_connections() == []


def test_available_connection_is_remote_type(deps_available):
    config = _config(work=_direct())
    checker = AIAvailabilityChecker(config, _broker({"work_api_key"}))

    [candidate] = checker.available_remote_connections()
    assert candidate.provider == AIProviderType.REMOTE
    assert candidate.identifier == "work"
