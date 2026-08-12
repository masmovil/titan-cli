"""Response contracts: what shape a call declares, and how it recovers it."""

import json

import pytest

from titan_cli.ai.agents.contracts import JsonContract, TextContract


ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
}


def _issue_contract(**overrides) -> JsonContract:
    kwargs = {
        "schema": ISSUE_SCHEMA,
        "required": ("category", "title", "body"),
    }
    kwargs.update(overrides)
    return JsonContract(**kwargs)


# --- TextContract ---------------------------------------------------------


def test_free_prose_always_parses():
    """A prose contract never spends a retry - that is why it is a real choice."""
    result = TextContract().parse("  just some text  ")

    assert result.ok
    assert result.data == "just some text"


def test_free_prose_adds_nothing_to_the_prompt():
    assert TextContract().format_instructions() == ""


def test_sections_are_split_and_keyed():
    contract = TextContract(sections=("TITLE", "DESCRIPTION"))

    result = contract.parse("TITLE: feat: Add thing\n\nDESCRIPTION:\nThe long body.")

    assert result.ok
    assert result.data == {"title": "feat: Add thing", "description": "The long body."}


def test_sections_use_the_declared_key_map():
    contract = TextContract(
        sections=("CATEGORY", "DESCRIPTION"),
        keys={"CATEGORY": "category", "DESCRIPTION": "body"},
    )

    result = contract.parse("CATEGORY: bug\nDESCRIPTION: it broke")

    assert result.data == {"category": "bug", "body": "it broke"}


def test_sections_survive_a_preamble_and_odd_casing():
    """A CLI is likelier than a remote model to introduce itself first."""
    contract = TextContract(sections=("TITLE", "DESCRIPTION"))

    result = contract.parse("Sure, here you go!\n\ntitle: fix: Thing\n\ndescription:\nBody here.")

    assert result.ok
    assert result.data["title"] == "fix: Thing"
    assert result.data["description"] == "Body here."


def test_sections_are_read_in_the_order_they_appear():
    contract = TextContract(sections=("TITLE", "DESCRIPTION"))

    result = contract.parse("DESCRIPTION:\nBody first.\n\nTITLE: feat: Reordered")

    assert result.ok
    assert result.data == {"title": "feat: Reordered", "description": "Body first."}


def test_a_duplicated_section_label_is_a_failure():
    contract = TextContract(sections=("TITLE", "DESCRIPTION"))

    result = contract.parse(
        "TITLE: feat: Real title\n\nDESCRIPTION:\nA list of drafts:\nTITLE: draft"
    )

    assert not result.ok
    assert "TITLE" in result.error


def test_a_missing_section_is_a_failure():
    contract = TextContract(sections=("TITLE", "DESCRIPTION"))

    result = contract.parse("TITLE: only this one")

    assert not result.ok
    assert "DESCRIPTION" in result.error


# --- JsonContract ---------------------------------------------------------


def test_bare_json_parses():
    payload = {"category": "bug", "title": "fix: Thing", "body": "Body"}

    result = _issue_contract().parse(json.dumps(payload))

    assert result.ok
    assert result.data == payload


def test_fenced_json_parses():
    result = _issue_contract().parse(
        '```json\n{"category": "bug", "title": "t", "body": "b"}\n```'
    )

    assert result.ok
    assert result.data["category"] == "bug"


def test_json_wrapped_in_prose_parses():
    """Exactly what a CLI returns when it ignores the schema and chats first."""
    result = _issue_contract().parse(
        'Here is the issue:\n{"category": "bug", "title": "t", "body": "b"}\nHope that helps!'
    )

    assert result.ok
    assert result.data["title"] == "t"


def test_a_body_containing_json_does_not_truncate_the_answer():
    """The outermost braces win, so a markdown body with its own JSON survives."""
    body = 'Run this:\n```json\n{"nested": true}\n```\ndone'
    payload = {"category": "bug", "title": "t", "body": body}

    result = _issue_contract().parse(json.dumps(payload))

    assert result.ok
    assert result.data["body"] == body


