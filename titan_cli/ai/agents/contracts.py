# titan_cli/ai/agents/contracts.py
"""
Response contracts for AI agent calls.

A contract states the shape of answer one call needs and how to recover that
shape from whatever the model actually returned. It travels on the request
rather than on the agent class, because a single agent can make several calls
that each want a different answer.

The same contract runs on every transport. A provider able to enforce a JSON
schema natively is given one, but honoring it is an optimization and never a
guarantee - a CLI can return prose with a successful exit code - so parsing and
validation always run, schema or no schema.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

# JSON Schema type names mapped to what `isinstance` understands. A schema may
# declare a list of types (["string", "null"]) for a nullable field, which is
# why validation checks membership rather than a single type.
_JSON_TYPES: Mapping[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}

_FENCED_BLOCK = re.compile(r"```(?:json)?\s*\n(.+?)\n```", re.DOTALL)
_OUTERMOST_OBJECT = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class ContractParse:
    """
    Outcome of checking one response against a contract.

    Deliberately not a `ClientResult`/`AIExecutionResult`: this never leaves the
    agent layer, and a third success/error pair at module scope would read like
    another routing result.
    """

    ok: bool
    data: Any = None
    error: str = ""


class AgentContract(ABC):
    """Base class for the answer shape an agent call declares."""

    @abstractmethod
    def format_instructions(self) -> str:
        """
        The block appended to the prompt telling the model what to emit.

        Returning an empty string means the prompt says nothing about format,
        which is the honest answer for free prose.
        """

    @abstractmethod
    def parse(self, text: str) -> ContractParse:
        """Recover the declared shape from a raw model response."""

    def json_schema(self) -> Optional[dict]:
        """
        Schema for providers that can enforce one, or None when there is
        nothing enforceable.

        A provider is free to ignore this and answer in prose anyway, so a
        caller must still run `parse` on the result.
        """
        return None

    def degraded_value(self) -> Optional[Any]:
        """
        What this call is worth when parsing fails for good.

        `None` means the failure is fatal and should raise. Anything else means
        the call degrades to that value rather than sinking the whole run.
        """
        return None

    def repair_prompt(self, previous: str) -> str:
        """A follow-up asking the model to reshape its own previous answer."""
        return (
            "Your previous response did not follow the required format.\n\n"
            f"{self.format_instructions()}\n\n"
            "Rewrite the following content in that exact format. Keep the same "
            "information - change only the shape, and output nothing else.\n\n"
            f"{previous}"
        )


@dataclass(frozen=True)
class TextContract(AgentContract):
    """
    A plain-text answer, optionally split into labelled sections.

    With no sections this is free prose: it always parses, so a call using it
    never spends a retry. That is the right declaration when the answer *is*
    prose - a commit message, a comment - and not an escape hatch. Prose behaves
    identically on every transport.

    With sections, `parse` returns a mapping and a missing section is a failure,
    which is what earns the repair retry.
    """

    sections: tuple[str, ...] = ()
    keys: Mapping[str, str] = field(default_factory=dict)

    def format_instructions(self) -> str:
        if not self.sections:
            return ""
        blocks = "\n\n".join(f"{label}:\n<content>" for label in self.sections)
        return (
            "Respond using exactly these labelled sections and nothing else:\n\n"
            f"{blocks}"
        )

    def parse(self, text: str) -> ContractParse:
        if not self.sections:
            return ContractParse(ok=True, data=text.strip())

        upper = text.upper()
        found = []
        for label in self.sections:
            index = upper.find(f"{label.upper()}:")
            if index == -1:
                return ContractParse(ok=False, error=f"missing section '{label}:'")
            found.append((index, label))

        # Slice between labels in the order they actually appear, not the order
        # they were declared - a model that reorders them is still answerable.
        found.sort()
        result = {}
        for position, (index, label) in enumerate(found):
            start = index + len(label) + 1
            end = found[position + 1][0] if position + 1 < len(found) else len(text)
            result[self.keys.get(label, label.lower())] = text[start:end].strip()

        return ContractParse(ok=True, data=result)


@dataclass(frozen=True)
class JsonContract(AgentContract):
    """
    A JSON object answer.

    `fallback` is tried when JSON parsing fails and before any retry, which is
    where a legacy labelled-text format lives. `defaults` decides what a final
    failure costs: with them the call degrades to a usable empty answer, without
    them it raises.

    The schema must be an object at the root - the structured-output tooling
    that enforces it requires one - so an array answer belongs under a key.
    """

    schema: dict
    required: tuple[str, ...] = ()
    defaults: Optional[dict] = None
    fallback: Optional[AgentContract] = None

    def json_schema(self) -> Optional[dict]:
        return self.schema

    def degraded_value(self) -> Optional[Any]:
        return self.defaults

    def format_instructions(self) -> str:
        return (
            "Respond with a single JSON object and nothing else - no prose "
            "before or after it, matching this schema:\n\n"
            f"{json.dumps(self.schema, indent=2)}"
        )

    def parse(self, text: str) -> ContractParse:
        payload = self._extract_object(text)
        if payload is None:
            return self._fall_back(text, "no JSON object found in the response")

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as error:
            return self._fall_back(text, f"invalid JSON: {error}")

        if not isinstance(data, dict):
            return self._fall_back(text, f"expected a JSON object, got {type(data).__name__}")

        return self._validate(data)

    @staticmethod
    def _extract_object(text: str) -> Optional[str]:
        """
        Pull the JSON object out of a response that may be wrapped in prose or
        markdown fences. Greedy on purpose: it takes the outermost braces, so a
        body containing its own JSON snippet does not truncate the answer.
        """
        fenced = _FENCED_BLOCK.search(text)
        candidate = fenced.group(1) if fenced else text

        match = _OUTERMOST_OBJECT.search(candidate)
        return match.group(0) if match else None

    def _validate(self, data: dict) -> ContractParse:
        properties = self.schema.get("properties", {})
        result = {}

        for name, spec in properties.items():
            if name not in data:
                if name in self.required:
                    return ContractParse(ok=False, error=f"missing required field '{name}'")
                result[name] = (self.defaults or {}).get(name)
                continue

            value = data[name]
            if not self._matches(value, spec):
                if name in self.required:
                    return ContractParse(
                        ok=False,
                        error=f"field '{name}' has the wrong type: got {type(value).__name__}",
                    )
                result[name] = (self.defaults or {}).get(name)
                continue

            result[name] = value

        return ContractParse(ok=True, data=result)

    @staticmethod
    def _matches(value: Any, spec: Any) -> bool:
        """Whether a value satisfies a schema field's declared type(s)."""
        if not isinstance(spec, dict):
            return True

        declared = spec.get("type")
        if declared is None:
            return True

        for name in declared if isinstance(declared, list) else [declared]:
            expected = _JSON_TYPES.get(name)
            if expected is None:
                # An unmapped type means the schema is richer than this check
                # understands; letting the value through beats rejecting it.
                return True
            # `bool` is a subclass of `int`, so an unguarded isinstance would
            # accept True for an integer field.
            if name in ("integer", "number") and isinstance(value, bool):
                continue
            if isinstance(value, expected):
                return True

        return False

    def _fall_back(self, text: str, reason: str) -> ContractParse:
        if self.fallback is None:
            return ContractParse(ok=False, error=reason)

        recovered = self.fallback.parse(text)
        if recovered.ok:
            return recovered

        return ContractParse(ok=False, error=f"{reason}; fallback also failed: {recovered.error}")


__all__ = [
    "AgentContract",
    "ContractParse",
    "JsonContract",
    "TextContract",
]
