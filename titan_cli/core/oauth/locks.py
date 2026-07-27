"""Credential-scoped locks for OAuth operations."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import threading
import time

from .exceptions import OAuthLockTimeout


class _OAuthLockAcquisitionCancelled(Exception):
    """Raised inside the worker thread when async lock acquisition is cancelled."""


class _FileLock:
    """Small cross-process file lock with no third-party dependency."""

    def __init__(
        self,
        path: Path,
        *,
        timeout_seconds: float | None,
        poll_interval_seconds: float,
    ) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._handle = None
        self._acquired = False

    def acquire(self, cancel_event: threading.Event | None = None) -> None:
        """Acquire the file lock, waiting up to timeout_seconds."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a+")
        try:
            self._ensure_windows_lock_byte()
        except Exception:
            self._close_handle()
            raise
        start = time.monotonic()

        has_attempted = False
        while True:
            if cancel_event and cancel_event.is_set():
                self._close_handle()
                raise _OAuthLockAcquisitionCancelled
            if has_attempted and self._timed_out(start):
                self._close_handle()
                raise OAuthLockTimeout(
                    f"Timed out waiting for OAuth lock '{self.path.name}'."
                )
            try:
                has_attempted = True
                self._try_acquire_once()
                self._acquired = True
                return
            except OSError as exc:
                if not self._is_lock_contention(exc):
                    self._close_handle()
                    raise
                if self._timed_out(start):
                    self._close_handle()
                    raise OAuthLockTimeout(
                        f"Timed out waiting for OAuth lock '{self.path.name}'."
                    ) from exc
                time.sleep(self._next_sleep_interval(start))

    def release(self) -> None:
        """Release the file lock."""
        if not self._handle:
            return

        try:
            if self._acquired:
                if os.name == "nt":
                    import msvcrt

                    self._handle.seek(0)
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._acquired = False
            self._close_handle()

    def _try_acquire_once(self) -> None:
        if not self._handle:
            raise RuntimeError("File lock handle is not open.")

        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _timed_out(self, start: float) -> bool:
        if self.timeout_seconds is None:
            return False
        return time.monotonic() - start >= self.timeout_seconds

    def _next_sleep_interval(self, start: float) -> float:
        """Return a sleep interval bounded by the remaining timeout."""
        if self.timeout_seconds is None:
            return self.poll_interval_seconds
        elapsed = time.monotonic() - start
        remaining = max(0.0, self.timeout_seconds - elapsed)
        return min(self.poll_interval_seconds, remaining)

    def _is_lock_contention(self, exc: OSError) -> bool:
        """Return whether an OS error represents a busy lock."""
        if getattr(exc, "winerror", None) in {32, 33}:
            return True
        lock_contention_errnos = {
            errno.EACCES,
            errno.EAGAIN,
            errno.EWOULDBLOCK,
        }
        return exc.errno in lock_contention_errnos

    def _ensure_windows_lock_byte(self) -> None:
        """Initialize the byte Windows locks without growing the file on retries."""
        if os.name != "nt" or not self._handle:
            return
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() > 0:
            self._handle.seek(0)
            return
        self._handle.write("0")
        self._handle.flush()
        self._handle.seek(0)

    def _close_handle(self) -> None:
        if self._handle:
            self._handle.close()
            self._handle = None


@dataclass
class OAuthHeldLock:
    """A held OAuth credential lock."""

    key: str
    thread_lock: threading.Lock
    file_lock: _FileLock | None = None

    def release(self) -> None:
        """Release file and in-process locks."""
        try:
            if self.file_lock:
                self.file_lock.release()
        finally:
            self.thread_lock.release()


