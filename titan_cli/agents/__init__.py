"""
Titan CLI Agents

AI-powered autonomous agents with dual mode support:
- Interactive Mode: AI executes tools autonomously (TAP)
- Analysis Mode: AI analyzes data as workflow steps

Available Agents:
- PlatformAgent: Dual mode agent (interactive + analysis)

Available Workflow Steps:
- See titan_cli.agents.steps for workflow step wrappers
"""

from .platform_agent import PlatformAgent

__all__ = [
    'PlatformAgent',
]
