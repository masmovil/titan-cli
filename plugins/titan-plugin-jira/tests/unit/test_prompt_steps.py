from types import SimpleNamespace
from unittest.mock import MagicMock

from titan_cli.engine import Error, Success, WorkflowContext
from titan_plugin_jira.steps.prompt_select_issue_step import prompt_select_issue_step


class InteractionStub:
    def __init__(self, answer: str) -> None:
        self.begin_step = MagicMock()
        self.end_step = MagicMock()
        self.ask_text = MagicMock(return_value=answer)
        self.text = MagicMock()
        self.success_text = MagicMock()
        self.error_text = MagicMock()


def test_prompt_select_issue_step_uses_interaction_port():
    issue = SimpleNamespace(key="ECAPP-123", summary="Improve login flow")
    interaction = InteractionStub(answer="1")
    ctx = WorkflowContext(
        secret_broker=MagicMock(),
        data={"jira_issues": [issue]},
        textual=None,
        interaction=interaction,
    )

    result = prompt_select_issue_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["jira_issue_key"] == "ECAPP-123"
    assert result.metadata["selected_issue"] is issue
    interaction.begin_step.assert_called_once()
    interaction.end_step.assert_called_once_with("success")


def test_prompt_select_issue_step_rejects_invalid_interaction_input():
    issue = SimpleNamespace(key="ECAPP-123", summary="Improve login flow")
    interaction = InteractionStub(answer="abc")
    ctx = WorkflowContext(
        secret_broker=MagicMock(),
        data={"jira_issues": [issue]},
        textual=None,
        interaction=interaction,
    )

    result = prompt_select_issue_step(ctx)

    assert isinstance(result, Error)
    assert "not a number" in result.message
    interaction.end_step.assert_called_once_with("error")
