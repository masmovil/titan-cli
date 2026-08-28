# titan_cli/ai/headless_generator.py
"""
Generation backed by a local CLI running headlessly.

`AIClient` generates by calling a remote connection; this generates by running
an installed CLI as a subprocess. Both satisfy the same `AIGenerator` protocol,
which is what lets one agent run against either without knowing the difference.

It lives beside `AIClient` rather than under `agents/` on purpose: an agent must
never import a transport, and a transport sitting inside `agents/` would be an
invitation to.
"""

import time
from typing import List, Optional, Sequence

from titan_cli.ai.exceptions import AIProviderError
from titan_cli.ai.models import AIMessage, AIResponse
from titan_cli.core.interrupt import run_interruptible
from titan_cli.core.logging.config import get_logger
from titan_cli.external_cli.adapters.base import HeadlessCliAdapter

logger = get_logger(__name__)

AGENT_HEADLESS_TIMEOUT_SECONDS = 180
"""Seconds allowed for a single agent call, not for a whole agent run.

An agent that makes five calls can therefore take five times this long. The
value is named rather than inlined because the right number is a measurement
nobody has taken yet.
"""

AGENT_DISALLOWED_TOOLS = ("Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent")
"""Tools removed from the CLI's session while it answers an agent.

Nobody is watching this run, so it must not modify files, reach the network, or
spawn a sub-agent. `Read`/`Grep`/`Glob` stay: they are the reason a CLI is worth
choosing at all, since they let the model check the real code instead of relying
solely on what the prompt could afford to include.
"""

# Exit codes the adapters use for the two failures worth naming precisely.
_EXIT_TIMEOUT = 124
_EXIT_NOT_INSTALLED = 127


class HeadlessGenerator:
    """
    Runs an agent's calls through a headless CLI, one subprocess per call.

    Implements `AIGenerator`, so the agent above it cannot tell which transport
    it is on - which is the point: an agent is written once, and the user picks
    where it runs.
    """

    def __init__(
        self,
        adapter: HeadlessCliAdapter,
        *,
        cwd: Optional[str] = None,
        timeout: int = AGENT_HEADLESS_TIMEOUT_SECONDS,
        model: Optional[str] = None,
        disallowed_tools: Sequence[str] = AGENT_DISALLOWED_TOOLS,
    ) -> None:
        """
        Args:
            adapter: The CLI to run.
            cwd: Directory the CLI runs in. Pointing it at the repository is
                what lets the model read the code being discussed.
            timeout: Seconds for each call.
            model: Optional model override for CLIs that accept one.
            disallowed_tools: Tools withheld from the CLI's session.
        """
        self.adapter = adapter
        self.cwd = cwd
        self.timeout = timeout
        self.model = model
        self.disallowed_tools = list(disallowed_tools)

    def generate(
        self,
        messages: List[AIMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> AIResponse:
        """
        Run one prompt through the CLI and return what it printed.

        `max_tokens` and `temperature` are accepted and ignored: a CLI exposes
        no such knobs. What bounds the answer here is the caller's contract, not
        a token cap.

        A schema is forwarded only to CLIs that can enforce one. The rest get
        the prompt alone - and even the ones that can enforce it may answer in
        prose anyway, so the caller still has to check what came back.

        Raises:
            AIProviderError: the CLI timed out, is not installed, or failed.
        """
        cli = self.adapter.cli_name.value
        prompt = self._flatten(messages)

        started = time.monotonic()
        # The subprocess blocks for up to `self.timeout` seconds with no way to poll
        # for app exit; run it interruptibly so quitting the TUI mid-call aborts the
        # workflow thread instead of hanging interpreter shutdown.
        response = run_interruptible(
            lambda: self.adapter.execute(
                prompt,
                cwd=self.cwd,
                timeout=self.timeout,
                json_schema=json_schema if self.adapter.supports_structured_output else None,
                disallowed_tools=(
                    self.disallowed_tools if self.adapter.supports_tool_restriction else None
                ),
                model=self.model,
            )
        )
        duration = round(time.monotonic() - started, 3)

        if not response.succeeded:
            logger.error(
                "ai_agent_cli_failed",
                cli=cli,
                exit_code=response.exit_code,
                duration=duration,
            )
            raise AIProviderError(self._failure_message(cli, response))

        logger.info(
            "ai_agent_cli_ok",
            cli=cli,
            duration=duration,
            response_chars=len(response.stdout or ""),
            schema_sent=bool(json_schema) and self.adapter.supports_structured_output,
        )

        return AIResponse(
            content=response.stdout,
            model=self.model or cli,
            # A CLI reports no token accounting, and inventing one would put a
            # made-up number in front of the user.
            usage={},
            finish_reason="stop",
        )

    def is_available(self) -> bool:
        """Whether the CLI is installed and usable."""
        return self.adapter.is_available()

    @staticmethod
    def _flatten(messages: List[AIMessage]) -> str:
        """
        Collapse a conversation into the single prompt a CLI accepts.

        A CLI takes one string, so the system message becomes a preamble. Order
        is preserved, which keeps the contract's format block last - where the
        agent put it, and where it carries the most weight.
        """
        return "\n\n".join(message.content for message in messages if message.content)

    @staticmethod
    def _failure_message(cli: str, response) -> str:
        if response.exit_code == _EXIT_TIMEOUT:
            return f"'{cli}' did not answer in time"
        if response.exit_code == _EXIT_NOT_INSTALLED:
            return f"'{cli}' is not installed"
        detail = (response.stderr or "").strip() or f"'{cli}' exited with code {response.exit_code}"
        if response.quota_exhausted:
            return (
                f"'{cli}' has run out of usage quota. Wait for it to reset or "
                f"route this task to another provider. Detail: {detail}"
            )
        return detail


__all__ = [
    "AGENT_DISALLOWED_TOOLS",
    "AGENT_HEADLESS_TIMEOUT_SECONDS",
    "HeadlessGenerator",
]
