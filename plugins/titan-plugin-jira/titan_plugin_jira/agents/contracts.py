# plugins/titan-plugin-jira/titan_plugin_jira/agents/contracts.py
"""
Response contracts for the Jira agent's calls.

The agent asks five different questions about an issue and each expects a
different answer, so each declares its own contract next to the prompt that
produces it.

Every contract here carries defaults. Issue analysis is additive - a missing
risk list is a thinner report, not a failed run - so a call that cannot be
parsed twice degrades to an empty answer instead of sinking the analysis.
"""

from titan_cli.ai.agents.contracts import JsonContract, TextContract

_STRING_LIST = {"type": "array", "items": {"type": "string"}}


REQUIREMENTS_CONTRACT = JsonContract(
    schema={
        "type": "object",
        "properties": {
            "functional": _STRING_LIST,
            "non_functional": _STRING_LIST,
            "acceptance_criteria": _STRING_LIST,
            "technical_approach": {"type": ["string", "null"]},
        },
    },
    defaults={
        "functional": [],
        "non_functional": [],
        "acceptance_criteria": [],
        "technical_approach": None,
    },
)


RISK_CONTRACT = JsonContract(
    schema={
        "type": "object",
        "properties": {
            "risks": _STRING_LIST,
            "edge_cases": _STRING_LIST,
            "complexity": {"type": ["string", "null"]},
            "effort": {"type": ["string", "null"]},
        },
    },
    defaults={"risks": [], "edge_cases": [], "complexity": None, "effort": None},
)


DEPENDENCY_CONTRACT = JsonContract(
    schema={
        "type": "object",
        "properties": {"dependencies": _STRING_LIST},
    },
    defaults={"dependencies": []},
)


SUBTASK_CONTRACT = JsonContract(
    schema={
        "type": "object",
        "properties": {
            "subtasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["summary"],
                },
            }
        },
    },
    defaults={"subtasks": []},
)


# A comment is prose written for a human to read, so there is nothing to parse.
COMMENT_CONTRACT = TextContract()


__all__ = [
    "COMMENT_CONTRACT",
    "DEPENDENCY_CONTRACT",
    "REQUIREMENTS_CONTRACT",
    "RISK_CONTRACT",
    "SUBTASK_CONTRACT",
]
