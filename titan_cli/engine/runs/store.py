"""In-memory workflow run store."""

from __future__ import annotations

from titan_cli.engine.runs.session import RunSession


class RunStore:
    """Persistence abstraction for workflow runs."""

    def __init__(self) -> None:
        self._runs: dict[str, RunSession] = {}

    def save(self, session: RunSession) -> None:
        """Persist or update a workflow run session."""
        self._runs[session.run_id] = session

    def get(self, run_id: str) -> RunSession | None:
        """Load a workflow run session by id."""
        return self._runs.get(run_id)

