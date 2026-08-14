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


def test_secrets_attribute_is_gone():
    """The deprecated ctx.secrets property is deleted, not just discouraged."""
    ctx = WorkflowContext()
    with pytest.raises(AttributeError):
        _ = ctx.secrets
