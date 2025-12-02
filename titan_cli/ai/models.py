"""
Data models for AI system
"""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class AIMessage:
    """Message in an AI conversation"""
    role: str  # "system", "user", "assistant"
    content: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for API calls"""
        return {"role": self.role, "content": self.content}


@dataclass
class AIRequest:
    """Request to an AI provider"""
    messages: List[AIMessage]
    max_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class AIResponse:
    """Response from an AI provider"""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "unknown"
