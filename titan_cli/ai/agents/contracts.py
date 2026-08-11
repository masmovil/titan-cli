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

import copy
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

        # A label only counts when it opens a line. Searching anywhere in the
        # text would let a label that is a substring of another ("TITLE" inside
        # "SUBTITLE:") or that is merely mentioned inside an earlier section's
        # content anchor the slice at the wrong offset, which silently returns
        # corrupted content instead of failing into the repair retry.
        found = []
        occupied = {}
        for label in self.sections:
            pattern = re.compile(rf"^[ \t]*{re.escape(label)}[ \t]*:", re.MULTILINE | re.IGNORECASE)
            match = pattern.search(text)
            if match is None:
                return ContractParse(ok=False, error=f"missing section '{label}:'")

            clash = occupied.get(match.start())
            if clash is not None:
                return ContractParse(
                    ok=False,
                    error=f"sections '{clash}:' and '{label}:' matched the same heading",
                )
            occupied[match.start()] = label
            found.append((match.start(), match.end(), label))

        # Slice between labels in the order they actually appear, not the order
        # they were declared - a model that reorders them is still answerable.
        found.sort()
        result = {}
        for position, (_, header_end, label) in enumerate(found):
            end = found[position + 1][0] if position + 1 < len(found) else len(text)
            result[self.keys.get(label, label.lower())] = text[header_end:end].strip()

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

    def __post_init__(self) -> None:
        # Validation only walks `schema["properties"]`, so a required name that
        # is not declared there would silently never be enforced. Fail here,
        # where the broken contract is defined, instead of letting it pass.
        undeclared = [
            name for name in self.required
            if name not in self.schema.get("properties", {})
        ]
        if undeclared:
            raise ValueError(
                "required fields not declared in schema properties: "
                + ", ".join(undeclared)
            )

    def json_schema(self) -> Optional[dict]:
        return self.schema

    def degraded_value(self) -> Optional[Any]:
        # Contracts are long-lived (often module-level singletons); handing out
        # the defaults themselves would let a caller that mutates its degraded
        # answer corrupt every later call using this contract.
        return copy.deepcopy(self.defaults)

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
        markdown fences. Every fenced block is a candidate (the first fence may
        be code, not the answer), with the full text as the final fallback for
        unfenced replies. The first candidate holding a parseable object wins;
        if none parses, the first brace match is returned so the caller reports
        the JSON error instead of "no object found". Greedy on the braces on
        purpose: it takes the outermost pair, so a body containing its own JSON
        snippet does not truncate the answer.
        """
        candidates = [fence.group(1) for fence in _FENCED_BLOCK.finditer(text)]
        candidates.append(text)

        fallback = None
        for candidate in candidates:
            match = _OUTERMOST_OBJECT.search(candidate)
            if not match:
                continue
            payload = match.group(0)
            try:
                json.loads(payload)
            except json.JSONDecodeError:
                if fallback is None:
                    fallback = payload
                continue
            return payload

        return fallback

    def _validate(self, data: dict) -> ContractParse:
        properties = self.schema.get("properties", {})
        result = {}

        for name, spec in properties.items():
            if name not in data:
                if name in self.required:
                    return ContractParse(ok=False, error=f"missing required field '{name}'")
                result[name] = self._default_for(name)
                continue

            value = data[name]
            if not self._matches(value, spec):
                if name in self.required:
                    return ContractParse(
                        ok=False,
                        error=f"field '{name}' has the wrong type: got {type(value).__name__}",
                    )
                result[name] = self._default_for(name)
                continue

            result[name] = value

        return ContractParse(ok=True, data=result)

    def _default_for(self, name: str) -> Any:
        # Defaults are mutable (lists, dicts) and shared by every parse of this
        # contract, so each result gets its own copy.
        return copy.deepcopy((self.defaults or {}).get(name))

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
