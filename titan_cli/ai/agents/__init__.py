# titan_cli/ai/agents/__init__.py
"""AI Agents base classes.

This module provides base classes for building AI agents.
Specific agents live in their respective plugins.
"""

from .base import BaseAIAgent, AgentRequest, AgentResponse, AIGenerator
from .contracts import AgentContract, ContractParse, JsonContract, TextContract

__all__ = [
    "BaseAIAgent",
    "AgentRequest",
    "AgentResponse",
    "AgentContract",
    "AIGenerator",
    "ContractParse",
    "JsonContract",
    "TextContract",
]
