"""
Provider availability detection for the AI execution routing layer.

Determines which providers (remote AI connections, headless CLIs, interactive
CLIs) are technically usable right now, without making or wiring any routing
decisions into workflows.

Mirrors the existing per-domain availability checks rather than reinventing
them: `AIClient.is_available()` for remote connections,
`list_available_headless_clis()` for headless CLIs, and the same
`CLILauncher.is_available()` loop already used by `ai_assistant_step.py` and
`cli_launcher.py` for interactive CLIs.
"""

from dataclasses import dataclass
from typing import List, Optional

from titan_cli.ai.client import AIClient
from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.core.models import AIConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.external_cli.adapters import list_available_headless_clis
from titan_cli.external_cli.configs import CLI_REGISTRY
from titan_cli.external_cli.launcher import CLILauncher

from .enums import AIProviderType


@dataclass
class AIProviderAvailability:
    """A single connection/CLI that is technically usable right now."""

    provider: AIProviderType
    identifier: str
    display_name: str = ""


class AIAvailabilityChecker:
    """
    Detects which providers are currently available for AI execution.

    Cheap, config/installation-only checks — no network calls, no route
    resolution. `ai_config`/`secrets` may be `None`, mirroring how `ctx.ai`
    can already be `None` when AI is not configured at all.
    """

    def __init__(self, ai_config: Optional[AIConfig], secrets: Optional[SecretManager]):
        self.ai_config = ai_config
        self.secrets = secrets
        # Probing is expensive: one network round trip per remote connection and one
        # subprocess per CLI. Callers ask repeatedly - resolving a screenful of tasks asks
        # dozens of times - so each answer is computed once per instance. Instances are
        # short-lived (rebuilt on every config load and every screen refresh), which is what
        # keeps a cached answer from going stale.
        self._cache: dict[str, List[AIProviderAvailability]] = {}

    def available_remote_connections(self) -> List[AIProviderAvailability]:
        """Return configured AI connections whose provider is ready to use."""
        return self._cached("remote", self._probe_remote_connections)

    def _probe_remote_connections(self) -> List[AIProviderAvailability]:
        if not self.ai_config or not self.ai_config.connections or not self.secrets:
            return []

        available = []
        for connection_id in self.ai_config.connections:
            try:
                client = AIClient(self.ai_config, self.secrets, connection_id=connection_id)
                if client.is_available():
                    available.append(
                        AIProviderAvailability(
                            provider=AIProviderType.REMOTE,
                            identifier=connection_id,
                            display_name=connection_id,
                        )
                    )
            except AIConfigurationError:
                continue
        return available

    def available_headless_clis(self) -> List[AIProviderAvailability]:
        """Return CLIs that have a working headless adapter installed."""
        return self._cached("headless", self._probe_headless_clis)

    def _probe_headless_clis(self) -> List[AIProviderAvailability]:
        return [
            AIProviderAvailability(
                provider=AIProviderType.CLI_HEADLESS,
                identifier=str(cli_name),
                display_name=CLI_REGISTRY.get(cli_name, {}).get("display_name", str(cli_name)),
            )
            for cli_name in list_available_headless_clis()
        ]

    def available_interactive_clis(self) -> List[AIProviderAvailability]:
        """Return CLIs registered in CLI_REGISTRY that are installed."""
        return self._cached("interactive", self._probe_interactive_clis)

    def _probe_interactive_clis(self) -> List[AIProviderAvailability]:
        available = []
        for cli_name, config in CLI_REGISTRY.items():
            launcher = CLILauncher(
                cli_name,
                install_instructions=config.get("install_instructions"),
                prompt_flag=config.get("prompt_flag"),
                model_flag=config.get("model_flag"),
            )
            if launcher.is_available():
                available.append(
                    AIProviderAvailability(
                        provider=AIProviderType.CLI_INTERACTIVE,
                        identifier=cli_name,
                        display_name=config.get("display_name", cli_name),
                    )
                )
        return available

    def _cached(self, key: str, probe) -> List[AIProviderAvailability]:
        if key not in self._cache:
            self._cache[key] = probe()
        return self._cache[key]

    def is_provider_available(self, provider: AIProviderType) -> bool:
        """Whether at least one candidate exists for the given provider type."""
        if provider == AIProviderType.REMOTE:
            return bool(self.available_remote_connections())
        if provider == AIProviderType.CLI_HEADLESS:
            return bool(self.available_headless_clis())
        if provider == AIProviderType.CLI_INTERACTIVE:
            return bool(self.available_interactive_clis())
        if provider == AIProviderType.OFF:
            return True
        return False


__all__ = ["AIProviderAvailability", "AIAvailabilityChecker"]
