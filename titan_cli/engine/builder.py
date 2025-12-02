"""
WorkflowContextBuilder - Fluent API for building WorkflowContext.
"""
from typing import Optional, Any

from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from .context import WorkflowContext
from .ui_container import UIComponents
from .views_container import UIViews


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

        # UI containers
        self._ui: Optional[UIComponents] = None
        self._views: Optional[UIViews] = None

        # Service clients
        self._ai = None

    def with_ui(
        self,
        ui: Optional[UIComponents] = None,
        views: Optional[UIViews] = None
    ) -> "WorkflowContextBuilder":
        """
        Add UI components and views.
        
        Args:
            ui: Optional UIComponents (auto-created if None)
            views: Optional UIViews (auto-created if None)
        
        Returns:
            Builder instance
        """
        # Create or inject UIComponents
        self._ui = ui or UIComponents.create()

        # Create or inject UIViews
        self._views = views or UIViews.create(self._ui)

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
            ui=self._ui,
            views=self._views,
            ai=self._ai,
        )
