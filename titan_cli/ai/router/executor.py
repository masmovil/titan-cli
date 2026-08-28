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

import time
from typing import Any, Callable, Dict, Optional, Union

from titan_cli.ai.client import AIClient
from titan_cli.ai.exceptions import AIConfigurationError
from titan_cli.ai.headless_generator import AGENT_HEADLESS_TIMEOUT_SECONDS, HeadlessGenerator
from titan_cli.ai.models import AIMessage
from titan_cli.core.interrupt import run_interruptible
from titan_cli.core.logging import get_logger
from titan_cli.core.models import AIConfig
from titan_cli.core.security import SecretBroker
from titan_cli.external_cli.adapters import get_headless_adapter

from .availability import AIAvailabilityChecker
from .declaration import get_declared_ai_policy
from .enums import AIProviderType, provider_label
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

# A step can hand in a sink for one line of user-facing text (typically `ctx.textual.dim_text`).
# Kept as a plain callable so this policy layer stays free of any UI type.
Announce = Optional[Callable[[str], None]]


def route_summary(decision: AIRouteDecision) -> str:
    """
    One line naming who is about to run this task.

    Worth showing even though the same fact is logged: a user watching a workflow should not
    have to grep a file to find out which AI just answered, and noticing the wrong one there
    is what prompts them to change it.

    The instance comes first because it is the part that identifies the answer ("claude", the
    connection's name); the kind of provider qualifies it.
    """
    if decision.provider == AIProviderType.OFF:
        return "AI is off for this task"
    instance = decision.cli or decision.connection_id
    label = provider_label(decision.provider)
    return f"{instance} · {label}" if instance else label


