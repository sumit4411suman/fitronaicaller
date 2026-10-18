from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Contact, Followup
from sellagent_backend.services import audit

KINDS = ("call", "demo", "email", "human_handoff")


def create(session: Session, contact_id: str, *, due_at: datetime, kind: str = "call", note: str | None = None, call_id: str | None = None, actor: str = "operator") -> Followup:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    c = session.get(Contact, contact_id)
    if c is None:
        raise ValueError("contact not found")
    if due_at.tzinfo is None:
        raise ValueError("due_at must be timezone-aware")
    f = Followup(contact_id=contact_id, due_at=due_at, kind=kind, note=note, call_id=call_id)
    session.add(f)
    c.next_followup_at = due_at if (c.next_followup_at is None or due_at < c.next_followup_at) else c.next_followup_at
    session.flush()
    audit.record(session, "followup.create", actor=actor, entity_type="followup", entity_id=f.id, data={"kind": kind, "due_at": due_at.isoformat()})
    return f


def complete(session: Session, followup_id: str, *, actor: str = "operator", status: str = "done") -> Followup:
    f = session.get(Followup, followup_id)
    if f is None:
        raise ValueError("follow-up not found")
    if status not in ("done", "cancelled"):
        raise ValueError("status must be done or cancelled")
    f.status, f.completed_at = status, datetime.now(UTC)
    c = session.get(Contact, f.contact_id)
    if c:
        nxt = session.scalar(select(Followup.due_at).where(Followup.contact_id == c.id, Followup.status == "open").order_by(Followup.due_at))
        c.next_followup_at = nxt
    session.flush()
    audit.record(session, f"followup.{status}", actor=actor, entity_type="followup", entity_id=f.id)
    return f


def list_open(session: Session, *, until: datetime | None = None, contact_id: str | None = None, include_done: bool = False) -> list[Followup]:
    q = select(Followup).order_by(Followup.due_at)
    if not include_done:
        q = q.where(Followup.status == "open")
    if until:
        q = q.where(Followup.due_at <= until)
    if contact_id:
        q = q.where(Followup.contact_id == contact_id)
    return list(session.scalars(q))


def to_dict(f: Followup) -> dict[str, Any]:
    return {k: getattr(f, k) for k in ("id", "contact_id", "call_id", "due_at", "kind", "status", "note", "completed_at", "created_at", "updated_at")}
