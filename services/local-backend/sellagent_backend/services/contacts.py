"""Contact CRUD, search, deduplication, archival and consent recording."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Contact, ContactPermission, SuppressionEntry
from sellagent_backend.services import audit
from sellagent_backend.services.phone import normalize

LEAD_STAGES = ("new", "contacted", "interested", "demo_scheduled", "converted", "not_interested", "do_not_call")
SORTABLE = {"business_name", "created_at", "updated_at", "last_contact_at", "next_followup_at", "lead_stage", "city"}


class ContactError(ValueError):
    pass


class DuplicateContact(ContactError):
    def __init__(self, existing: Contact) -> None:
        super().__init__(f"duplicate of contact {existing.id} ({existing.business_name}, {existing.phone_e164})")
        self.existing = existing


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9ऀ-ॿ]+", " ", (name or "").lower()).strip()


def find_duplicate(session: Session, phone_e164: str, business_name: str | None = None, exclude_id: str | None = None) -> Contact | None:
    q = select(Contact).where(Contact.phone_e164 == phone_e164)
    if exclude_id:
        q = q.where(Contact.id != exclude_id)
    hit = session.scalars(q).first()
    if hit:
        return hit
    if business_name:
        nn = _norm_name(business_name)
        if len(nn) >= 4:
            q2 = select(Contact).where(func.lower(Contact.business_name) == business_name.lower())
            if exclude_id:
                q2 = q2.where(Contact.id != exclude_id)
            for c in session.scalars(q2):
                if _norm_name(c.business_name) == nn and (c.city or "") == "":
                    return c
    return None


def create(session: Session, data: dict[str, Any], *, actor: str = "operator", region: str = "IN", allow_duplicate: bool = False) -> Contact:
    if not (data.get("business_name") or "").strip():
        raise ContactError("business_name is required")
    phone_raw = data.get("phone") or data.get("phone_e164") or data.get("phone_raw")
    e164 = normalize(phone_raw, region)
    if not allow_duplicate:
        dup = find_duplicate(session, e164, data.get("business_name"))
        if dup:
            raise DuplicateContact(dup)
    stage = data.get("lead_stage") or "new"
    if stage not in LEAD_STAGES:
        raise ContactError(f"invalid lead_stage {stage!r}")
    c = Contact(
        business_name=data["business_name"].strip(),
        contact_person=(data.get("contact_person") or None),
        phone_e164=e164,
        phone_raw=str(phone_raw),
        email=(data.get("email") or None),
        city=data.get("city") or None,
        district=data.get("district") or None,
        state=data.get("state") or None,
        country=(data.get("country") or region)[:2].upper(),
        source_url=data.get("source_url") or None,
        source_verification=data.get("source_verification") or "unverified",
        lead_source=data.get("lead_source") or None,
        lead_stage=stage,
        campaign_id=data.get("campaign_id") or None,
        notes=data.get("notes") or None,
        tags=list(data.get("tags") or []),
        consent_status=data.get("consent_status") or "unknown",
    )
    if c.email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", c.email):
        raise ContactError("invalid email address")
    session.add(c)
    session.flush()
    _sync_suppression_flag(session, c)
    audit.record(session, "contact.create", actor=actor, entity_type="contact", entity_id=c.id, data={"phone": e164})
    return c


def update(session: Session, contact_id: str, data: dict[str, Any], *, actor: str = "operator", region: str = "IN") -> Contact:
    c = session.get(Contact, contact_id)
    if c is None:
        raise ContactError("contact not found")
    changes: dict[str, Any] = {}
    if "phone" in data or "phone_e164" in data:
        e164 = normalize(data.get("phone") or data.get("phone_e164"), region)
        if e164 != c.phone_e164:
            dup = find_duplicate(session, e164, exclude_id=c.id)
            if dup:
                raise DuplicateContact(dup)
            changes["phone_e164"] = e164
            c.phone_e164 = e164
            c.phone_raw = data.get("phone") or data.get("phone_e164")
    for field in (
        "business_name", "contact_person", "email", "city", "district", "state", "country", "source_url",
        "source_verification", "lead_source", "lead_stage", "campaign_id", "notes", "tags", "consent_status",
        "last_contact_at", "next_followup_at", "archived",
    ):
        if field in data:
            val = data[field]
            if field == "lead_stage" and val not in LEAD_STAGES:
                raise ContactError(f"invalid lead_stage {val!r}")
            if field == "business_name" and not (val or "").strip():
                raise ContactError("business_name is required")
            if field == "source_verification" and val not in ("unverified", "verified", "rejected"):
                raise ContactError("invalid source_verification")
            if field == "consent_status" and val not in ("unknown", "granted", "denied", "withdrawn"):
                raise ContactError("invalid consent_status")
            setattr(c, field, val)
            changes[field] = val if not isinstance(val, datetime) else val.isoformat()
    session.flush()
    _sync_suppression_flag(session, c)
    audit.record(session, "contact.update", actor=actor, entity_type="contact", entity_id=c.id, data=changes)
    return c


def archive(session: Session, contact_id: str, archived: bool = True, *, actor: str = "operator") -> Contact:
    c = session.get(Contact, contact_id)
    if c is None:
        raise ContactError("contact not found")
    c.archived = archived
    session.flush()
    audit.record(session, "contact.archive" if archived else "contact.unarchive", actor=actor, entity_type="contact", entity_id=c.id)
    return c


def delete(session: Session, contact_id: str, *, actor: str = "operator") -> None:
    c = session.get(Contact, contact_id)
    if c is None:
        raise ContactError("contact not found")
    session.delete(c)
    session.flush()
    audit.record(session, "contact.delete", actor=actor, entity_type="contact", entity_id=contact_id, severity="warning")


def search(
    session: Session,
    *,
    q: str | None = None,
    lead_stage: str | None = None,
    city: str | None = None,
    campaign_id: str | None = None,
    consent_status: str | None = None,
    opted_out: bool | None = None,
    archived: bool | None = False,
    tag: str | None = None,
    sort: str = "updated_at",
    desc: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Contact], int]:
    stmt = select(Contact)
    if archived is not None:
        stmt = stmt.where(Contact.archived.is_(archived))
    if q:
        like = f"%{q.strip()}%"
        digits = re.sub(r"\D", "", q)
        conds = [Contact.business_name.ilike(like), Contact.contact_person.ilike(like), Contact.email.ilike(like), Contact.city.ilike(like)]
        if digits:
            conds.append(Contact.phone_e164.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    if lead_stage:
        stmt = stmt.where(Contact.lead_stage == lead_stage)
    if city:
        stmt = stmt.where(Contact.city.ilike(city))
    if campaign_id:
        stmt = stmt.where(Contact.campaign_id == campaign_id)
    if consent_status:
        stmt = stmt.where(Contact.consent_status == consent_status)
    if opted_out is not None:
        stmt = stmt.where(Contact.opted_out.is_(opted_out))
    if tag:
        stmt = stmt.where(cast(Contact.tags, String).like(f'%"{tag}"%'))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    sort_col = getattr(Contact, sort if sort in SORTABLE else "updated_at")
    stmt = stmt.order_by(sort_col.desc() if desc else sort_col.asc()).limit(min(limit, 500)).offset(offset)
    return list(session.scalars(stmt)), int(total)


def record_permission(
    session: Session, contact_id: str, *, status: str, source: str, evidence: str | None = None,
    channel: str = "voice", recorded_by: str = "operator", expires_at: datetime | None = None,
) -> ContactPermission:
    c = session.get(Contact, contact_id)
    if c is None:
        raise ContactError("contact not found")
    if status not in ("granted", "denied", "withdrawn"):
        raise ContactError("status must be granted, denied or withdrawn")
    if not source.strip():
        raise ContactError("consent source is required")
    p = ContactPermission(
        contact_id=contact_id, status=status, source=source.strip(), evidence=evidence, channel=channel,
        recorded_by=recorded_by, expires_at=expires_at,
    )
    session.add(p)
    c.consent_status = status
    session.flush()
    audit.record(session, "consent.record", actor=recorded_by, entity_type="contact", entity_id=contact_id, data={"status": status, "source": source})
    return p


def opt_out(session: Session, contact_id: str, *, reason: str, actor: str = "operator", source: str = "operator") -> Contact:
    """Immediate opt-out: flags contact, withdraws consent and adds the number to the suppression list."""
    c = session.get(Contact, contact_id)
    if c is None:
        raise ContactError("contact not found")
    now = datetime.now(UTC)
    c.opted_out = True
    c.opt_out_reason = reason
    c.opted_out_at = now
    c.consent_status = "withdrawn"
    c.lead_stage = "do_not_call"
    session.add(ContactPermission(contact_id=c.id, status="withdrawn", source=source, evidence=reason, recorded_by=actor))
    entry = session.scalar(select(SuppressionEntry).where(SuppressionEntry.phone_e164 == c.phone_e164))
    if entry is None:
        session.add(SuppressionEntry(phone_e164=c.phone_e164, reason="opt_out", note=reason, source=source, contact_id=c.id))
    else:
        entry.active = True
        entry.reason = "opt_out"
        entry.note = reason
    session.flush()
    audit.record(session, "contact.opt_out", actor=actor, entity_type="contact", entity_id=c.id, severity="warning", data={"reason": reason})
    return c


def _sync_suppression_flag(session: Session, c: Contact) -> None:
    sup = session.scalar(select(SuppressionEntry).where(SuppressionEntry.phone_e164 == c.phone_e164, SuppressionEntry.active.is_(True)))
    if sup and not c.opted_out:
        c.opted_out = True
        c.opt_out_reason = f"suppressed:{sup.reason}"
        c.opted_out_at = datetime.now(UTC)


def to_dict(c: Contact) -> dict[str, Any]:
    return {
        "id": c.id, "business_name": c.business_name, "contact_person": c.contact_person, "phone_e164": c.phone_e164,
        "phone_raw": c.phone_raw, "email": c.email, "city": c.city, "district": c.district, "state": c.state,
        "country": c.country, "source_url": c.source_url, "source_verification": c.source_verification,
        "lead_source": c.lead_source, "lead_stage": c.lead_stage, "campaign_id": c.campaign_id,
        "last_contact_at": c.last_contact_at, "next_followup_at": c.next_followup_at, "notes": c.notes, "tags": c.tags,
        "consent_status": c.consent_status, "opted_out": c.opted_out, "opt_out_reason": c.opt_out_reason,
        "opted_out_at": c.opted_out_at, "archived": c.archived, "created_at": c.created_at, "updated_at": c.updated_at,
    }
