"""
Route resolution for the AI execution routing layer.

Resolves which provider a task should use given persisted preferences
(`titan_cli.core.models.AIPreferences`) and provider availability
(`AIAvailabilityChecker`). Never picks a fallback silently: if a resolved
provider is unavailable, resolution reports that user input is needed instead
of guessing, regardless of how many compatible candidates remain.

The task is the only persisted preference scope. Resolution has exactly three
levels: a runtime override, the user's persisted preference for the task, and
the step's own declared `preferred` order.

Each of those levels answers only WHICH KIND of provider to use. Which concrete
connection or CLI serves that kind is a single global setting
(`AIConfig.default_connection` / `AIConfig.default_cli`), attached here so every
decision leaves this module naming the instance that will actually run.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from titan_cli.core.models import AIConfig, AIProviderPreference

from .availability import AIAvailabilityChecker, AIProviderAvailability
from .enums import AIProviderType
from .models import AIRouteDecision, AIRoutePolicy


@dataclass
class AIRouteNeedsInput:
    """
    Resolution could not pick a provider automatically.

    Returned when no preference exists yet, or a persisted preference's
    provider became unavailable. Callers should ask the user; no ask-UI
    exists yet, so callers currently just surface this state.
    """

    reason: str
    candidates: List[AIProviderAvailability] = field(default_factory=list)


AIRouteResolution = AIRouteDecision | AIRouteNeedsInput


class AIRouteResolver:
    """Resolves which provider a task should use, given persisted preferences."""

    def __init__(self, ai_config: Optional[AIConfig], availability: AIAvailabilityChecker):
        self.ai_config = ai_config
        self.availability = availability

    def resolve(
        self,
        task: str,
        policy: Optional[AIRoutePolicy] = None,
        runtime_override: Optional[AIProviderType] = None,
    ) -> AIRouteResolution:
        """
        Resolve a provider following this precedence: runtime override ->
        persisted task preference -> the step's declared `preferred` order ->
        ask the user (no silent fallback).
        """
        if runtime_override is not None:
            resolved = self._decide(runtime_override, reason="runtime override")
            if isinstance(resolved, AIRouteDecision):
                return self._guard_executable(resolved, policy, task, source="requested")
            return resolved

        preferences = self._preferences()

        if preferences and task in preferences.tasks:
            resolved = self._resolve_preference(
                preferences.tasks[task],
                reason=f"task preference for '{task}'",
            )
            if isinstance(resolved, AIRouteDecision):
                return self._guard_executable(resolved, policy, task)
            if resolved is not None:
                return resolved

        if policy and policy.preferred:
            # Keep the first concrete obstacle: "no default CLI is configured" tells the user
            # what to do, where a generic "nothing resolved" would not.
            first_obstacle: Optional[AIRouteNeedsInput] = None
            for provider in policy.preferred:
                resolved = self._decide(provider, reason=f"step default '{provider}'")
                if isinstance(resolved, AIRouteDecision):
                    return resolved
                first_obstacle = first_obstacle or resolved
            if first_obstacle:
                return first_obstacle

        return AIRouteNeedsInput(
            reason="no persisted preference and no available step default",
            candidates=self._candidates(),
        )

    def _decide(self, provider: AIProviderType, reason: str) -> AIRouteResolution:
        """
        Turn a provider TYPE into a decision naming the instance that will run it.

        The instance is never part of the choice being made here - it is the single global
        default for that kind of provider. A missing or uninstalled default is reported by
        name rather than swapped for whatever else happens to be available.
        """
        if provider == AIProviderType.OFF:
            return AIRouteDecision(provider=provider, reason=reason)

        identifier = self._configured_instance(provider)
        if identifier is None:
            return AIRouteNeedsInput(
                reason=self._missing_instance_reason(provider),
                candidates=self._candidates(),
            )

        if not self._identifier_available(provider, identifier):
            return AIRouteNeedsInput(
                reason=(
                    f"the configured {self._instance_noun(provider)} '{identifier}' "
                    f"is not available"
                ),
                candidates=self._candidates(),
            )

        if provider == AIProviderType.REMOTE:
            return AIRouteDecision(provider=provider, connection_id=identifier, reason=reason)
        return AIRouteDecision(provider=provider, cli=identifier, reason=reason)

    def _configured_instance(self, provider: AIProviderType) -> Optional[str]:
        """The global default connection or CLI serving this kind of provider."""
        if not self.ai_config:
            return None
        if provider == AIProviderType.REMOTE:
            return self.ai_config.default_connection
        return self.ai_config.default_cli

    @staticmethod
    def _instance_noun(provider: AIProviderType) -> str:
        return "AI connection" if provider == AIProviderType.REMOTE else "CLI"

    @staticmethod
    def _missing_instance_reason(provider: AIProviderType) -> str:
        if provider == AIProviderType.REMOTE:
            return "no default AI connection is configured"
        return "no default CLI is configured"

    def _preferences(self):
        if not self.ai_config or not self.ai_config.preferences:
            return None
        return self.ai_config.preferences

    def _guard_executable(
        self,
        decision: AIRouteDecision,
        policy: Optional[AIRoutePolicy],
        task: str,
        source: str = "configured",
    ) -> AIRouteResolution:
        """
        Refuse a provider the step's code can't execute.

        The preferences UI only offers what a step declares in `executes`, but
        a preference can predate a step's declaration (or be shared by several
        steps with different abilities), and a runtime override comes from a
        caller that never consulted `executes` at all. Handing the step a
        provider it can't drive would fail later and further from the cause, so
        it is refused here, by name. `off` is always honored - any step can
        skip. When the step declared no `executes` at all, the guard does not
        apply and the decision passes through unchanged.
        """
        if decision.provider == AIProviderType.OFF:
            return decision
        if not policy or not policy.executes:
            return decision
        if decision.provider in policy.executes:
            return decision
        return AIRouteNeedsInput(
            reason=(
                f"the {source} provider for '{task}' is '{decision.provider}', "
                f"which this step cannot run (it supports: "
                f"{', '.join(str(p) for p in policy.executes)})"
            ),
            candidates=self._candidates(),
        )

    def _candidates(self) -> List[AIProviderAvailability]:
        return (
            self.availability.available_remote_connections()
            + self.availability.available_headless_clis()
            + self.availability.available_interactive_clis()
        )

    def _resolve_preference(
        self, pref: AIProviderPreference, reason: str
    ) -> Optional[AIRouteResolution]:
        """
        Try to honor a persisted preference.

        The preference names only a kind of provider; `_decide` attaches the global instance
        and reports by name if that instance is missing or unavailable. Returns `None` when
        the stored provider value doesn't map to a known `AIProviderType`, so the caller keeps
        checking lower-precedence sources.
        """
        try:
            provider = AIProviderType(pref.provider)
        except ValueError:
            return None

        return self._decide(provider, reason=reason)

    def _identifier_available(self, provider: AIProviderType, identifier: str) -> bool:
        """
        Whether that exact CLI or connection is among the available ones.

        Exact, not "any candidate of the same kind": a configured provider that has gone
        away must be reported, never swapped for a sibling the user didn't choose.
        """
        if provider == AIProviderType.CLI_HEADLESS:
            candidates = self.availability.available_headless_clis()
        elif provider == AIProviderType.CLI_INTERACTIVE:
            candidates = self.availability.available_interactive_clis()
        elif provider == AIProviderType.REMOTE:
            candidates = self.availability.available_remote_connections()
        else:
            return False

        return any(candidate.identifier == identifier for candidate in candidates)


__all__ = ["AIRouteResolver", "AIRouteNeedsInput", "AIRouteResolution"]
