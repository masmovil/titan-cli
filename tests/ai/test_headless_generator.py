"""Generation through a local CLI: what it forwards, what it drops, how it fails."""

import pytest

from titan_cli.ai.exceptions import AIProviderError
from titan_cli.ai.headless_generator import AGENT_DISALLOWED_TOOLS, HeadlessGenerator
from titan_cli.ai.models import AIMessage
from titan_cli.external_cli.adapters.base import HeadlessResponse, SupportedCLI


SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}}


class FakeAdapter:
    """Records the execute() call so the test can assert what was forwarded."""

    def __init__(
        self,
        *,
        stdout: str = "an answer",
        exit_code: int = 0,
        stderr: str = "",
        structured: bool = True,
        tool_restriction: bool = True,
        available: bool = True,
    ):
        self._response = HeadlessResponse(stdout=stdout, stderr=stderr, exit_code=exit_code)
        self.supports_structured_output = structured
        self.supports_tool_restriction = tool_restriction
        self.supports_effort_control = False
        self.supports_model_selection = True
        self.cli_name = SupportedCLI.CLAUDE
        self._available = available
        self.call = None

    def execute(self, prompt, **kwargs):
        self.call = {"prompt": prompt, **kwargs}
        return self._response

    def is_available(self) -> bool:
        return self._available


def _messages():
    return [
        AIMessage(role="system", content="You are an agent."),
        AIMessage(role="user", content="Do the thing."),
    ]


def test_the_conversation_is_flattened_into_one_prompt():
    adapter = FakeAdapter()

    HeadlessGenerator(adapter).generate(_messages())

    assert adapter.call["prompt"] == "You are an agent.\n\nDo the thing."


def test_message_order_is_preserved():
    """The contract's format block is last, and must stay last."""
    adapter = FakeAdapter()
    messages = [
        AIMessage(role="system", content="system"),
        AIMessage(role="user", content="task\n\nFORMAT"),
    ]

    HeadlessGenerator(adapter).generate(messages)

    assert adapter.call["prompt"].endswith("FORMAT")


def test_empty_messages_are_skipped():
    adapter = FakeAdapter()
    messages = [AIMessage(role="system", content=""), AIMessage(role="user", content="ask")]

    HeadlessGenerator(adapter).generate(messages)

    assert adapter.call["prompt"] == "ask"


def test_stdout_becomes_the_response_content():
    adapter = FakeAdapter(stdout="the model said this")

    response = HeadlessGenerator(adapter).generate(_messages())

    assert response.content == "the model said this"


def test_no_token_usage_is_reported():
    """A CLI reports none, and inventing a number would show the user a lie."""
    response = HeadlessGenerator(FakeAdapter()).generate(_messages())

    assert response.usage == {}


# --- capability gating ----------------------------------------------------


def test_a_schema_reaches_a_cli_that_can_enforce_it():
    adapter = FakeAdapter(structured=True)

    HeadlessGenerator(adapter).generate(_messages(), json_schema=SCHEMA)

    assert adapter.call["json_schema"] == SCHEMA


def test_a_schema_is_withheld_from_a_cli_that_cannot_enforce_it():
    """Gemini and codex accept the argument and drop it; not sending it is honest."""
    adapter = FakeAdapter(structured=False)

    HeadlessGenerator(adapter).generate(_messages(), json_schema=SCHEMA)

    assert adapter.call["json_schema"] is None


def test_tools_are_withheld_by_default_so_an_unwatched_run_cannot_edit():
    adapter = FakeAdapter(tool_restriction=True)

    HeadlessGenerator(adapter).generate(_messages())

    assert adapter.call["disallowed_tools"] == list(AGENT_DISALLOWED_TOOLS)
    assert "Edit" in adapter.call["disallowed_tools"]
    assert "Write" in adapter.call["disallowed_tools"]


def test_reading_the_repo_stays_allowed():
    """Reading real code is the reason to pick a CLI over a remote connection."""
    for tool in ("Read", "Grep", "Glob"):
        assert tool not in AGENT_DISALLOWED_TOOLS


def test_tool_restriction_is_skipped_when_the_cli_ignores_it():
    adapter = FakeAdapter(tool_restriction=False)

    HeadlessGenerator(adapter).generate(_messages())

    assert adapter.call["disallowed_tools"] is None


def test_max_tokens_and_temperature_are_accepted_and_dropped():
    """A CLI has no such knobs; the contract is what bounds the answer."""
    adapter = FakeAdapter()

    HeadlessGenerator(adapter).generate(_messages(), max_tokens=8192, temperature=0.9)

    assert "max_tokens" not in adapter.call
    assert "temperature" not in adapter.call


def test_cwd_and_timeout_are_forwarded():
    adapter = FakeAdapter()

    HeadlessGenerator(adapter, cwd="/repo", timeout=42).generate(_messages())

    assert adapter.call["cwd"] == "/repo"
    assert adapter.call["timeout"] == 42


def test_the_model_override_is_forwarded_and_named_in_the_response():
    adapter = FakeAdapter()

    response = HeadlessGenerator(adapter, model="sonnet").generate(_messages())

    assert adapter.call["model"] == "sonnet"
    assert response.model == "sonnet"


def test_without_an_override_the_response_names_the_cli():
    response = HeadlessGenerator(FakeAdapter()).generate(_messages())

    assert response.model == "claude"


# --- failures -------------------------------------------------------------


def test_a_timeout_says_so_by_name():
    adapter = FakeAdapter(exit_code=124, stdout="")

    with pytest.raises(AIProviderError, match="claude.*not answer in time"):
        HeadlessGenerator(adapter).generate(_messages())


def test_a_missing_binary_says_so_by_name():
    adapter = FakeAdapter(exit_code=127, stdout="")

    with pytest.raises(AIProviderError, match="claude.*not installed"):
        HeadlessGenerator(adapter).generate(_messages())


def test_any_other_failure_surfaces_stderr():
    adapter = FakeAdapter(exit_code=1, stdout="", stderr="model overloaded")

    with pytest.raises(AIProviderError, match="model overloaded"):
        HeadlessGenerator(adapter).generate(_messages())


def test_a_quota_exhaustion_failure_says_the_quota_is_spent():
    adapter = FakeAdapter(
        exit_code=1, stdout="", stderr="RESOURCE_EXHAUSTED (code 429): Individual quota reached"
    )

    with pytest.raises(AIProviderError, match="run out of usage quota"):
        HeadlessGenerator(adapter).generate(_messages())


def test_a_silent_failure_still_names_the_exit_code():
    adapter = FakeAdapter(exit_code=3, stdout="", stderr="")

    with pytest.raises(AIProviderError, match="exited with code 3"):
        HeadlessGenerator(adapter).generate(_messages())


def test_prose_with_a_successful_exit_is_returned_unchanged():
    """A CLI can honour a schema and still answer in prose; that is the
    caller's problem to parse, not a transport failure."""
    adapter = FakeAdapter(stdout="Sure! Here is my analysis...", structured=True)

    response = HeadlessGenerator(adapter).generate(_messages(), json_schema=SCHEMA)

    assert response.content == "Sure! Here is my analysis..."


def test_is_available_delegates_to_the_adapter():
    assert HeadlessGenerator(FakeAdapter(available=True)).is_available() is True
    assert HeadlessGenerator(FakeAdapter(available=False)).is_available() is False
