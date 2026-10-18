"""Background worker status and manual triggers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from sellagent_backend.api.deps import require_area
from sellagent_backend.api.v1.errors import not_found

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_area("system"))])


@router.get("/workers")
def workers(request: Request) -> dict:
    return request.app.state.workers.status()


@router.post("/workers/{name}/run")
async def run_worker(name: str, request: Request) -> dict:
    w = request.app.state.workers.periodic.get(name)
    if w is None:
        raise not_found(f"unknown worker {name!r}")
    result = await w.run_once()
    return {"worker": name, "result": result, "stats": w.stats.to_dict()}


@router.post("/workers/{name}/enabled")
def set_enabled(name: str, request: Request, enabled: bool = True) -> dict:
    w = request.app.state.workers.periodic.get(name)
    if w is None:
        raise not_found(f"unknown worker {name!r}")
    w.stats.enabled = enabled
    return w.stats.to_dict()


@router.post("/ai-jobs/{job_id}/cancel")
def cancel_ai_job(job_id: str, request: Request) -> dict:
    wm = request.app.state.workers
    return {"cancelled": wm.ai.cancel(job_id) or wm.speech.cancel(job_id)}
