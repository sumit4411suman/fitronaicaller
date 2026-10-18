from __future__ import annotations

from typing import Any

from sellagent_protocol import Envelope, MessageType
from sellagent_protocol.messages import Event
from sqlalchemy.orm import Session, sessionmaker

from sellagent_backend.workers.ai import InferenceWorker
from sellagent_backend.workers.jobs import CallQueueWorker, CampaignEngineWorker, FollowupWorker, ReportWorker


class WorkerManager:
    def __init__(self, session_factory: sessionmaker[Session], hub: Any, reports_dir: Any) -> None:
        self.hub = hub

        async def emit(name: str, data: dict[str, Any]) -> None:
            await hub.broadcast_desktop(Envelope.of(MessageType.EVENT, Event(name=name, data=_jsonable(data))))

        self.emit = emit
        self.periodic = {
            "call_queue": CallQueueWorker(session_factory, emit),
            "campaign_engine": CampaignEngineWorker(session_factory, emit),
            "followup_scheduler": FollowupWorker(session_factory, emit),
            "report": ReportWorker(session_factory, emit, reports_dir=reports_dir),
        }
        self.ai = InferenceWorker("ai", max_workers=1)
        self.speech = InferenceWorker("speech", max_workers=1)

    def start(self) -> None:
        for w in self.periodic.values():
            w.start()

    async def stop(self) -> None:
        for w in self.periodic.values():
            await w.stop()
        self.ai.shutdown()
        self.speech.shutdown()

    def status(self) -> dict[str, Any]:
        return {"periodic": {k: w.stats.to_dict() for k, w in self.periodic.items()}, "ai": self.ai.status(), "speech": self.speech.status()}


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v
