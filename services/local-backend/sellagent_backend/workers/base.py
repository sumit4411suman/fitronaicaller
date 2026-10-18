"""Periodic background worker with run statistics. DB work runs in a thread so the event loop
(WebSockets, emergency stop) is never blocked."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger("sellagent.workers")
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class WorkerStats:
    name: str
    interval_s: float
    runs: int = 0
    errors: int = 0
    items: int = 0
    last_run_at: datetime | None = None
    last_duration_ms: float | None = None
    last_error: str | None = None
    last_result: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("name", "interval_s", "runs", "errors", "items", "last_run_at", "last_duration_ms", "last_error", "last_result", "enabled")}


class PeriodicWorker:
    name = "worker"
    interval_s = 30.0

    def __init__(self, session_factory: sessionmaker[Session], emit: Emit) -> None:
        self.sf = session_factory
        self.emit = emit
        self.stats = WorkerStats(self.name, self.interval_s)
        self._task: asyncio.Task[Any] | None = None
        self._wake = asyncio.Event()

    def run_once_sync(self, session: Session) -> dict[str, Any]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def run_once(self) -> dict[str, Any]:
        t0 = time.perf_counter()
        self.stats.last_run_at = datetime.now(UTC)
        try:
            result = await asyncio.to_thread(self._run_in_session)
            self.stats.last_result = result
            self.stats.items += int(result.get("items", 0))
            self.stats.last_error = None
            for name, data in result.pop("_events", []):
                await self.emit(name, data)
            return result
        except Exception as exc:  # noqa: BLE001
            self.stats.errors += 1
            self.stats.last_error = f"{exc.__class__.__name__}: {exc}"[:500]
            log.exception("%s failed", self.name)
            await self.emit("worker.error", {"worker": self.name, "error": self.stats.last_error})
            return {"error": self.stats.last_error}
        finally:
            self.stats.runs += 1
            self.stats.last_duration_ms = (time.perf_counter() - t0) * 1000

    def _run_in_session(self) -> dict[str, Any]:
        with self.sf() as s:
            try:
                result = self.run_once_sync(s)
                s.commit()
                return result
            except Exception:
                s.rollback()
                raise

    def trigger(self) -> None:
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            if self.stats.enabled:
                await self.run_once()
            try:
                await asyncio.wait_for(self._wake.wait(), self.interval_s)
            except TimeoutError:
                pass
            self._wake.clear()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name=f"worker:{self.name}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
                log.debug("%s stopped: %r", self.name, exc)
            self._task = None
