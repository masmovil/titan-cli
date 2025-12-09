"""
Titan CLI Agent Workflow Steps

Steps that integrate AI agents into workflows for analysis and decision-making.

Available Steps:
- ai_analyze_changes_step: Generic AI analysis (simple)
- ai_suggest_commit_message_step: Generic AI commit suggestion (simple)
- platform_agent_analysis_step: PlatformAgent analysis (TOML-configured)
- platform_agent_suggest_commit_step: PlatformAgent commit suggestion (TOML-configured)
"""

from .analysis_step import (
    ai_analyze_changes_step,
    ai_suggest_commit_message_step,
)

from .platform_agent_step import (
    platform_agent_analysis_step,
    platform_agent_suggest_commit_step,
    create_platform_agent_step,
)

__all__ = [
    # Generic AI steps (simple, hardcoded prompts)
    "ai_analyze_changes_step",
    "ai_suggest_commit_message_step",
    # Platform Agent steps (TOML-configured, more powerful)
    "platform_agent_analysis_step",
    "platform_agent_suggest_commit_step",
    "create_platform_agent_step",
]
