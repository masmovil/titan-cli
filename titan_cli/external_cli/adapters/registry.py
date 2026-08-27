"""
Registry of available headless CLI adapters.

To add a new CLI:
1. Create a new adapter class implementing HeadlessCliAdapter in its own module.
2. Add a new value to SupportedCLI in base.py.
3. Register the adapter below.

Analogous to the AI source registries in titan_cli/ai/client.py.
"""

from typing import Dict, Type, Union

from .base import HeadlessCliAdapter, SupportedCLI
from .claude import ClaudeHeadlessAdapter
from .gemini import GeminiHeadlessAdapter
from .codex import CodexHeadlessAdapter

HEADLESS_ADAPTER_REGISTRY: Dict[SupportedCLI, Type] = {
    SupportedCLI.CLAUDE: ClaudeHeadlessAdapter,
    SupportedCLI.GEMINI: GeminiHeadlessAdapter,
    SupportedCLI.CODEX: CodexHeadlessAdapter,
}


def get_headless_adapter(cli_name: Union[SupportedCLI, str]) -> HeadlessCliAdapter:
    """
    Return a concrete HeadlessCliAdapter for the given CLI name.

    Accepts both SupportedCLI enum values and plain strings (e.g. "claude"),
    since SupportedCLI inherits from str.

    Args:
        cli_name: CLI identifier — a SupportedCLI value or equivalent string.

    Raises:
        ValueError: If no adapter is registered for cli_name.
    """
    adapter_class = HEADLESS_ADAPTER_REGISTRY.get(cli_name)  # type: ignore[arg-type]
    if adapter_class is None:
        available = ", ".join(HEADLESS_ADAPTER_REGISTRY.keys())
        raise ValueError(
            f"No headless adapter registered for '{cli_name}'. "
            f"Available: {available}"
        )
    return adapter_class()


def list_available_headless_clis() -> list[SupportedCLI]:
    """
    Return the registered CLIs that currently have an available headless adapter,
    in registry order.
    """
    return [
        cli_name
        for cli_name in HEADLESS_ADAPTER_REGISTRY
        if get_headless_adapter(cli_name).is_available()
    ]
