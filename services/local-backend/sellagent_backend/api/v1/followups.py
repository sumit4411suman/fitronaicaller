from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from sellagent_backend.api.deps import get_db, require_local_auth
from sellagent_backend.api.schemas import FollowupIn, FollowupOut
from sellagent_backend.api.v1.errors import bad_request, not_found
from sellagent_backend.services import followups as svc

router = APIRouter(prefix="/followups", tags=["followups"], dependencies=[Depends(require_local_auth)])


@router.get("", response_model=list[FollowupOut])
def list_followups(db: Session = Depends(get_db), until: datetime | None = None, contact_id: str | None = None, include_done: bool = False) -> list:
    return svc.list_open(db, until=until, contact_id=contact_id, include_done=include_done)


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
