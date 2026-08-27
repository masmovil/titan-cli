"""
Base protocol and models for headless CLI adapters.

Each CLI (Claude, Gemini, etc.) implements HeadlessCliAdapter
to abstract away CLI-specific flags and output parsing.
Titan interacts only with this generic interface.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Optional
from typing import Protocol, runtime_checkable


class SupportedCLI(StrEnum):
    """
    Enum of CLIs with a registered headless adapter.

    Values match the CLI command name and the keys in configs.CLI_REGISTRY,
    so string literals like "claude" remain compatible.
    """
    CLAUDE = "claude"
    GEMINI = "gemini"
    CODEX = "codex"


@dataclass
class HeadlessResponse:
    """Result of a headless CLI execution."""
    stdout: str
    stderr: str
    exit_code: int

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@runtime_checkable
class HeadlessCliAdapter(Protocol):
    """
    Generic interface for running a CLI tool in headless (non-interactive) mode.

    Each CLI has a concrete adapter that knows:
    - Which flags to use for non-interactive execution
    - How to sanitize/parse the output
    - How to handle CLI-specific quirks

    Analogous to AIProvider in the AI layer.
    """

    @property
    def cli_name(self) -> SupportedCLI:
        """The CLI identifier."""
        ...

    @property
    def supports_structured_output(self) -> bool:
        """Whether this adapter can enforce a JSON Schema on the CLI's own response,
        instead of relying on prompt instructions the model may not follow."""
        ...

    @property
    def supports_tool_restriction(self) -> bool:
        """Whether this adapter can enforce a tool denylist on the CLI's own session,
        instead of relying on prompt instructions the model may not follow."""
        ...

    @property
    def supports_effort_control(self) -> bool:
        """Whether this adapter can set a reasoning-effort tier for the CLI's own session."""
        ...

    @property
    def supports_model_selection(self) -> bool:
        """Whether this adapter can select a specific model for the CLI's own session."""
        ...

    def is_available(self) -> bool:
        """Return True if the CLI is installed and reachable."""
        ...

    def execute(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        json_schema: Optional[dict[str, Any]] = None,
        disallowed_tools: Optional[list[str]] = None,
        effort: Optional[str] = None,
        model: Optional[str] = None,
    ) -> HeadlessResponse:
        """
        Run the CLI with the given prompt in headless mode.

        Args:
            prompt: The prompt to send to the CLI.
            cwd: Working directory for the subprocess.
            timeout: Seconds before the subprocess is killed.
            json_schema: Optional JSON Schema (top-level type "object") to enforce on the
                response. Ignored by adapters where `supports_structured_output` is False.
            disallowed_tools: Optional list of built-in tool names to remove from the CLI's
                session entirely (e.g. ["Bash", "Agent"]). Ignored by adapters where
                `supports_tool_restriction` is False.
            effort: Optional reasoning-effort tier (e.g. "low", "medium", "high"). Ignored by
                adapters where `supports_effort_control` is False.
            model: Optional model identifier to run the CLI with (e.g. "claude-opus-4-8").
                Ignored by adapters where `supports_model_selection` is False.

        Returns:
            HeadlessResponse with stdout, stderr, and exit_code. When `json_schema` is
            honored, stdout is the schema-validated JSON, with no surrounding prose.
        """
        ...
