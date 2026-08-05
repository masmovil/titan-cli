"""
Route resolution for the AI execution routing layer.

Resolves which provider a task should use given persisted preferences
(`titan_cli.core.models.AIPreferences`) and provider availability
(`AIAvailabilityChecker`). Never picks a fallback silently: if a persisted
preference's provider is unavailable, resolution reports that user input is
needed instead of guessing, regardless of how many compatible candidates
remain.

The task is the only persisted preference scope. Resolution has exactly three
levels: a runtime override, the user's persisted preference for the task, and
the step's own declared `preferred` order.
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
            if self.availability.is_provider_available(runtime_override):
                return AIRouteDecision(provider=runtime_override, reason="runtime override")
            return AIRouteNeedsInput(
                reason=f"runtime override '{runtime_override}' is not available",
                candidates=self._candidates(),
            )

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
            for provider in policy.preferred:
                if self.availability.is_provider_available(provider):
                    return AIRouteDecision(provider=provider, reason=f"step default '{provider}'")

        return AIRouteNeedsInput(
            reason="no persisted preference and no available step default",
            candidates=self._candidates(),
        )

    def _preferences(self):
        if not self.ai_config or not self.ai_config.preferences:
            return None
        return self.ai_config.preferences

    def _guard_executable(
        self, decision: AIRouteDecision, policy: Optional[AIRoutePolicy], task: str
    ) -> AIRouteResolution:
        """
        Refuse a persisted preference the step's code can't execute.

        The preferences UI only offers what a step declares in `executes`, but
        a preference can predate a step's declaration (or be shared by several
        steps with different abilities). Handing the step a provider it can't
        drive would fail later and further from the cause, so it is refused
        here, by name. `off` is always honored - any step can skip. When the
        step declared no `executes` at all, the guard does not apply and the
        decision passes through unchanged.
        """
        if decision.provider == AIProviderType.OFF:
            return decision
        if not policy or not policy.executes:
            return decision
        if decision.provider in policy.executes:
            return decision
        return AIRouteNeedsInput(
            reason=(
                f"the configured provider for '{task}' is '{decision.provider}', "
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

        Returns `AIRouteDecision` if its exact provider/cli/connection_id is
        available, `AIRouteNeedsInput` if unavailable (never a silent
        fallback, even when a *different* candidate of the same provider type
        happens to be available), or `None` if the preference's provider value
        doesn't map to a known `AIProviderType` (caller should keep checking
        lower-precedence sources).
        """
        try:
            provider = AIProviderType(pref.provider)
        except ValueError:
            return None

        if self._identifier_available(provider, pref.cli or pref.connection_id):
            return AIRouteDecision(
                provider=provider,
                cli=pref.cli,
                connection_id=pref.connection_id,
                reason=reason,
            )

        return AIRouteNeedsInput(
            reason=f"{reason} is no longer available ('{pref.provider}')",
            candidates=self._candidates(),
        )

    def _identifier_available(self, provider: AIProviderType, identifier: Optional[str]) -> bool:
        """
        Whether `provider` is available and, if `identifier` (a specific CLI
        name or connection ID) is given, whether that exact candidate is
        among the available ones - not just any candidate of that provider
        type.
        """
        if provider == AIProviderType.CLI_HEADLESS:
            candidates = self.availability.available_headless_clis()
        elif provider == AIProviderType.CLI_INTERACTIVE:
            candidates = self.availability.available_interactive_clis()
        elif provider == AIProviderType.REMOTE:
            candidates = self.availability.available_remote_connections()
        elif provider == AIProviderType.OFF:
            return True
        else:
            return False

        if identifier is None:
            return bool(candidates)
        return any(candidate.identifier == identifier for candidate in candidates)


__all__ = ["AIRouteResolver", "AIRouteNeedsInput", "AIRouteResolution"]
