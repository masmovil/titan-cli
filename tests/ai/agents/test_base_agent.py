"""The agent base class: how a declared contract is enforced across one retry."""

import json

import pytest

from titan_cli.ai.agents.base import AgentRequest, BaseAIAgent
from titan_cli.ai.agents.contracts import JsonContract, TextContract
from titan_cli.ai.exceptions import AIResponseParseError
from titan_cli.ai.models import AIResponse


SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
}


class FakeGenerator:
    """Returns each queued answer in turn and records every call it received."""

    def __init__(self, *answers: str):
        self.answers = list(answers)
        self.calls = []

    def generate(self, messages, max_tokens=None, temperature=None, json_schema=None):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "json_schema": json_schema,
            }
        )
        content = self.answers.pop(0) if self.answers else ""
        return AIResponse(content=content, model="fake", usage={"total_tokens": 10})

    def is_available(self) -> bool:
        return True


class Agent(BaseAIAgent):
    def get_system_prompt(self) -> str:
        return "You are a test agent."


def _request(contract, **overrides) -> AgentRequest:
    kwargs = {"context": "do the thing", "contract": contract, "operation": "testing"}
    kwargs.update(overrides)
    return AgentRequest(**kwargs)


def test_a_satisfied_contract_costs_one_call():
    generator = FakeGenerator(json.dumps({"title": "ok"}))
    agent = Agent(generator)

    response = agent.generate(_request(JsonContract(schema=SCHEMA, required=("title",))))

    assert len(generator.calls) == 1
    assert response.parsed == {"title": "ok"}
    assert response.contract_degraded is False


def test_free_prose_never_retries():
    """The cheapest call must stay one subprocess on the CLI path."""
    generator = FakeGenerator("just a commit message")
    agent = Agent(generator)

    response = agent.generate(_request(TextContract()))

    assert len(generator.calls) == 1
    assert response.parsed == "just a commit message"


def test_a_malformed_answer_earns_exactly_one_repair():
    generator = FakeGenerator("sorry, no JSON here", json.dumps({"title": "recovered"}))
    agent = Agent(generator)

    response = agent.generate(_request(JsonContract(schema=SCHEMA, required=("title",))))

    assert len(generator.calls) == 2
    assert response.parsed == {"title": "recovered"}
    assert response.contract_degraded is False


def test_the_repair_call_carries_the_previous_answer():
    generator = FakeGenerator("garbage", json.dumps({"title": "t"}))
    agent = Agent(generator)

    agent.generate(_request(JsonContract(schema=SCHEMA, required=("title",))))

    repair_content = generator.calls[1]["messages"][0].content
    assert "garbage" in repair_content


def test_a_second_failure_raises_when_the_contract_has_no_defaults():
    generator = FakeGenerator("garbage", "still garbage")
    agent = Agent(generator)

    with pytest.raises(AIResponseParseError) as excinfo:
        agent.generate(_request(JsonContract(schema=SCHEMA, required=("title",))))

    assert len(generator.calls) == 2
    assert "testing" in str(excinfo.value)


def test_a_second_failure_degrades_when_the_contract_has_defaults():
    generator = FakeGenerator("garbage", "still garbage")
    agent = Agent(generator)
    contract = JsonContract(
        schema=SCHEMA, required=(), defaults={"title": "Untitled"}
    )

    response = agent.generate(_request(contract))

    assert response.parsed == {"title": "Untitled"}
    assert response.contract_degraded is True


def test_a_schema_honouring_provider_that_answers_prose_still_recovers():
    """A CLI can accept a schema and return prose with a successful exit code."""
    generator = FakeGenerator(
        "Here is my analysis in plain English.",
        json.dumps({"title": "recovered"}),
    )
    agent = Agent(generator)

    response = agent.generate(_request(JsonContract(schema=SCHEMA, required=("title",))))

    assert generator.calls[0]["json_schema"] == SCHEMA
    assert response.parsed == {"title": "recovered"}


def test_the_contract_schema_reaches_the_generator():
    generator = FakeGenerator(json.dumps({"title": "t"}))
    agent = Agent(generator)

    agent.generate(_request(JsonContract(schema=SCHEMA, required=("title",))))

    assert generator.calls[0]["json_schema"] == SCHEMA


def test_a_text_contract_sends_no_schema():
    generator = FakeGenerator("prose")
    agent = Agent(generator)

    agent.generate(_request(TextContract()))

    assert generator.calls[0]["json_schema"] is None


def test_format_instructions_are_appended_to_the_user_message():
    generator = FakeGenerator("TITLE: x\nDESCRIPTION: y")
    agent = Agent(generator)

    agent.generate(_request(TextContract(sections=("TITLE", "DESCRIPTION"))))

    user_message = generator.calls[0]["messages"][-1]
    assert user_message.role == "user"
    assert user_message.content.startswith("do the thing")
    assert "TITLE:" in user_message.content


def test_free_prose_adds_no_format_block():
    generator = FakeGenerator("prose")
    agent = Agent(generator)

    agent.generate(_request(TextContract()))

    assert generator.calls[0]["messages"][-1].content == "do the thing"


def test_tokens_from_both_attempts_are_counted():
    generator = FakeGenerator("garbage", json.dumps({"title": "t"}))
    agent = Agent(generator)

    response = agent.generate(_request(JsonContract(schema=SCHEMA, required=("title",))))

    assert response.tokens_used == 20


def test_a_generator_with_no_usage_reports_zero_tokens():
    """A CLI reports no token counts at all; zero is the honest answer."""

    class NoUsage(FakeGenerator):
        def generate(self, messages, max_tokens=None, temperature=None, json_schema=None):
            super().generate(messages, max_tokens, temperature, json_schema)
            return AIResponse(content="prose", model="cli", usage={})

    agent = Agent(NoUsage("prose"))

    response = agent.generate(_request(TextContract()))

    assert response.tokens_used == 0


def test_a_generator_failure_propagates_without_a_retry():
    class Broken:
        def generate(self, *args, **kwargs):
            raise RuntimeError("cli exploded")

        def is_available(self):
            return True

    agent = Agent(Broken())

    with pytest.raises(RuntimeError):
        agent.generate(_request(TextContract()))


def test_is_available_delegates_to_the_generator():
    assert Agent(FakeGenerator()).is_available() is True
