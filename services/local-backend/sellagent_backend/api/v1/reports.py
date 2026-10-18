from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area
from sellagent_backend.db.models import AuditEvent
from sellagent_backend.services import reports as svc

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_area("reports"))])
audit_router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_area("audit"))])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    return svc.dashboard(db)


@router.get("/campaign/{campaign_id}")
def campaign(campaign_id: str, db: Session = Depends(get_db)) -> dict:
    return svc.campaign_report(db, campaign_id)


@audit_router.get("")
def audit_list(db: Session = Depends(get_db), action: str | None = None, severity: str | None = None, limit: int = Query(200, ge=1, le=2000), offset: int = 0) -> list[dict]:
    q = select(AuditEvent).order_by(AuditEvent.occurred_at.desc())
    if action:
        q = q.where(AuditEvent.action.like(f"{action}%"))
    if severity:
        q = q.where(AuditEvent.severity == severity)
    return [{"id": e.id, "occurred_at": e.occurred_at, "actor": e.actor, "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id, "severity": e.severity, "request_id": e.request_id, "data": e.data} for e in db.scalars(q.limit(limit).offset(offset))]


generated_router = APIRouter(prefix="/reports/generated", tags=["reports"], dependencies=[Depends(require_area("reports"))])


@generated_router.get("")
def list_generated(request: Request) -> list[dict]:
    root = request.app.state.settings.reports_dir
    out = []
    if root.exists():
        for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
            out.append({"date": d.name, "files": sorted(f.name for f in d.iterdir() if f.is_file())})
    return out


@generated_router.post("")
async def generate_now(request: Request, date: str | None = None) -> dict:
    import asyncio
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from sellagent_backend.services import settings_service
    from sellagent_backend.workers.jobs import generate_report

    def _run() -> dict:
        with request.app.state.session_factory() as s:
            tz = ZoneInfo(settings_service.get(s, "general.timezone") or "Asia/Kolkata")
            day = date or datetime.now(UTC).astimezone(tz).date().isoformat()
            datetime.fromisoformat(day)  # validates YYYY-MM-DD
            return generate_report(s, request.app.state.settings.reports_dir, day, tz)

    try:
        info = await asyncio.to_thread(_run)
    except ValueError as exc:
        from sellagent_backend.api.v1.errors import bad_request

        raise bad_request(f"invalid date: {exc}") from exc
    await request.app.state.workers.emit("report.ready", info)
    return info


@generated_router.get("/{date}/{filename}")
def download(date: str, filename: str, request: Request) -> FileResponse:
    import re

    from sellagent_backend.api.v1.errors import not_found

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or filename not in ("summary.json", "calls.csv", "report.html"):
        raise not_found("report file not found")
    path = request.app.state.settings.reports_dir / date / filename
    if not path.is_file():
        raise not_found("report file not found")
    media = {"json": "application/json", "csv": "text/csv; charset=utf-8", "html": "text/html; charset=utf-8"}[filename.rsplit(".", 1)[1]]
    return FileResponse(path, media_type=media, filename=f"sellagent-{date}-{filename}")
