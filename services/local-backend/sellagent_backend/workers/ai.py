"""AI Worker and Speech Worker: bounded CPU executors with cancellation, so concurrent requests queue instead of
starving the machine, and the event loop (WebSockets, emergency stop, opt-out) never waits on inference."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sellagent_ai.llm import CancelToken


@dataclass
class Job:
    id: str
    kind: str
    created_at: datetime
    cancel: CancelToken = field(default_factory=CancelToken)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "queued"  # queued | running | done | failed | cancelled
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "status": self.status, "created_at": self.created_at, "started_at": self.started_at, "finished_at": self.finished_at, "error": self.error}


class InferenceWorker:
    def __init__(self, name: str, max_workers: int = 1) -> None:
        self.name = name
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"sellagent-{name}")
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.completed = 0
        self.failed = 0
        self.total_ms = 0.0

    def _register(self, kind: str) -> Job:
        job = Job(uuid.uuid4().hex, kind, datetime.now(UTC))
        with self._lock:
            self.jobs[job.id] = job
            if len(self.jobs) > 200:
                for k in [k for k, j in self.jobs.items() if j.status in ("done", "failed", "cancelled")][:100]:
                    self.jobs.pop(k, None)
        return job

    async def run(self, kind: str, fn: Callable[[CancelToken], Any], *, timeout: float | None = None) -> tuple[Job, Any]:
        job = self._register(kind)

        def _wrapped() -> Any:
            if job.cancel.cancelled:
                job.status = "cancelled"
                return None
            job.status, job.started_at = "running", datetime.now(UTC)
            t0 = time.perf_counter()
            try:
                out = fn(job.cancel)
                job.status = "cancelled" if job.cancel.cancelled else "done"
                self.completed += 1
                return out
            except Exception as exc:
                job.status, job.error = "failed", str(exc)[:300]
                self.failed += 1
                raise
            finally:
                job.finished_at = datetime.now(UTC)
                self.total_ms += (time.perf_counter() - t0) * 1000

        fut = asyncio.get_running_loop().run_in_executor(self.pool, _wrapped)
        try:
            return job, await asyncio.wait_for(fut, timeout) if timeout else await fut
        except TimeoutError:
            job.cancel.cancel()
            job.status, job.error = "cancelled", "timeout"
            raise

    def submit_stream(self, kind: str, fn: Callable[[CancelToken, Callable[[str], None]], None], loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[Any]) -> Job:
        """Run a streaming producer in the pool; pieces are pushed to `queue`; None marks the end."""
        job = self._register(kind)

        def _push(piece: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, piece)

        def _wrapped() -> None:
            job.status, job.started_at = "running", datetime.now(UTC)
            try:
                fn(job.cancel, _push)
                job.status = "cancelled" if job.cancel.cancelled else "done"
                self.completed += 1
            except Exception as exc:  # noqa: BLE001
                job.status, job.error = "failed", str(exc)[:300]
                self.failed += 1
                loop.call_soon_threadsafe(queue.put_nowait, {"error": job.error})
            finally:
                job.finished_at = datetime.now(UTC)
                loop.call_soon_threadsafe(queue.put_nowait, None)

        self.pool.submit(_wrapped)
        return job

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job is None or job.status in ("done", "failed", "cancelled"):
            return False
        job.cancel.cancel()
        return True

    def cancel_all(self) -> int:
        n = 0
        for j in list(self.jobs.values()):
            if j.status in ("queued", "running"):
                j.cancel.cancel()
                n += 1
        return n

    def status(self) -> dict[str, Any]:
        active = [j.to_dict() for j in self.jobs.values() if j.status in ("queued", "running")]
        return {"name": self.name, "active": active, "completed": self.completed, "failed": self.failed, "avg_ms": (self.total_ms / self.completed) if self.completed else None}

    def shutdown(self) -> None:
        self.cancel_all()
        self.pool.shutdown(wait=False, cancel_futures=True)