def test_a_required_name_missing_from_the_schema_is_rejected_at_construction():
    """Validation only walks the declared properties, so an undeclared required
    name would otherwise never be enforced - the broken contract must not build."""
    with pytest.raises(ValueError, match="labels"):
        _issue_contract(required=("title", "labels"))


def test_a_missing_required_field_fails():
    result = _issue_contract().parse('{"category": "bug", "title": "t"}')

    assert not result.ok
    assert "body" in result.error


def test_a_missing_optional_field_takes_its_default():
    contract = _issue_contract(
        required=("title",),
        defaults={"category": "feature", "title": "New issue", "body": ""},
    )

    result = contract.parse('{"title": "t"}')

    assert result.ok
    assert result.data == {"category": "feature", "title": "t", "body": ""}


def test_a_wrong_type_on_a_required_field_fails():
    result = _issue_contract().parse('{"category": 3, "title": "t", "body": "b"}')

    assert not result.ok
    assert "category" in result.error


def test_a_boolean_does_not_satisfy_an_integer_field():
    contract = JsonContract(
        schema={"type": "object", "properties": {"count": {"type": "integer"}}},
        required=("count",),
    )

    result = contract.parse('{"count": true}')

    assert not result.ok


def test_a_nullable_field_accepts_null():
    contract = JsonContract(
        schema={"type": "object", "properties": {"line": {"type": ["integer", "null"]}}},
        required=("line",),
    )

    assert contract.parse('{"line": null}').ok
    assert contract.parse('{"line": 12}').ok


def test_truncated_json_fails_rather_than_being_guessed_at():
    """A cut-off answer earns the repair retry; repairing it here would guess."""
    result = _issue_contract().parse('{"category": "bug", "title": "t", "body": "half a bod')

    assert not result.ok


def test_a_json_array_is_not_an_object():
    result = _issue_contract().parse('[{"category": "bug"}]')

    assert not result.ok


def test_prose_with_no_json_at_all_fails():
    result = _issue_contract().parse("I could not do that, sorry.")

    assert not result.ok


# --- fallback -------------------------------------------------------------


def test_the_text_fallback_runs_when_json_parsing_fails():
    contract = _issue_contract(
        fallback=TextContract(
            sections=("CATEGORY", "TITLE", "DESCRIPTION"),
            keys={"CATEGORY": "category", "TITLE": "title", "DESCRIPTION": "body"},
        )
    )

    result = contract.parse("CATEGORY: bug\nTITLE: fix: Thing\nDESCRIPTION:\nThe body.")

    assert result.ok
    assert result.data == {"category": "bug", "title": "fix: Thing", "body": "The body."}


def test_a_failing_fallback_reports_both_reasons():
    contract = _issue_contract(fallback=TextContract(sections=("CATEGORY",)))

    result = contract.parse("nothing usable here")

    assert not result.ok
    assert "fallback also failed" in result.error


def test_user_text_mentioning_a_label_does_not_beat_valid_json():
    """The JSON path runs first, so a body quoting 'CATEGORY:' stays in the body."""
    contract = _issue_contract(
        fallback=TextContract(sections=("CATEGORY",), keys={"CATEGORY": "category"})
    )
    payload = {"category": "bug", "title": "t", "body": "The log said CATEGORY: feature"}

    result = contract.parse(json.dumps(payload))

    assert result.data["category"] == "bug"


# --- what the contract tells the model and the provider -------------------


def test_the_schema_is_offered_to_providers_that_can_enforce_it():
    assert _issue_contract().json_schema() == ISSUE_SCHEMA
    assert TextContract().json_schema() is None


def test_defaults_decide_whether_a_final_failure_is_fatal():
    assert _issue_contract().degraded_value() is None
    assert _issue_contract(defaults={"category": "feature"}).degraded_value() == {
        "category": "feature"
    }
    assert TextContract().degraded_value() is None


def test_the_repair_prompt_carries_the_previous_answer_and_the_format():
    contract = TextContract(sections=("TITLE",))

    prompt = contract.repair_prompt("some malformed thing")

    assert "some malformed thing" in prompt
    assert "TITLE:" in prompt
