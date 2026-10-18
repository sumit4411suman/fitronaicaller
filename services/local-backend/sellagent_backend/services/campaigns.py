"""Campaign lifecycle: draft -> authorized -> active -> paused/completed/archived, with membership."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sellagent_backend.db.models import Campaign, CampaignContact, Contact
from sellagent_backend.services import audit, eligibility, settings_service

_TRANSITIONS = {
    "draft": {"authorized", "archived"},
    "authorized": {"active", "draft", "archived"},
    "active": {"paused", "completed"},
    "paused": {"active", "completed", "archived"},
    "completed": {"archived"},
    "archived": set(),
}


class CampaignError(ValueError):
    pass


def create(session: Session, data: dict[str, Any], *, actor: str = "operator") -> Campaign:
    name = (data.get("name") or "").strip()
    if not name:
        raise CampaignError("name is required")
    if session.scalar(select(Campaign).where(Campaign.name == name)):
        raise CampaignError("a campaign with this name already exists")
    mode = data.get("calling_mode") or "human_assisted"
    if mode not in ("human_assisted", "autonomous"):
        raise CampaignError("calling_mode must be human_assisted or autonomous")
    c = Campaign(
        name=name, description=data.get("description"), calling_mode=mode, script_id=data.get("script_id"),
        language=data.get("language") or "auto", max_calls_per_day=int(data.get("max_calls_per_day") or 50),
        max_attempts_per_contact=int(data.get("max_attempts_per_contact") or 3),
        quiet_hours_start=data.get("quiet_hours_start"), quiet_hours_end=data.get("quiet_hours_end"),
        requires_consent=bool(data.get("requires_consent", True)), starts_at=data.get("starts_at"), ends_at=data.get("ends_at"),
        auto_followup=bool(data.get("auto_followup", True)), followup_after_days=int(data.get("followup_after_days") or 2),
    )
    session.add(c)
    session.flush()
    audit.record(session, "campaign.create", actor=actor, entity_type="campaign", entity_id=c.id, data={"name": name, "mode": mode})
    return c


def update(session: Session, campaign_id: str, data: dict[str, Any], *, actor: str = "operator") -> Campaign:
    c = _get(session, campaign_id)
    if c.status in ("active", "completed", "archived") and any(k in data for k in ("calling_mode", "requires_consent")):
        raise CampaignError("cannot change mode/consent policy of an active or finished campaign")
    for k in ("name", "description", "calling_mode", "script_id", "language", "max_calls_per_day", "max_attempts_per_contact", "quiet_hours_start", "quiet_hours_end", "requires_consent", "starts_at", "ends_at", "auto_followup", "followup_after_days"):
        if k in data:
            setattr(c, k, data[k])
    if c.status == "authorized" and data:
        c.status, c.authorized_by, c.authorized_at = "draft", None, None  # edits invalidate authorization
    session.flush()
    audit.record(session, "campaign.update", actor=actor, entity_type="campaign", entity_id=c.id, data={k: str(v) for k, v in data.items()})
    return c


def transition(session: Session, campaign_id: str, new_status: str, *, actor: str = "operator") -> Campaign:
    c = _get(session, campaign_id)
    if new_status not in _TRANSITIONS.get(c.status, set()):
        raise CampaignError(f"cannot move campaign from {c.status} to {new_status}")
    if new_status == "authorized":
        if c.calling_mode == "autonomous" and not settings_service.get(session, "release_gate.autonomous_calling_allowed"):
            raise CampaignError("autonomous campaigns cannot be authorized until the audio release gate passes")
        c.authorized_by, c.authorized_at = actor, datetime.now(UTC)
    c.status = new_status
    session.flush()
    audit.record(session, f"campaign.{new_status}", actor=actor, entity_type="campaign", entity_id=c.id, severity="warning" if new_status in ("authorized", "active") else "info")
    return c


def add_contacts(session: Session, campaign_id: str, contact_ids: list[str], *, actor: str = "operator") -> dict[str, int]:
    c = _get(session, campaign_id)
    added = skipped = excluded = 0
    for cid in contact_ids:
        contact = session.get(Contact, cid)
        if contact is None:
            skipped += 1
            continue
        if session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == c.id, CampaignContact.contact_id == cid)):
            skipped += 1
            continue
        snap = eligibility.check(session, contact, campaign=c, mode=c.calling_mode).to_dict()
        status = "pending" if not (contact.opted_out or contact.archived) else "excluded"
        if status == "excluded":
            excluded += 1
        session.add(CampaignContact(campaign_id=c.id, contact_id=cid, status=status, eligibility_snapshot=snap))
        if contact.campaign_id is None:
            contact.campaign_id = c.id
        added += 1
    session.flush()
    audit.record(session, "campaign.add_contacts", actor=actor, entity_type="campaign", entity_id=c.id, data={"added": added, "skipped": skipped, "excluded": excluded})
    return {"added": added, "skipped": skipped, "excluded": excluded}


def members(session: Session, campaign_id: str) -> list[tuple[CampaignContact, Contact]]:
    rows = session.execute(select(CampaignContact, Contact).join(Contact, Contact.id == CampaignContact.contact_id).where(CampaignContact.campaign_id == campaign_id).order_by(CampaignContact.created_at)).all()
    return [(m, c) for m, c in rows]


def stats(session: Session, campaign_id: str) -> dict[str, int]:
    rows = session.execute(select(CampaignContact.status, func.count()).where(CampaignContact.campaign_id == campaign_id).group_by(CampaignContact.status)).all()
    out = {"pending": 0, "queued": 0, "called": 0, "done": 0, "excluded": 0}
    for st, n in rows:
        out[st] = int(n)
    out["total"] = sum(out.values())
    finished = out["called"] + out["done"]
    reachable = out["total"] - out["excluded"]
    out["progress_percent"] = round(100 * finished / reachable, 1) if reachable else 0.0
    return out


def _get(session: Session, campaign_id: str) -> Campaign:
    c = session.get(Campaign, campaign_id)
    if c is None:
        raise CampaignError("campaign not found")
    return c


def to_dict(c: Campaign) -> dict[str, Any]:
    return {k: getattr(c, k) for k in ("id", "name", "description", "status", "authorized_by", "authorized_at", "calling_mode", "script_id", "language", "max_calls_per_day", "max_attempts_per_contact", "quiet_hours_start", "quiet_hours_end", "requires_consent", "starts_at", "ends_at", "created_at", "updated_at")}
