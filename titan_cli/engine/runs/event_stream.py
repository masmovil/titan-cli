"""Run-scoped event stream with backlog and live subscriptions."""

from __future__ import annotations

from collections import defaultdict
from queue import Queue
import threading

from titan_cli.engine.runs.store import RunStore
from titan_cli.ports.protocol import EngineEvent


class RunEventStream:
    """Publish/subscribe stream backed by persisted run events."""

    def __init__(self, run_store: RunStore) -> None:
        self._run_store = run_store
        self._subscribers: dict[str, list[Queue[EngineEvent]]] = defaultdict(list)
        self._lock = threading.RLock()

    def publish(self, event: EngineEvent) -> None:
        """Publish an event to all live subscribers for its run."""
        with self._lock:
            subscribers = list(self._subscribers[event.run_id])
        for queue in subscribers:
            queue.put(event)

    def snapshot(self, run_id: str, after_sequence: int = 0) -> list[EngineEvent]:
        """Return persisted events for a run after the given sequence."""
        with self._lock:
            session = self._run_store.get(run_id)
        if session is None:
            return []
        return [event for event in session.events if event.sequence > after_sequence]

    def subscribe(self, run_id: str) -> Queue[EngineEvent]:
        """Create a live event subscription queue for the given run."""
        queue: Queue[EngineEvent] = Queue()
        with self._lock:
            self._subscribers[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: Queue[EngineEvent]) -> None:
        """Remove a live subscription queue for the given run when present."""
        with self._lock:
            queues = self._subscribers.get(run_id)
            if not queues:
                return
            try:
                queues.remove(queue)
            except ValueError:
                return
            if not queues:
                del self._subscribers[run_id]
