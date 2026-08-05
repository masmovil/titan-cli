"""
Unified execution façade for AI requests.

`AIExecutor` is the single surface a workflow step needs: it resolves which
provider the user configured for the step's task, runs the prompt through that
provider (remote connection or headless CLI), and returns a result the step
pattern-matches on. Steps do not build resolvers, read preferences, or pick
adapters themselves.

A step passes its own decorated function as `policy=` and the façade reads the
declared policy off it, so a step cannot silently lose its routing declaration
by forgetting to repeat it at the call site.

Nothing is ever silently remapped: a disabled task, an unavailable configured
provider, or a provider that cannot serve a one-shot text call all come back as
an `AIExecutionError` with a distinct `error_code`, never as a quiet fall back
to a different provider.
"""

from typing import Callable, Dict, Optional, Union

from titan_cli.ai.client import AIClient
from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.ai.models import AIMessage
from titan_cli.core.logging import get_logger
from titan_cli.core.models import AIConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.external_cli.adapters import get_headless_adapter

from .availability import AIAvailabilityChecker
from .declaration import get_declared_ai_policy
from .enums import AIProviderType
from .models import (
    AIExecutionError,
    AIExecutionResult,
    AIExecutionSuccess,
    AIRouteDecision,
    AIRoutePolicy,
)
from .resolver import AIRouteNeedsInput, AIRouteResolution, AIRouteResolver

logger = get_logger(__name__)

# Used when a caller provides neither a policy nor a decorated function: try a
# remote connection first, then a headless CLI.
DEFAULT_PREFERRED = [AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS]

CONFIG_HINT = "Configure it in AI Configuration (main menu)."

PolicySource = Union[AIRoutePolicy, Callable, None]


