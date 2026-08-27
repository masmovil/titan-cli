"""Pure validation for inbound interaction responses."""

from __future__ import annotations

from typing import Any

from titan_cli.ports.protocol import InteractionRequest
from titan_cli.ports.protocol import InteractionType


def validate_interaction_response(
    interaction: InteractionRequest,
    response_type: str,
    value: Any,
) -> dict[str, object]:
    """Validate an inbound interaction response against the pending interaction.

    Raises:
        ValueError: If the response does not satisfy the interaction contract.
    """
    if interaction.interaction_type == InteractionType.ITEM_REVIEW:
        return _validate_item_review_response(interaction, response_type, value)

    return {
        "response_type": response_type,
        "value": value,
    }


def _validate_item_review_response(
    interaction: InteractionRequest,
    response_type: str,
    value: Any,
) -> dict[str, object]:
    if response_type != "complete":
        raise ValueError(
            f"Unsupported item_review response_type: {response_type or 'empty'}"
        )

    if not isinstance(value, dict):
        raise ValueError("item_review response value must be an object")

    raw_items = value.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("item_review response items must be a list")

    raw_interaction_items = interaction.state.get("items") or []
    item_index: dict[str, dict[str, Any]] = {}
    for raw_item in raw_interaction_items:
        if isinstance(raw_item, dict):
            item_id = raw_item.get("id")
            editable = bool(raw_item.get("editable", False))
        else:
            item_id = getattr(raw_item, "id", None)
            editable = bool(getattr(raw_item, "editable", False))
        if item_id is None:
            continue
        item_index[str(item_id)] = {"editable": editable}

    allowed_actions = {str(action) for action in interaction.state.get("allowed_actions") or []}
    edit_state = interaction.state.get("edit")
    edit_enabled = bool(
        edit_state.get("enabled", False)
        if isinstance(edit_state, dict)
        else getattr(edit_state, "enabled", False)
    )
    exit_requested = bool(value.get("exit_requested", False))
    seen_item_ids: set[str] = set()

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("item_review decision entries must be objects")

        item_id = raw_item.get("item_id")
        action = raw_item.get("action")
        if item_id is None or action is None:
            raise ValueError("item_review decisions require item_id and action")

        item_id = str(item_id)
        action = str(action)

        if item_id not in item_index:
            raise ValueError(f"item_review response references unknown item_id '{item_id}'")
        if item_id in seen_item_ids:
            raise ValueError(f"item_review response contains duplicate decision for '{item_id}'")
        if action == "exit":
            raise ValueError("item_review exit must be expressed with exit_requested")
        if action not in allowed_actions:
            raise ValueError(f"item_review response uses unsupported action '{action}'")

        if action == "edit":
            if not edit_enabled:
                raise ValueError("item_review edit action is disabled for this session")
            if not item_index[item_id]["editable"]:
                raise ValueError(f"item_review item '{item_id}' is not editable")
            if not isinstance(raw_item.get("content"), str):
                raise ValueError(
                    f"item_review edit decision for '{item_id}' requires string content"
                )

        seen_item_ids.add(item_id)

    if not exit_requested and len(seen_item_ids) != len(item_index):
        raise ValueError(
            "item_review complete response must include one decision for every item"
        )

    return {
        "response_type": response_type,
        "value": value,
    }
