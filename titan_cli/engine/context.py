"""
WorkflowContext - Dependency injection container for workflows.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.ui.views.prompts import PromptsRenderer


@dataclass
class WorkflowContext:
    """
    Context container for workflow execution.
    
    Provides:
    - Dependency injection (clients, services)
    - Shared data storage between steps
    - Access to UI components
    - Access to configuration and secrets
    """

    # Core dependencies
    config: TitanConfig
    secrets: SecretManager

    # UI components
    text: Optional[TextRenderer] = None
    prompts: Optional[PromptsRenderer] = None

    # Service clients (populated by builder)
    ai: Optional[Any] = None      # AIClient

    # Shared data storage between steps
    data: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Set shared data."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get shared data."""
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if key exists in shared data."""
        return key in self.data
