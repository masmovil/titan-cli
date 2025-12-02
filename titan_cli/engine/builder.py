"""
WorkflowContextBuilder - Fluent API for building WorkflowContext.
"""

from typing import Optional
from pathlib import Path

from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.views.prompts import PromptsRenderer
from .context import WorkflowContext


class WorkflowContextBuilder:
    """
    Fluent builder for WorkflowContext.
    
    Example:
        ctx = WorkflowContextBuilder() \
            .with_ui() \
            .with_github() \
            .with_ai() \
            .build()
    """

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize builder.
        
        Args:
            project_path: Optional project path for config/secrets lookup
        """
        self._config = TitanConfig(project_path=project_path)
        self._secrets = SecretManager(project_path=project_path)

        # UI components
        self._text: Optional[TextRenderer] = None
        self._prompts: Optional[PromptsRenderer] = None

        # Service clients
        self._github = None
        self._git = None
        self._jira = None
        self._ai = None

    def with_ui(self) -> "WorkflowContextBuilder":
        """Add UI components (TextRenderer, PromptsRenderer)."""
        self._text = TextRenderer()
        self._prompts = PromptsRenderer(text_renderer=self._text)
        return self

    def with_github(self) -> "WorkflowContextBuilder":
        """Add GitHub client (future implementation)."""
        # TODO: Initialize GitHub client when implemented
        # from titan_cli.plugins.github.client import GitHubClient
        # self._github = GitHubClient(self._config, self._secrets)
        return self

    def with_git(self) -> "WorkflowContextBuilder":
        """Add Git client (future implementation)."""
        # TODO: Initialize Git client when implemented
        return self

    def with_jira(self) -> "WorkflowContextBuilder":
        """Add Jira client (future implementation)."""
        # TODO: Initialize Jira client when implemented
        return self

    def with_ai(self) -> "WorkflowContextBuilder":
        """Add AI client."""
        from titan_cli.ai.client import AIClient
        from titan_cli.ai.exceptions import AIConfigurationError

        try:
            self._ai = AIClient(self._config, self._secrets)
        except AIConfigurationError:
            # AI not configured, skip
            self._ai = None

        return self

    def build(self) -> WorkflowContext:
        """Build the WorkflowContext."""
        return WorkflowContext(
            config=self._config,
            secrets=self._secrets,
            text=self._text,
            prompts=self._prompts,
            github=self._github,
            git=self._git,
            jira=self._jira,
            ai=self._ai,
        )