class AIExecutor:
    """
    Resolves and runs a step's AI request against the provider the user chose.

    `ai_config`/`provider_factory`/`secret_broker` may be `None`, mirroring
    how `ctx.ai` can already be `None` when AI is not configured at all -
    resolution then reports that nothing is available rather than raising.
    """

    def __init__(
        self,
        ai_config: Optional[AIConfig],
        provider_factory: Optional[Callable] = None,
        secret_broker: Optional[SecretBroker] = None,
    ):
        """
        Args:
            ai_config: The AI configuration, or None when AI is unconfigured.
            provider_factory: Builds authenticated providers for remote
                clients — normally `titan_cli.core.security.create_ai_provider`.
            secret_broker: Core-scoped broker the availability checker uses
                to test key existence without ever reading a value.
        """
        self.ai_config = ai_config
        self.provider_factory = provider_factory
        self.availability = AIAvailabilityChecker(ai_config, secret_broker)
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
        resolution = self.resolver.resolve(
            task=resolved_policy.task,
            policy=resolved_policy,
            runtime_override=runtime_override,
        )

        if isinstance(resolution, AIRouteNeedsInput):
            logger.info(
                "ai_route_unresolved",
                task=resolved_policy.task,
                reason=resolution.reason,
                candidates=[c.identifier for c in resolution.candidates],
            )
        else:
            logger.info(
                "ai_route_resolved",
                task=resolved_policy.task,
                provider=str(resolution.provider),
                identifier=resolution.cli or resolution.connection_id,
                reason=resolution.reason,
            )

        return resolution

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
        announce: Announce = None,
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
        - `QUOTA_EXHAUSTED`: the provider ran but its usage quota is spent;
          retrying the same provider is pointless until the quota resets.
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
            announce: Optional sink for one line of user-facing text naming the
                provider that will run this, e.g. `ctx.textual.dim_text`.
        """
        resolution = self.resolve(policy=policy, task=task, runtime_override=runtime_override)

        if isinstance(resolution, AIRouteNeedsInput):
            return self._needs_input_error(resolution)

        self._announce(announce, resolution)

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

    def resolve_generator(
        self,
        *,
        policy: PolicySource = None,
        task: Optional[str] = None,
        runtime_override: Optional[AIProviderType] = None,
        announce: Announce = None,
        cwd: Optional[str] = None,
        timeout: int = AGENT_HEADLESS_TIMEOUT_SECONDS,
        model: Optional[str] = None,
    ) -> AIExecutionResult[Any]:
        """
        Resolve something an agent can generate with, honoring the user's choice.

        Agents make several calls of their own, so they need a generator rather
        than a single generated string. Both a remote connection and an
        automatic CLI can serve one, and which arrives here is the user's
        setting - the agent above cannot tell the difference.

        Error codes match `generate_text`: `AI_DISABLED` when the task is off,
        `PROVIDER_NOT_CAPABLE` for a provider that cannot run unattended, and
        `PROVIDER_UNAVAILABLE`/`NO_PROVIDER_AVAILABLE` when the choice cannot
        be honored.

        Args:
            cwd: Directory a CLI runs in. Pointing it at the repository is what
                lets the model read the code being discussed.
            timeout: Seconds per call for a CLI.
            model: Optional model override for a CLI that accepts one.
        """
        resolution = self.resolve(policy=policy, task=task, runtime_override=runtime_override)

        if isinstance(resolution, AIRouteNeedsInput):
            return self._needs_input_error(resolution)

        self._announce(announce, resolution)

        match resolution.provider:
            case AIProviderType.OFF:
                return AIExecutionError(
                    error_message="AI is turned off for this task.",
                    error_code="AI_DISABLED",
                    log_level="info",
                    decision=resolution,
                )
            case AIProviderType.REMOTE:
                return self._remote_generator(resolution)
            case AIProviderType.CLI_HEADLESS:
                return self._headless_generator(resolution, cwd=cwd, timeout=timeout, model=model)
            case _:
                return AIExecutionError(
                    error_message=(
                        f"'{resolution.provider}' cannot run an agent's calls unattended. "
                        f"Choose a remote connection or an automatic CLI for this task. "
                        f"{CONFIG_HINT}"
                    ),
                    error_code="PROVIDER_NOT_CAPABLE",
                    decision=resolution,
                )

    def _remote_generator(self, decision: AIRouteDecision) -> AIExecutionResult[Any]:
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

        return AIExecutionSuccess(decision=decision, data=client)

    def _headless_generator(
        self,
        decision: AIRouteDecision,
        *,
        cwd: Optional[str],
        timeout: int,
        model: Optional[str],
    ) -> AIExecutionResult[Any]:
        cli = decision.cli
        if not cli:
            return AIExecutionError(
                error_message=f"No CLI was resolved for this request. {CONFIG_HINT}",
                error_code="NO_PROVIDER_AVAILABLE",
                decision=decision,
            )

        try:
            adapter = get_headless_adapter(cli)
        except ValueError as e:
            return AIExecutionError(
                error_message=str(e),
                error_code="PROVIDER_UNAVAILABLE",
                decision=decision,
            )

        # An agent run costs a subprocess per call, so a missing binary is worth
        # catching now rather than as an exit code after the first minute.
        if not adapter.is_available():
            return AIExecutionError(
                error_message=f"'{cli}' is not installed. {CONFIG_HINT}",
                error_code="PROVIDER_UNAVAILABLE",
                decision=decision,
            )

        return AIExecutionSuccess(
            decision=decision,
            data=HeadlessGenerator(adapter, cwd=cwd, timeout=timeout, model=model),
        )

    def remote_client(self, decision: AIRouteDecision) -> Optional[AIClient]:
        """
        Return an `AIClient` for a remote decision, cached per connection.

        Steps that hand a client to an agent (rather than generating text
        themselves) use this to honor the connection the user picked. Returns
        `None` if a client cannot be built for it.
        """
        if not self.ai_config or not self.provider_factory:
            return None

        cache_key = decision.connection_id or "__default__"
        cached = self._remote_clients.get(cache_key)
        if cached is not None:
            return cached

        try:
            client = AIClient(
                self.ai_config, self.provider_factory, connection_id=decision.connection_id
            )
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

        A function passed as `policy=` that carries no declaration is a broken
        contract, not a default: it would route under the empty task key that
        every such call shares, with no `executes` set to guard it. It is
        refused unless the caller names a `task` itself, and even then the
        missing declaration is logged.

        Raises:
            ValueError: If `policy` is a function with no declared policy and
                no explicit `task` was given.
        """
        declared: Optional[AIRoutePolicy] = None
        undeclared_callable = False
        if isinstance(policy, AIRoutePolicy):
            declared = policy
        elif callable(policy):
            declared = get_declared_ai_policy(policy)
            undeclared_callable = declared is None

        if undeclared_callable:
            name = getattr(policy, "__qualname__", None) or repr(policy)
            if not task:
                raise ValueError(
                    f"{name} was passed as policy= but has no @declare_ai_usage "
                    f"declaration, so there is no task to route or persist a preference "
                    f"under. Decorate the step, or pass an explicit task="
                )
            logger.warning(
                "ai_policy_declaration_missing",
                func=name,
                task=task,
            )

        if declared is None:
            return AIRoutePolicy(
                task=task or "",
                executes=list(DEFAULT_PREFERRED),
                preferred=list(DEFAULT_PREFERRED),
            )
        if task and task != declared.task:
            return AIRoutePolicy(
                task=task,
                executes=list(declared.executes),
                preferred=list(declared.preferred),
            )
        return declared

    @staticmethod
    def _announce(announce: Announce, decision: AIRouteDecision) -> None:
        """
        Tell the user who is running this, if the caller gave us somewhere to say it.

        Just the summary, no "Using" preamble: the sink decides how to present it (today a
        chip, where the words would only eat width), and the OFF case read as
        "Using AI is off for this task".
        """
        if announce is None:
            return
        announce(route_summary(decision))

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

        started = time.monotonic()
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

        content = response.content or ""
        if not content.strip():
            logger.warning(
                "ai_remote_generate_empty",
                connection_id=client.connection_id,
                model=getattr(response, "model", None),
            )
            return AIExecutionError(
                error_message=(
                    f"AI connection '{client.connection_id}' returned an empty response."
                ),
                error_code="EXECUTION_FAILED",
                decision=decision,
                details={"connection_id": client.connection_id},
            )

        logger.info(
            "ai_remote_generate_ok",
            connection_id=client.connection_id,
            model=getattr(response, "model", None),
            duration=round(time.monotonic() - started, 3),
            response_chars=len(content),
        )
        return AIExecutionSuccess(decision=decision, data=content)

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
            # Resolution attaches the configured CLI to every headless decision, so reaching
            # here means the decision was built by hand. Picking one would be choosing for the
            # user, which is the whole thing this layer exists to avoid.
            return AIExecutionError(
                error_message=f"No CLI was resolved for this request. {CONFIG_HINT}",
                error_code="NO_PROVIDER_AVAILABLE",
                decision=decision,
            )

        try:
            adapter = get_headless_adapter(cli)
        except ValueError as e:
            return AIExecutionError(
                error_message=str(e),
                error_code="PROVIDER_UNAVAILABLE",
                decision=decision,
            )

        # A missing binary means the provider is not usable, not that it ran and
        # failed; report it as PROVIDER_UNAVAILABLE with the config hint instead of
        # letting execute() raise into the generic EXECUTION_FAILED handler below.
        if not adapter.is_available():
            return AIExecutionError(
                error_message=f"'{cli}' is not installed. {CONFIG_HINT}",
                error_code="PROVIDER_UNAVAILABLE",
                decision=decision,
            )

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        started = time.monotonic()
        try:
            # The subprocess blocks for up to `timeout` seconds with no way to poll
            # for app exit; run it interruptibly so quitting the TUI mid-call aborts
            # the workflow thread instead of hanging interpreter shutdown.
            response = run_interruptible(
                lambda: adapter.execute(
                    full_prompt,
                    cwd=cwd,
                    timeout=timeout,
                    json_schema=json_schema,
                    model=model,
                )
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
            detail = (response.stderr or "").strip() or f"'{cli}' exited with code {response.exit_code}"
            if response.quota_exhausted:
                logger.error("ai_executor_quota_exhausted", cli=cli)
                return AIExecutionError(
                    error_message=(
                        f"'{cli}' has run out of usage quota. Wait for it to reset or "
                        f"route this task to another provider. Detail: {detail}"
                    ),
                    error_code="QUOTA_EXHAUSTED",
                    decision=decision,
                    details={"cli": cli, "exit_code": response.exit_code},
                )
            return AIExecutionError(
                error_message=detail,
                error_code="EXECUTION_FAILED",
                decision=decision,
                details={"cli": cli, "exit_code": response.exit_code},
            )

        stdout = response.stdout or ""
        if not stdout.strip():
            logger.warning("ai_headless_execute_empty", cli=cli, model=model)
            return AIExecutionError(
                error_message=f"'{cli}' exited successfully but produced no output.",
                error_code="EXECUTION_FAILED",
                decision=decision,
                details={"cli": cli, "exit_code": response.exit_code},
            )

        logger.info(
            "ai_headless_execute_ok",
            cli=cli,
            model=model,
            duration=round(time.monotonic() - started, 3),
            response_chars=len(stdout),
        )
        return AIExecutionSuccess(decision=decision, data=stdout)


__all__ = ["AIExecutor", "DEFAULT_PREFERRED"]
