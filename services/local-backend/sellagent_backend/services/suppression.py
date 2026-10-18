"""Suppression list management (opt-outs, DND, complaints, manual blocks)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Contact, SuppressionEntry
from sellagent_backend.services import audit
from sellagent_backend.services.phone import normalize

REASONS = ("opt_out", "dnd", "complaint", "manual", "invalid", "wrong_number")


def is_suppressed(session: Session, phone_e164: str) -> SuppressionEntry | None:
    return session.scalar(select(SuppressionEntry).where(SuppressionEntry.phone_e164 == phone_e164, SuppressionEntry.active.is_(True)))


def add(session: Session, phone: str, reason: str, *, note: str | None = None, source: str = "operator", actor: str = "operator", region: str = "IN") -> SuppressionEntry:
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    e164 = normalize(phone, region)
    entry = session.scalar(select(SuppressionEntry).where(SuppressionEntry.phone_e164 == e164))
    if entry is None:
        entry = SuppressionEntry(phone_e164=e164, reason=reason, note=note, source=source)
        session.add(entry)
    else:
        entry.active, entry.reason, entry.note, entry.source = True, reason, note, source
    for c in session.scalars(select(Contact).where(Contact.phone_e164 == e164)):
        c.opted_out = True
        c.opt_out_reason = f"suppressed:{reason}"
        c.opted_out_at = datetime.now(UTC)
        if reason == "opt_out":
            c.consent_status = "withdrawn"
    session.flush()
    audit.record(session, "suppression.add", actor=actor, entity_type="suppression", entity_id=entry.id, data={"phone": e164, "reason": reason})
    return entry


def remove(session: Session, entry_id: str, *, actor: str = "operator", justification: str = "") -> None:
    entry = session.get(SuppressionEntry, entry_id)
    if entry is None:
        raise ValueError("suppression entry not found")
    if not justification.strip():
        raise ValueError("a justification is required to lift a suppression")
    entry.active = False
    for c in session.scalars(select(Contact).where(Contact.phone_e164 == entry.phone_e164)):
        if (c.opt_out_reason or "").startswith("suppressed:"):
            c.opted_out = False
            c.opt_out_reason = None
    session.flush()
    audit.record(session, "suppression.remove", actor=actor, entity_type="suppression", entity_id=entry_id, severity="warning", data={"justification": justification})


def list_entries(session: Session, active_only: bool = True) -> list[SuppressionEntry]:
    q = select(SuppressionEntry).order_by(SuppressionEntry.created_at.desc())
    if active_only:
        q = q.where(SuppressionEntry.active.is_(True))
    return list(session.scalars(q))
