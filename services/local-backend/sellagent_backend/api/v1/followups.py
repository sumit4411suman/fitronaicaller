from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_area
from sellagent_backend.api.schemas import FollowupIn, FollowupOut
from sellagent_backend.api.v1.errors import bad_request, not_found
from sellagent_backend.services import followups as svc

router = APIRouter(prefix="/followups", tags=["followups"], dependencies=[Depends(require_area("followups"))])


@router.get("", response_model=list[FollowupOut])
def list_followups(db: Session = Depends(get_db), until: datetime | None = None, contact_id: str | None = None, include_done: bool = False) -> list:
    return svc.list_open(db, until=until, contact_id=contact_id, include_done=include_done)


@router.get("/calendar")
def calendar(db: Session = Depends(get_db), month: str | None = None) -> dict:
    """Follow-ups grouped by local day for a month (YYYY-MM), for the calendar view."""
    import calendar as cal
    from datetime import UTC, datetime, timedelta
    from zoneinfo import ZoneInfo

    from sqlalchemy import select

    from sellagent_backend.db.models import Contact, Followup
    from sellagent_backend.services import settings_service

    tz = ZoneInfo(settings_service.get(db, "general.timezone") or "Asia/Kolkata")
    now_local = datetime.now(UTC).astimezone(tz)
    try:
        y, m = (int(x) for x in (month or now_local.strftime("%Y-%m")).split("-"))
        start_local = datetime(y, m, 1, tzinfo=tz)
    except ValueError as exc:
        raise bad_request("month must be YYYY-MM") from exc
    days_in = cal.monthrange(y, m)[1]
    end_local = start_local + timedelta(days=days_in)
    rows = db.execute(select(Followup, Contact.business_name).join(Contact, Contact.id == Followup.contact_id).where(Followup.due_at >= start_local.astimezone(UTC), Followup.due_at < end_local.astimezone(UTC)).order_by(Followup.due_at)).all()
    days: dict[str, list[dict]] = {}
    for f, name in rows:
        d = f.due_at.astimezone(tz)
        days.setdefault(d.date().isoformat(), []).append({"id": f.id, "time": d.strftime("%H:%M"), "kind": f.kind, "status": f.status, "contact_id": f.contact_id, "business_name": name, "note": f.note, "overdue": f.status == "open" and f.due_at < datetime.now(UTC)})
    return {"month": f"{y:04d}-{m:02d}", "timezone": str(tz), "days_in_month": days_in, "first_weekday": start_local.weekday(), "days": days, "total": len(rows)}


@router.post("", response_model=FollowupOut, status_code=201)
def create(body: FollowupIn, db: Session = Depends(get_db)) -> object:
    try:
        return svc.create(db, body.contact_id, due_at=body.due_at, kind=body.kind, note=body.note, call_id=body.call_id)
    except ValueError as exc:
        raise (not_found if "not found" in str(exc) else bad_request)(str(exc)) from exc


@router.post("/{followup_id}/complete", response_model=FollowupOut)
def complete(followup_id: str, db: Session = Depends(get_db), status: str = "done") -> object:
    try:
        return svc.complete(db, followup_id, status=status)
    except ValueError as exc:
        raise (not_found if "not found" in str(exc) else bad_request)(str(exc)) from exc
