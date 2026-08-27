"""
Tests for `extract_json_payload()`, the centralized JSON-extraction operation
(review-batching-006) shared by `ai_review_plan`, `ai_review_findings`, and
`ai_thread_resolution`. Replaces the previously duplicated
`_strip_markdown_fences()`/`_extract_json_slice()` free functions (two call
sites) and a third hand-rolled copy inside `ai_thread_resolution`.
"""

from titan_cli.core.result import ClientError, ClientSuccess
from titan_plugin_github.operations.ai_response_parsing_operations import (
    REFORMAT_RETRY_TIMEOUT_SECONDS,
    build_json_reformat_prompt,
    extract_json_payload,
)


def test_extract_json_payload_parses_plain_array():
    result = extract_json_payload('[{"a": 1}, {"b": 2}]', kind="array")

    assert isinstance(result, ClientSuccess)
    assert result.data == [{"a": 1}, {"b": 2}]


def test_extract_json_payload_parses_plain_object():
    result = extract_json_payload('{"a": 1}', kind="object")

    assert isinstance(result, ClientSuccess)
    assert result.data == {"a": 1}


def test_extract_json_payload_strips_markdown_fences_for_array():
    text = '```json\n[{"a": 1}]\n```'

    result = extract_json_payload(text, kind="array")

    assert isinstance(result, ClientSuccess)
    assert result.data == [{"a": 1}]


def test_extract_json_payload_strips_markdown_fences_for_object():
    text = '```json\n{"a": 1}\n```'

    result = extract_json_payload(text, kind="object")

    assert isinstance(result, ClientSuccess)
    assert result.data == {"a": 1}


def test_extract_json_payload_ignores_surrounding_prose():
    text = 'Sure thing, here you go:\n[{"a": 1}]\nHope that helps!'

    result = extract_json_payload(text, kind="array")

    assert isinstance(result, ClientSuccess)
    assert result.data == [{"a": 1}]


def test_extract_json_payload_errors_when_no_array_found():
    result = extract_json_payload("Sorry, I could not find any issues.", kind="array")

    assert isinstance(result, ClientError)
    assert "array" in result.error_message


def test_extract_json_payload_errors_when_no_object_found():
    result = extract_json_payload("Sorry, no plan today.", kind="object")

    assert isinstance(result, ClientError)
    assert "object" in result.error_message


def test_extract_json_payload_errors_on_malformed_json():
    result = extract_json_payload("[1, 2,]", kind="array")

    assert isinstance(result, ClientError)
    assert result.error_code == "JSON_PARSE_ERROR"


def test_build_json_reformat_prompt_includes_previous_output_and_asks_for_json_only():
    prompt = build_json_reformat_prompt("Reported one finding: fix the null check.", kind="array")

    assert "Reported one finding: fix the null check." in prompt
    assert "array" in prompt
    assert "do not redo the analysis" in prompt.lower()


def test_reformat_retry_timeout_is_distinct_from_the_full_analysis_timeout():
    assert REFORMAT_RETRY_TIMEOUT_SECONDS < 300
    assert REFORMAT_RETRY_TIMEOUT_SECONDS < 240
