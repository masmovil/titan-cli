"""
WorkflowContextBuilder - Fluent API for building WorkflowContext.
"""
from typing import Optional, Any

from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.views.prompts import PromptsRenderer
from .context import WorkflowContext


class WorkflowContextBuilder:
    """
    Fluent builder for WorkflowContext.
    
    Example:
        config = TitanConfig()
        secrets = SecretManager()
        ctx = WorkflowContextBuilder(config, secrets) \\
            .with_ui() \\
            .with_ai() \\
            .build()
    """

    def __init__(self, config: TitanConfig, secrets: SecretManager):
        """
        Initialize builder.
        
        Args:
            config: The TitanConfig instance.
            secrets: The SecretManager instance.
        """
        self._config = config
        self._secrets = secrets

        # UI components
        self._text: Optional[TextRenderer] = None
        self._prompts: Optional[PromptsRenderer] = None

        # Service clients
        self._ai = None

    def with_ui(
        self,
        text: Optional[TextRenderer] = None,
        prompts: Optional[PromptsRenderer] = None
    ) -> "WorkflowContextBuilder":
        """
        Add UI components.
        
        Args:
            text: Optional TextRenderer (auto-created if None)
            prompts: Optional PromptsRenderer (auto-created if None)
        """
        self._text = text or TextRenderer()
        # If prompts are injected but text is not, ensure prompts uses a valid text renderer
        if prompts and not text:
            self._prompts = prompts
            self._prompts.text_renderer = self._text
        else:
            self._prompts = prompts or PromptsRenderer(text_renderer=self._text)
        return self

    def with_ai(self, ai_client: Optional[Any] = None) -> "WorkflowContextBuilder":
        """
        Add AI client.
        
        Args:
            ai_client: Optional AIClient instance (auto-created if None)
        """
        if ai_client:
            # DI puro - usar el cliente inyectado
            self._ai = ai_client
        else:
            # Conveniencia - auto-crear desde config
            try:
                from titan_cli.ai.client import AIClient
                from titan_cli.ai.exceptions import AIConfigurationError

                self._ai = AIClient(self._config, self._secrets)
            except AIConfigurationError:
                self._ai = None
        return self

    def build(self) -> WorkflowContext:
        """Build the WorkflowContext."""
        return WorkflowContext(
            config=self._config,
            secrets=self._secrets,
            text=self._text,
            prompts=self._prompts,
            ai=self._ai,
        )
