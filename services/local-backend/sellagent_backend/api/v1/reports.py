from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.db.models import AuditEvent
from sellagent_backend.services import reports as svc

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_local_auth)])
audit_router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_local_auth)])


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
