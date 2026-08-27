from unittest.mock import MagicMock

from titan_cli.core.workflows.models import WorkflowStepModel
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Error, Success
from titan_cli.engine.workflow_executor import WorkflowExecutor


def make_executor_with_plugin(step_name: str, step_func):
    plugin = MagicMock()
    plugin.get_steps.return_value = {step_name: step_func}

    plugin_registry = MagicMock()
    plugin_registry.get_plugin.return_value = plugin

    workflow_registry = MagicMock()
    return WorkflowExecutor(plugin_registry, workflow_registry)


def make_context():
    return WorkflowContext(data={})


def test_plugin_step_uses_requires_field_before_params_requires():
    step_func = MagicMock(return_value=Success("ok"))
    executor = make_executor_with_plugin("run", step_func)
    ctx = make_context()
    ctx.data["field_var"] = "present"

    step = WorkflowStepModel(
        id="run",
        plugin="github",
        step="run",
        requires=["field_var"],
        params={"requires": ["legacy_var"]},
    )

    result = executor._execute_plugin_step(step, ctx)

    assert isinstance(result, Success)
    step_func.assert_called_once_with(ctx)


def test_plugin_step_falls_back_to_params_requires_when_field_is_empty():
    step_func = MagicMock(return_value=Success("ok"))
    executor = make_executor_with_plugin("run", step_func)
    ctx = make_context()

    step = WorkflowStepModel(
        id="run",
        plugin="github",
        step="run",
        params={"requires": ["legacy_var"]},
    )

    result = executor._execute_plugin_step(step, ctx)

    assert isinstance(result, Error)
    assert "legacy_var" in result.message
    step_func.assert_not_called()
