"""WorkflowContext no longer carries a SecretManager — only a scoped broker."""

import dataclasses
from unittest.mock import MagicMock

import pytest

from titan_cli.engine.context import WorkflowContext


def test_secrets_is_not_a_context_field():
    field_names = {f.name for f in dataclasses.fields(WorkflowContext)}
    assert "secrets" not in field_names
    assert "secret_broker" in field_names


def test_context_constructs_without_secrets():
    ctx = WorkflowContext()
    assert ctx.secret_broker is None


def test_context_accepts_secret_broker():
    broker = MagicMock()
    ctx = WorkflowContext(secret_broker=broker)
    assert ctx.secret_broker is broker


def test_legacy_secrets_property_warns_and_returns_backing_manager():
    legacy = MagicMock()
    ctx = WorkflowContext(_legacy_secrets=legacy)
    with pytest.warns(DeprecationWarning, match="ctx.secrets is deprecated"):
        assert ctx.secrets is legacy


def test_legacy_secrets_property_defaults_to_none():
    ctx = WorkflowContext()
    with pytest.warns(DeprecationWarning):
        assert ctx.secrets is None
