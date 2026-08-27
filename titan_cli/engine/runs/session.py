"""Workflow run session state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from titan_cli.engine.runs.status import RunSessionStatus
from titan_cli.ports.protocol import EngineEvent
from titan_cli.ports.protocol import InteractionRequest
from titan_cli.ports.protocol import PromptRequest

if TYPE_CHECKING:
    from titan_cli.engine.runs.models import PromptResponse


@dataclass
class RunSession:
    """Mutable state for a workflow run."""

    run_id: str
    workflow_name: str
    status: RunSessionStatus = RunSessionStatus.PENDING
    result_message: Optional[str] = None
    events: list[EngineEvent] = field(default_factory=list)
    pending_prompt: Optional[PromptRequest] = None
    pending_interaction: Optional[InteractionRequest] = None
    prompt_history: list["PromptResponse"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_prompt_answer(self, prompt: PromptRequest, value: object) -> None:
        """Persist a prompt response without exposing extra non-V1 events."""
        from titan_cli.engine.runs.models import PromptResponse

        self.prompt_history.append(
            PromptResponse(prompt_id=prompt.prompt_id, value=value)
        )
        self.pending_prompt = None

    def record_interaction_answer(
        self,
        interaction: InteractionRequest,
        response: dict[str, object],
    ) -> None:
        """Persist interaction response metadata for resume flow."""
        self.metadata.setdefault("interaction_history", []).append(
            {
                "interaction_id": interaction.interaction_id,
                "response_type": response.get("response_type"),
            }
        )
        self.pending_interaction = None
