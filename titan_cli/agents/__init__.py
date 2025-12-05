"""
Titan CLI Agents

AI-powered autonomous agents using TAP (Tool Anything Protocol).

Available Agents:
- PlatformAgent: TAP + TOML configuration (platform engineering workflows)
- AutoCommitAgent: TAP + Cascade (production, token-optimized)
- AutoCommitLangGraphAgent: TAP + LangGraph (complex workflows)
"""

from .platform_agent import PlatformAgent

__all__ = [
    'PlatformAgent',
]