class OAuthLockManager:
    """Coordinates refresh/login for the same OAuth credential."""

    def __init__(
        self,
        *,
        lock_dir: Path | None = None,
        poll_interval_seconds: float = 0.05,
        enable_file_locks: bool = True,
    ) -> None:
        self.lock_dir = lock_dir or Path.home() / ".titan" / "oauth" / "locks"
        self.poll_interval_seconds = poll_interval_seconds
        self.enable_file_locks = enable_file_locks
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    async def acquire(
        self,
        key: str,
        *,
        timeout_seconds: float | None = 60,
    ) -> OAuthHeldLock:
        """Acquire a credential lock without blocking the event loop."""
        cancel_event = threading.Event()
        worker = asyncio.create_task(
            asyncio.to_thread(
                self.acquire_blocking,
                key,
                timeout_seconds=timeout_seconds,
                _cancel_event=cancel_event,
            )
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancel_event.set()
            try:
                held_lock = await asyncio.shield(worker)
            except _OAuthLockAcquisitionCancelled:
                pass
            except OAuthLockTimeout:
                pass
            else:
                held_lock.release()
            raise

    def acquire_blocking(
        self,
        key: str,
        *,
        timeout_seconds: float | None = 60,
        _cancel_event: threading.Event | None = None,
    ) -> OAuthHeldLock:
        """Acquire a credential lock from synchronous code."""
        started_at = time.monotonic()
        thread_lock = self._get_thread_lock(key)
        self._acquire_thread_lock(
            thread_lock,
            key,
            timeout_seconds=timeout_seconds,
            started_at=started_at,
            cancel_event=_cancel_event,
        )

        file_lock = None
        try:
            if self.enable_file_locks:
                file_lock = _FileLock(
                    self._lock_path(key),
                    timeout_seconds=self._remaining_timeout(
                        started_at,
                        timeout_seconds,
                    ),
                    poll_interval_seconds=self.poll_interval_seconds,
                )
                file_lock.acquire(cancel_event=_cancel_event)
            return OAuthHeldLock(key=key, thread_lock=thread_lock, file_lock=file_lock)
        except Exception:
            thread_lock.release()
            raise

    @asynccontextmanager
    async def lock(
        self,
        key: str,
        *,
        timeout_seconds: float | None = 60,
    ):
        """Async context manager for a credential lock."""
        held_lock = await self.acquire(key, timeout_seconds=timeout_seconds)
        try:
            yield held_lock
        finally:
            await asyncio.to_thread(held_lock.release)

    def _acquire_thread_lock(
        self,
        thread_lock: threading.Lock,
        key: str,
        *,
        timeout_seconds: float | None,
        started_at: float,
        cancel_event: threading.Event | None,
    ) -> None:
        """Acquire an in-process lock while observing async cancellation."""
        while True:
            if cancel_event and cancel_event.is_set():
                raise _OAuthLockAcquisitionCancelled

            acquired = thread_lock.acquire(
                timeout=self._next_poll_timeout(started_at, timeout_seconds)
            )
            if acquired:
                return

            if self._timed_out(started_at, timeout_seconds):
                raise OAuthLockTimeout(f"Timed out waiting for OAuth lock '{key}'.")

    def _next_poll_timeout(
        self,
        start: float,
        timeout_seconds: float | None,
    ) -> float:
        """Return the next bounded wait interval for cancellable acquisition."""
        if timeout_seconds is None:
            return self.poll_interval_seconds
        remaining = timeout_seconds - (time.monotonic() - start)
        return max(0.0, min(self.poll_interval_seconds, remaining))

    def _remaining_timeout(
        self,
        start: float,
        timeout_seconds: float | None,
    ) -> float | None:
        """Return remaining timeout budget from a shared acquisition start."""
        if timeout_seconds is None:
            return None
        return max(0.0, timeout_seconds - (time.monotonic() - start))

    def _timed_out(self, start: float, timeout_seconds: float | None) -> bool:
        """Return whether a lock wait exceeded its timeout."""
        return (
            timeout_seconds is not None
            and time.monotonic() - start >= timeout_seconds
        )

    def _get_thread_lock(self, key: str) -> threading.Lock:
        with self._guard:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def _lock_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.lock_dir / f"{digest}.lock"
