import pytest

from titan_cli.engine.runs.interaction_validation import validate_interaction_response
from titan_cli.ports.protocol import InteractionAction
from titan_cli.ports.protocol import InteractionRequest
from titan_cli.ports.protocol import InteractionType


def _request(
    interaction_type: InteractionType,
    *,
    actions: list[InteractionAction] | None = None,
    state: dict | None = None,
) -> InteractionRequest:
    return InteractionRequest(
        interaction_id="step:interaction",
        interaction_type=interaction_type,
        message="Continue",
        state=state or {},
        actions=actions or [],
    )


def test_action_list_accepts_only_declared_actions():
    interaction = _request(
        InteractionType.ACTION_LIST,
        actions=[InteractionAction(id="approve", label="Approve")],
    )

    assert validate_interaction_response(interaction, "select", "approve") == {
        "response_type": "select",
        "value": "approve",
    }
    with pytest.raises(ValueError, match="unsupported action"):
        validate_interaction_response(interaction, "select", "delete")


def test_editable_text_requires_complete_edited_content():
    interaction = _request(
        InteractionType.EDITABLE_TEXT,
        actions=[InteractionAction(id="edit", label="Edit")],
        state={"title": "Original", "content": "Body"},
    )

    response = validate_interaction_response(
        interaction,
        "complete",
        {"action": "edit", "title": "Updated", "content": "New body"},
    )

    assert response["value"] == {
        "action": "edit",
        "title": "Updated",
        "content": "New body",
    }
    with pytest.raises(ValueError, match="requires string title and content"):
        validate_interaction_response(
            interaction,
            "complete",
            {"action": "edit", "title": "Updated"},
        )


def test_external_cli_session_requires_integer_exit_code():
    interaction = _request(InteractionType.EXTERNAL_CLI_SESSION)

    assert validate_interaction_response(
        interaction,
        "complete",
        {"exit_code": 0},
    ) == {"response_type": "complete", "value": {"exit_code": 0}}
    assert validate_interaction_response(interaction, "cancel", None) == {
        "response_type": "cancel",
        "value": {"exit_code": 130},
    }
    with pytest.raises(ValueError, match="integer exit_code"):
        validate_interaction_response(interaction, "complete", {"exit_code": "0"})