class AIExecutor:
    """
    Resolves and runs a step's AI request against the provider the user chose.

    `ai_config`/`secrets` may be `None`, mirroring how `ctx.ai` can already be
    `None` when AI is not configured at all - resolution then reports that
    nothing is available rather than raising.
    """

    def __init__(self, ai_config: Optional[AIConfig], secrets: Optional[SecretManager]):
        self.ai_config = ai_config
        self.secrets = secrets
        self.availability = AIAvailabilityChecker(ai_config, secrets)
        self.resolver = AIRouteResolver(ai_config, self.availability)
        self._remote_clients: Dict[str, AIClient] = {}

    def resolve(
        self,
        *,
        policy: PolicySource = None,
        task: Optional[str] = None,
        runtime_override: Optional[AIProviderType] = None,
    ) -> AIRouteResolution:
        """
        Resolve which provider should serve this request.

        Steps that own their own execution (e.g. launching an interactive CLI
        session) call this directly instead of `generate_text`.

        Args:
            policy: An `AIRoutePolicy`, or the decorated step function itself
                (its declared policy is read off the function).
            task: Task key. Defaults to the policy's task.
            runtime_override: A provider type chosen for this run only, taking
                precedence over any persisted preference.
        """
        resolved_policy = self._resolve_policy(policy, task)
        return self.resolver.resolve(
            task=resolved_policy.task,
            policy=resolved_policy,
            runtime_override=runtime_override,
        )

    def generate_text(
        self,
        prompt: str,
        *,
        policy: PolicySource = None,
        task: Optional[str] = None,
        runtime_override: Optional[AIProviderType] = None,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        cwd: Optional[str] = None,
        timeout: int = 180,
        json_schema: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> AIExecutionResult[str]:
        """
        Run a one-shot text generation through the resolved provider.

        Returns `AIExecutionSuccess` carrying the generated text, or
        `AIExecutionError` whose `error_code` tells the step what happened:

        - `AI_DISABLED`: the user turned AI off for this task; steps should Skip.
        - `PROVIDER_UNAVAILABLE`: the configured provider is no longer usable.
        - `NO_PROVIDER_AVAILABLE`: nothing is configured or installed at all.
        - `PROVIDER_NOT_CAPABLE`: the configured provider cannot serve a
          one-shot text call (an interactive CLI needs a real session).
        - `EXECUTION_FAILED`: the provider ran and failed.

        Args:
            prompt: The user prompt.
            policy: An `AIRoutePolicy`, or the decorated step function itself.
            task: Task key. Defaults to the policy's task.
            runtime_override: A provider type chosen for this run only.
            system_prompt: Optional system message (remote providers only;
                headless CLIs receive it prepended to the prompt).
            max_tokens: Remote-only generation cap.
            temperature: Remote-only sampling temperature.
            cwd: Working directory for a headless CLI run.
            timeout: Seconds before a headless CLI run is killed.
            json_schema: Optional JSON Schema for adapters that can enforce
                structured output.
            model: Optional model identifier for the chosen provider's CLI.
        """
        resolution = self.resolve(policy=policy, task=task, runtime_override=runtime_override)

        if isinstance(resolution, AIRouteNeedsInput):
            return self._needs_input_error(resolution)

        match resolution.provider:
            case AIProviderType.OFF:
                return AIExecutionError(
                    error_message="AI is turned off for this task.",
                    error_code="AI_DISABLED",
                    log_level="info",
                    decision=resolution,
                )
            case AIProviderType.REMOTE:
                return self._generate_remote(
                    resolution,
                    prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            case AIProviderType.CLI_HEADLESS:
                return self._generate_headless(
                    resolution,
                    prompt,
                    system_prompt=system_prompt,
                    cwd=cwd,
                    timeout=timeout,
                    json_schema=json_schema,
                    model=model,
                )
            case _:
                return AIExecutionError(
                    error_message=(
                        f"'{resolution.provider}' cannot generate text in a single call. "
                        f"Choose a remote connection or a headless CLI for this task. {CONFIG_HINT}"
                    ),
                    error_code="PROVIDER_NOT_CAPABLE",
                    decision=resolution,
                )

    def remote_client(self, decision: AIRouteDecision) -> Optional[AIClient]:
        """
        Return an `AIClient` for a remote decision, cached per connection.

        Steps that hand a client to an agent (rather than generating text
        themselves) use this to honor the connection the user picked. Returns
        `None` if a client cannot be built for it.
        """
        if not self.ai_config or not self.secrets:
            return None

        cache_key = decision.connection_id or "__default__"
        cached = self._remote_clients.get(cache_key)
        if cached is not None:
            return cached

        try:
            client = AIClient(self.ai_config, self.secrets, connection_id=decision.connection_id)
        except AIConfigurationError as e:
            logger.warning(
                "ai_executor_remote_client_unavailable",
                connection_id=decision.connection_id,
                error=str(e),
            )
            return None

        self._remote_clients[cache_key] = client
        return client

    def _resolve_policy(self, policy: PolicySource, task: Optional[str]) -> AIRoutePolicy:
        """
        Normalize the caller's `policy`/`task` into a single policy.

        Accepts a policy object, a decorated step function, or nothing at all.
        An explicit `task` always wins over the policy's own task, so a step
        with one declaration can still route a secondary call elsewhere.
        """
        declared: Optional[AIRoutePolicy] = None
        if isinstance(policy, AIRoutePolicy):
            declared = policy
        elif callable(policy):
            declared = get_declared_ai_policy(policy)

        if declared is None:
            return AIRoutePolicy(task=task or "", preferred=list(DEFAULT_PREFERRED))
        if task and task != declared.task:
            return AIRoutePolicy(task=task, preferred=list(declared.preferred))
        return declared

    def _needs_input_error(self, resolution: AIRouteNeedsInput) -> AIExecutionError:
        """Turn an unresolvable route into an error that says what to fix."""
        if resolution.candidates:
            return AIExecutionError(
                error_message=f"{resolution.reason}. {CONFIG_HINT}",
                error_code="PROVIDER_UNAVAILABLE",
                details={"candidates": [c.identifier for c in resolution.candidates]},
            )
        return AIExecutionError(
            error_message=(
                f"No AI provider is available ({resolution.reason}). "
                f"Add an AI connection or install a supported CLI. {CONFIG_HINT}"
            ),
            error_code="NO_PROVIDER_AVAILABLE",
        )

    def _generate_remote(
        self,
        decision: AIRouteDecision,
        prompt: str,
        *,
        system_prompt: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> AIExecutionResult[str]:
        client = self.remote_client(decision)
        if client is None:
            return AIExecutionError(
                error_message=(
                    f"AI connection '{decision.connection_id or 'default'}' could not be used. "
                    f"{CONFIG_HINT}"
                ),
                error_code="PROVIDER_UNAVAILABLE",
                decision=decision,
            )

        messages = []
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))
        messages.append(AIMessage(role="user", content=prompt))

        try:
            response = client.generate(messages, max_tokens=max_tokens, temperature=temperature)
        except Exception as e:
            logger.error(
                "ai_executor_remote_generate_failed",
                connection_id=client.connection_id,
                error=str(e),
            )
            return AIExecutionError(
                error_message=str(e),
                error_code="EXECUTION_FAILED",
                decision=decision,
                details={"connection_id": client.connection_id},
            )

        return AIExecutionSuccess(decision=decision, data=response.content)

    def _generate_headless(
        self,
        decision: AIRouteDecision,
        prompt: str,
        *,
        system_prompt: Optional[str],
        cwd: Optional[str],
        timeout: int,
        json_schema: Optional[dict],
        model: Optional[str],
    ) -> AIExecutionResult[str]:
        cli = decision.cli
        if not cli:
            available = self.availability.available_headless_clis()
            if not available:
                return AIExecutionError(
                    error_message=f"No headless CLI is installed. {CONFIG_HINT}",
                    error_code="NO_PROVIDER_AVAILABLE",
                    decision=decision,
                )
            cli = available[0].identifier

        try:
            adapter = get_headless_adapter(cli)
        except ValueError as e:
            return AIExecutionError(
                error_message=str(e),
                error_code="PROVIDER_UNAVAILABLE",
                decision=decision,
            )

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        try:
            response = adapter.execute(
                full_prompt,
                cwd=cwd,
                timeout=timeout,
                json_schema=json_schema,
                model=model,
            )
        except Exception as e:
            logger.error("ai_executor_headless_execute_failed", cli=cli, error=str(e))
            return AIExecutionError(
                error_message=str(e),
                error_code="EXECUTION_FAILED",
                decision=decision,
                details={"cli": cli},
            )

        if not response.succeeded:
            return AIExecutionError(
                error_message=(response.stderr or "").strip() or f"'{cli}' exited with code {response.exit_code}",
                error_code="EXECUTION_FAILED",
                decision=decision,
                details={"cli": cli, "exit_code": response.exit_code},
            )

        return AIExecutionSuccess(decision=decision, data=response.stdout)


__all__ = ["AIExecutor", "DEFAULT_PREFERRED"]
